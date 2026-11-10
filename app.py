import io
import os
import socket
import time
from urllib.parse import quote
import mysql.connector
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, abort, send_file, Response, flash

app = Flask(__name__)
app.secret_key = "hdd-expedientes-clave-local"

# ---------- Listas para los menús desplegables ----------
SUCURSALES = ["Escalón", "Santa Elena", "Colonia Médica"]
ESTADOS = ["Activo", "Inactivo", "Licencia médica", "Vacaciones"]
AREAS = [
    "Admisión", "Archivo clínico", "Cardiología", "Consulta externa", "Emergencias",
    "Farmacia", "Imagenología", "Laboratorio", "Mantenimiento", "Nutrición",
    "Quirófano", "Recursos humanos", "Talento Humano", "Tecnología", "Administración",
    "Limpieza y servicios generales",
]
PUESTOS = [
    "Médico/a general", "Médico/a especialista", "Radiólogo/a", "Cardiólogo/a", "Enfermero/a",
    "Auxiliar de enfermería", "Técnico/a de laboratorio", "Técnico/a en radiología",
    "Farmacéutico/a", "Nutricionista", "Recepcionista", "Cajero/a", "Asistente administrativo/a",
    "Analista de talento humano", "Contador/a", "Técnico/a de sistemas", "Archivista",
    "Camillero/a", "Personal de limpieza", "Personal de mantenimiento", "Seguridad",
    "Gerente de área", "Director/a médico/a", "Psicólogo/a", "Fisioterapeuta", "Anestesiólogo/a",
]
CLASE_ESTADO = {"Activo": "activo", "Inactivo": "inactivo",
                "Licencia médica": "licencia", "Vacaciones": "vacaciones"}

PREFIJO_CODIGO = "HDD-"

# ---------- Archivos ----------
EXTENSIONES_PERMITIDAS = (".pdf", ".doc", ".docx")
MAX_BYTES = 1024 ** 3          # 1 GB por documento
TAMANO_PARTE = 256 * 1024      # cada pedazo que se guarda en la base de datos
app.config["MAX_CONTENT_LENGTH"] = MAX_BYTES + 8 * 1024 * 1024

# ---------- Servicios de XAMPP que deben estar encendidos ----------
SERVICIOS = [("Apache", "127.0.0.1", 80), ("MySQL", "127.0.0.1", 3306)]
_cache_servicios = {"hora": 0.0, "caidos": []}


def conectar():
    # En XAMPP el usuario es root y la contraseña va vacía
    return mysql.connector.connect(host="localhost", user="root", password="",
                                   database="hospital_hdd", charset="utf8mb4")


def puerto_abierto(host, puerto):
    try:
        with socket.create_connection((host, puerto), timeout=0.6):
            return True
    except OSError:
        return False


def servicios_caidos():
    # Se revisa como mucho una vez por segundo para no frenar cada petición
    ahora = time.time()
    if ahora - _cache_servicios["hora"] > 1:
        _cache_servicios["caidos"] = [n for n, h, p in SERVICIOS if not puerto_abierto(h, p)]
        _cache_servicios["hora"] = ahora
    return _cache_servicios["caidos"]


@app.before_request
def verificar_servicios():
    if request.endpoint == "static":
        return None
    caidos = servicios_caidos()
    if caidos:
        estado = [{"nombre": n, "puerto": p, "activo": n not in caidos} for n, h, p in SERVICIOS]
        return render_template("servicios.html", servicios=estado), 503
    return None


def formato_tamano(n):
    if n >= 1024 ** 3:
        return "%.2f GB" % (n / 1024 ** 3)
    if n >= 1024 ** 2:
        valor = n / 1024 ** 2
        return ("%d MB" % valor) if valor == int(valor) else ("%.1f MB" % valor)
    if n >= 1024:
        return "%d KB" % (n // 1024)
    return "%d B" % n


@app.template_filter("iniciales")
def iniciales(nombre):
    partes = nombre.split()
    if not partes:
        return "?"
    return (partes[0][0] + (partes[-1][0] if len(partes) > 1 else "")).upper()


@app.template_filter("clase_estado")
def clase_estado(estado):
    return CLASE_ESTADO.get(estado, "inactivo")


def con_actual(lista, actual):
    """Si el valor guardado ya no está en la lista, se agrega para no perderlo al editar."""
    return lista if actual in lista else [actual] + lista


@app.errorhandler(mysql.connector.Error)
def error_mysql(e):
    print("Error de MySQL:", e)
    return render_template("error.html", titulo="No se pudo usar la base de datos",
                           mensaje="Verifica que MySQL esté iniciado en XAMPP y que importaste "
                                   "crear_bd.sql en phpMyAdmin.",
                           detalle=str(e)), 500


@app.errorhandler(413)
def archivo_demasiado_grande(e):
    return render_template("error.html", titulo="Archivo demasiado grande",
                           mensaje="El archivo supera el máximo de %s por documento." % formato_tamano(MAX_BYTES),
                           detalle=""), 413


@app.errorhandler(404)
def no_encontrado(e):
    return render_template("error.html", titulo="Página no encontrada",
                           mensaje="El registro o la página que buscas no existe.", detalle=""), 404


def siguiente_codigo(cursor):
    """Devuelve HDD-0007, HDD-0008... El contador solo avanza, así que un código borrado no se repite."""
    cursor.execute("UPDATE secuencia_codigos SET ultimo = ultimo + 1 WHERE nombre = 'empleado'")
    cursor.execute("SELECT ultimo FROM secuencia_codigos WHERE nombre = 'empleado'")
    numero = cursor.fetchone()["ultimo"]
    codigo = "%s%04d" % (PREFIJO_CODIGO, numero)
    # Por si alguien insertó un código a mano en la base: se sigue avanzando hasta uno libre
    cursor.execute("SELECT id FROM empleados WHERE codigo = %s", (codigo,))
    while cursor.fetchone():
        cursor.execute("UPDATE secuencia_codigos SET ultimo = ultimo + 1 WHERE nombre = 'empleado'")
        cursor.execute("SELECT ultimo FROM secuencia_codigos WHERE nombre = 'empleado'")
        codigo = "%s%04d" % (PREFIJO_CODIGO, cursor.fetchone()["ultimo"])
        cursor.execute("SELECT id FROM empleados WHERE codigo = %s", (codigo,))
    return codigo


def obtener_empleados():
    """Empleados con su checklist, sus archivos subidos y sus documentos vencidos."""
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("""
        SELECT e.*,
               CAST(COALESCE(SUM(x.entregado), 0) AS UNSIGNED) AS entregados,
               COUNT(x.documento_id) AS total,
               (SELECT COUNT(DISTINCT a.documento_id) FROM archivos a
                WHERE a.empleado_id = e.id) AS con_archivo,
               (SELECT COUNT(*) FROM archivos a
                WHERE a.empleado_id = e.id AND a.fecha_vencimiento < CURDATE()
                  AND a.version = (SELECT MAX(a2.version) FROM archivos a2
                                   WHERE a2.empleado_id = a.empleado_id
                                     AND a2.documento_id = a.documento_id)) AS vencidos
        FROM empleados e
        LEFT JOIN expediente x ON x.empleado_id = e.id
        GROUP BY e.id
        ORDER BY e.id
    """)
    filas = cursor.fetchall()
    cursor.close()
    conexion.close()
    return filas


@app.route("/")
def inicio():
    return redirect("/empleados")


# ---------- Listado ----------
@app.route("/empleados")
def listar():
    filas = obtener_empleados()
    empleados = []
    completos = 0
    con_vencidos = 0
    docs_subidos = 0
    docs_requeridos = 0
    for fila in filas:
        docs_subidos = docs_subidos + fila["con_archivo"]
        docs_requeridos = docs_requeridos + fila["total"]
        if fila["total"] > 0 and fila["con_archivo"] == fila["total"] and fila["vencidos"] == 0:
            estado, clase = "Completo", "completo"
            completos = completos + 1
        elif fila["vencidos"] > 0:
            estado, clase = "Con vencidos", "vencidos"
            con_vencidos = con_vencidos + 1
        else:
            estado, clase = "Incompleto", "incompleto"
        # Solo se puede eliminar un perfil que no tenga ningún dato asociado
        eliminable = fila["con_archivo"] == 0 and fila["entregados"] == 0
        empleados.append({"datos": fila, "estado": estado, "clase": clase, "eliminable": eliminable})
    kpis = {"total": len(filas), "completos": completos, "con_vencidos": con_vencidos,
            "docs_subidos": docs_subidos, "docs_requeridos": docs_requeridos}
    return render_template("empleados.html", empleados=empleados, kpis=kpis)


# ---------- Registrar ----------
@app.route("/empleados/nuevo", methods=["GET", "POST"])
def nuevo():
    error = ""
    datos = {"nombre": "", "puesto": "", "area": "", "sucursal": "", "estado": "Activo", "fecha_ingreso": ""}
    if request.method == "POST":
        for campo in datos:
            datos[campo] = request.form.get(campo, "").strip()

        fecha_valida = True
        try:
            datetime.strptime(datos["fecha_ingreso"], "%Y-%m-%d")
        except ValueError:
            fecha_valida = False

        if "" in datos.values():
            error = "Todos los campos son obligatorios."
        elif datos["puesto"] not in PUESTOS:
            error = "Selecciona un puesto de la lista."
        elif datos["area"] not in AREAS:
            error = "Selecciona un área de la lista."
        elif datos["sucursal"] not in SUCURSALES:
            error = "Selecciona una sucursal válida."
        elif datos["estado"] not in ESTADOS:
            error = "Selecciona un estado válido."
        elif not fecha_valida:
            error = "La fecha de ingreso no es válida."
        else:
            conexion = conectar()
            cursor = conexion.cursor(dictionary=True)
            codigo = siguiente_codigo(cursor)
            cursor.execute(
                "INSERT INTO empleados (codigo, nombre, puesto, area, sucursal, estado, fecha_ingreso) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (codigo, datos["nombre"], datos["puesto"], datos["area"], datos["sucursal"],
                 datos["estado"], datos["fecha_ingreso"]))
            emp_id = cursor.lastrowid
            cursor.execute("SELECT id FROM documentos")
            for doc in cursor.fetchall():
                cursor.execute(
                    "INSERT INTO expediente (empleado_id, documento_id, entregado) VALUES (%s, %s, 0)",
                    (emp_id, doc["id"]))
            conexion.commit()
            cursor.close()
            conexion.close()
            flash("Empleado registrado con el código %s." % codigo, "ok")
            return redirect("/empleados")
    return render_template("nuevo.html", error=error, datos=datos, sucursales=SUCURSALES,
                           puestos=PUESTOS, areas=AREAS, estados=ESTADOS)


# ---------- Modificar perfil y checklist ----------
@app.route("/empleados/editar/<int:emp_id>", methods=["GET", "POST"])
def editar(emp_id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT * FROM empleados WHERE id = %s", (emp_id,))
    empleado = cursor.fetchone()
    if empleado is None:
        cursor.close()
        conexion.close()
        abort(404)
    cursor.execute("""
        SELECT d.id, d.nombre, x.entregado
        FROM expediente x JOIN documentos d ON d.id = x.documento_id
        WHERE x.empleado_id = %s ORDER BY d.id
    """, (emp_id,))
    docs = cursor.fetchall()

    error = ""
    datos = {"nombre": empleado["nombre"], "puesto": empleado["puesto"], "area": empleado["area"],
             "sucursal": empleado["sucursal"], "estado": empleado["estado"],
             "fecha_ingreso": empleado["fecha_ingreso"].strftime("%Y-%m-%d")}
    if request.method == "POST":
        for campo in datos:
            datos[campo] = request.form.get(campo, "").strip()
        marcados = request.form.getlist("doc")
        validos = {str(d["id"]) for d in docs}

        fecha_valida = True
        try:
            datetime.strptime(datos["fecha_ingreso"], "%Y-%m-%d")
        except ValueError:
            fecha_valida = False

        # Los valores que ya tenía el perfil se aceptan aunque hayan salido de la lista
        if "" in datos.values():
            error = "Todos los campos son obligatorios."
        elif datos["puesto"] not in con_actual(PUESTOS, empleado["puesto"]):
            error = "Selecciona un puesto de la lista."
        elif datos["area"] not in con_actual(AREAS, empleado["area"]):
            error = "Selecciona un área de la lista."
        elif datos["sucursal"] not in con_actual(SUCURSALES, empleado["sucursal"]):
            error = "Selecciona una sucursal válida."
        elif datos["estado"] not in ESTADOS:
            error = "Selecciona un estado válido."
        elif not fecha_valida:
            error = "La fecha de ingreso no es válida."
        elif any(m not in validos for m in marcados):
            error = "Se recibió un documento que no pertenece al expediente."
        else:
            # El código nunca se modifica
            cursor.execute(
                "UPDATE empleados SET nombre = %s, puesto = %s, area = %s, sucursal = %s, "
                "estado = %s, fecha_ingreso = %s WHERE id = %s",
                (datos["nombre"], datos["puesto"], datos["area"], datos["sucursal"],
                 datos["estado"], datos["fecha_ingreso"], emp_id))
            cursor.execute("UPDATE expediente SET entregado = 0 WHERE empleado_id = %s", (emp_id,))
            for m in marcados:
                cursor.execute(
                    "UPDATE expediente SET entregado = 1 WHERE empleado_id = %s AND documento_id = %s",
                    (emp_id, int(m)))
            conexion.commit()
            cursor.close()
            conexion.close()
            flash("Los cambios de %s se guardaron." % empleado["codigo"], "ok")
            return redirect("/empleados")
        # Si hubo error, el checklist conserva lo que el usuario había marcado
        for d in docs:
            d["entregado"] = 1 if str(d["id"]) in marcados else 0
    cursor.close()
    conexion.close()
    return render_template("editar.html", empleado=empleado, docs=docs, error=error, datos=datos,
                           sucursales=con_actual(SUCURSALES, empleado["sucursal"]),
                           puestos=con_actual(PUESTOS, empleado["puesto"]),
                           areas=con_actual(AREAS, empleado["area"]), estados=ESTADOS)


# ---------- Eliminar (solo perfiles sin datos asociados) ----------
@app.route("/empleados/eliminar/<int:emp_id>", methods=["POST"])
def eliminar(emp_id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT codigo, nombre FROM empleados WHERE id = %s", (emp_id,))
    empleado = cursor.fetchone()
    if empleado is None:
        cursor.close()
        conexion.close()
        abort(404)
    cursor.execute("SELECT COUNT(*) AS n FROM archivos WHERE empleado_id = %s", (emp_id,))
    archivos = cursor.fetchone()["n"]
    cursor.execute("SELECT COUNT(*) AS n FROM expediente WHERE empleado_id = %s AND entregado = 1", (emp_id,))
    entregados = cursor.fetchone()["n"]
    if archivos > 0 or entregados > 0:
        cursor.close()
        conexion.close()
        flash("%s no se puede eliminar porque tiene datos asociados (archivos o documentos "
              "entregados). Cambia su estado a Inactivo si ya no trabaja en el hospital." % empleado["codigo"],
              "error")
        return redirect("/empleados")
    cursor.execute("DELETE FROM expediente WHERE empleado_id = %s", (emp_id,))
    cursor.execute("DELETE FROM empleados WHERE id = %s", (emp_id,))
    conexion.commit()
    cursor.close()
    conexion.close()
    flash("Se eliminó el perfil %s." % empleado["codigo"], "ok")
    return redirect("/empleados")


# ---------- Archivos y versiones ----------
def texto_dias(n):
    return "1 día" if n == 1 else "%d días" % n


@app.route("/empleados/<int:emp_id>/archivos")
def ver_archivos(emp_id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT * FROM empleados WHERE id = %s", (emp_id,))
    empleado = cursor.fetchone()
    if empleado is None:
        cursor.close()
        conexion.close()
        abort(404)
    # No se trae la columna contenido: solo lo que se muestra
    cursor.execute("""
        SELECT a.id, a.documento_id, d.nombre AS documento, a.version, a.nombre_original,
               a.tamano, a.fecha_vencimiento, a.fecha_subida
        FROM archivos a JOIN documentos d ON d.id = a.documento_id
        WHERE a.empleado_id = %s
        ORDER BY d.id, a.version DESC
    """, (emp_id,))
    filas = cursor.fetchall()
    cursor.execute("""
        SELECT d.id, d.nombre FROM documentos d
        WHERE d.id NOT IN (SELECT documento_id FROM archivos WHERE empleado_id = %s)
        ORDER BY d.id
    """, (emp_id,))
    pendientes = cursor.fetchall()
    cursor.close()
    conexion.close()

    hoy = date.today()
    grupos = []
    por_documento = {}
    vigentes = 0
    vencidos = 0
    for fila in filas:
        # Vienen de la versión más nueva a la más vieja: la primera de cada documento es la vigente
        es_ultima = fila["documento_id"] not in por_documento
        vence = fila["fecha_vencimiento"]
        aviso = ""
        if not es_ultima:
            estado, clase = "Versión anterior", "anterior"
        elif vence is not None and vence < hoy:
            estado, clase = "Vencido", "vencido"
            aviso = "Venció hace " + texto_dias((hoy - vence).days)
            vencidos = vencidos + 1
        else:
            estado, clase = "Vigente", "vigente"
            if vence == hoy:
                aviso = "Vence hoy"
            elif vence is not None:
                aviso = "Vence en " + texto_dias((vence - hoy).days)
            vigentes = vigentes + 1
        es_pdf = os.path.splitext(fila["nombre_original"])[1].lower() == ".pdf"
        item = {"datos": fila, "estado": estado, "clase": clase, "aviso": aviso,
                "tamano": formato_tamano(fila["tamano"]),
                "tipo": "pdf" if es_pdf else "word", "etiqueta": "PDF" if es_pdf else "DOC"}
        if es_ultima:
            grupo = {"documento_id": fila["documento_id"], "nombre": fila["documento"],
                     "ultima": item, "versiones": [item]}
            por_documento[fila["documento_id"]] = grupo
            grupos.append(grupo)
        else:
            por_documento[fila["documento_id"]]["versiones"].append(item)

    resumen_archivos = {"subidos": len(grupos), "total": len(grupos) + len(pendientes),
                        "vigentes": vigentes, "vencidos": vencidos, "pendientes": len(pendientes)}
    return render_template("archivos.html", empleado=empleado, grupos=grupos,
                           pendientes=pendientes, r=resumen_archivos)


# ---------- Subir un archivo (crea una versión nueva) ----------
@app.route("/empleados/<int:emp_id>/archivos/nuevo", methods=["GET", "POST"])
def subir(emp_id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT * FROM empleados WHERE id = %s", (emp_id,))
    empleado = cursor.fetchone()
    if empleado is None:
        cursor.close()
        conexion.close()
        abort(404)
    cursor.execute("SELECT id, nombre, requiere_vencimiento FROM documentos ORDER BY id")
    documentos = cursor.fetchall()

    error = ""
    datos = {"documento_id": request.args.get("documento", ""), "fecha_vencimiento": ""}
    if request.method == "POST":
        datos["documento_id"] = request.form.get("documento_id", "").strip()
        datos["fecha_vencimiento"] = request.form.get("fecha_vencimiento", "").strip()

        archivo = request.files.get("archivo")
        nombre = ""
        tamano = 0
        if archivo is not None and archivo.filename:
            # Solo el nombre, sin carpetas
            nombre = archivo.filename.replace("\\", "/").split("/")[-1].strip()[:255]
            # El tamaño se obtiene moviéndose al final del flujo, sin cargar el archivo en memoria
            archivo.stream.seek(0, os.SEEK_END)
            tamano = archivo.stream.tell()
            archivo.stream.seek(0)
        extension = os.path.splitext(nombre)[1].lower()

        documento = None
        for d in documentos:
            if str(d["id"]) == datos["documento_id"]:
                documento = d

        fecha_valida = True
        if datos["fecha_vencimiento"] != "":
            try:
                datetime.strptime(datos["fecha_vencimiento"], "%Y-%m-%d")
            except ValueError:
                fecha_valida = False

        if documento is None:
            error = "Selecciona el tipo de documento."
        elif nombre == "":
            error = "Selecciona un archivo."
        elif extension not in EXTENSIONES_PERMITIDAS:
            error = "Solo se permiten archivos PDF, DOC o DOCX."
        elif tamano == 0:
            error = "El archivo está vacío."
        elif tamano > MAX_BYTES:
            error = "El archivo supera el tamaño máximo de %s." % formato_tamano(MAX_BYTES)
        elif documento["requiere_vencimiento"] and datos["fecha_vencimiento"] == "":
            error = "Este documento requiere fecha de vencimiento."
        elif not fecha_valida:
            error = "La fecha de vencimiento no es válida."
        else:
            cursor.execute(
                "SELECT MAX(version) AS ultima FROM archivos WHERE empleado_id = %s AND documento_id = %s",
                (emp_id, documento["id"]))
            version = (cursor.fetchone()["ultima"] or 0) + 1
            # El primer pedazo va en la fila del archivo; el resto, en archivo_partes
            primera = archivo.stream.read(TAMANO_PARTE)
            cursor.execute(
                "INSERT INTO archivos (empleado_id, documento_id, version, nombre_original, tamano, "
                "contenido, fecha_vencimiento) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (emp_id, documento["id"], version, nombre, tamano, primera,
                 datos["fecha_vencimiento"] or None))
            archivo_id = cursor.lastrowid
            orden = 1
            while True:
                pedazo = archivo.stream.read(TAMANO_PARTE)
                if not pedazo:
                    break
                cursor.execute(
                    "INSERT INTO archivo_partes (archivo_id, orden, contenido) VALUES (%s, %s, %s)",
                    (archivo_id, orden, pedazo))
                orden = orden + 1
            cursor.execute(
                "UPDATE expediente SET entregado = 1 WHERE empleado_id = %s AND documento_id = %s",
                (emp_id, documento["id"]))
            # Todo o nada: si algo falla antes de este commit no queda un archivo a medias
            conexion.commit()
            cursor.close()
            conexion.close()
            flash("%s se guardó como versión %d." % (nombre, version), "ok")
            return redirect("/empleados/%d/archivos" % emp_id)
    cursor.close()
    conexion.close()
    return render_template("subir.html", empleado=empleado, documentos=documentos, datos=datos,
                           error=error, limite_texto=formato_tamano(MAX_BYTES), max_bytes=MAX_BYTES)


# ---------- Descargar ----------
@app.route("/archivos/<int:archivo_id>/descargar")
def descargar(archivo_id):
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT nombre_original, tamano, contenido FROM archivos WHERE id = %s", (archivo_id,))
    fila = cursor.fetchone()
    if fila is None:
        cursor.close()
        conexion.close()
        abort(404)
    cursor.execute("SELECT COUNT(*) AS n FROM archivo_partes WHERE archivo_id = %s", (archivo_id,))
    hay_partes = cursor.fetchone()["n"] > 0
    cursor.close()
    conexion.close()

    nombre = fila["nombre_original"]
    if not hay_partes:
        return send_file(io.BytesIO(fila["contenido"]), as_attachment=True, download_name=nombre)

    def leer_partes():
        # Se entrega pedazo por pedazo para no cargar un archivo de 1 GB en memoria
        yield fila["contenido"]
        con = conectar()
        cur = con.cursor()
        orden = 1
        while True:
            cur.execute("SELECT contenido FROM archivo_partes WHERE archivo_id = %s AND orden = %s",
                        (archivo_id, orden))
            parte = cur.fetchone()
            if parte is None:
                break
            yield bytes(parte[0])
            orden = orden + 1
        cur.close()
        con.close()

    respuesta = Response(leer_partes(), mimetype="application/octet-stream")
    respuesta.headers["Content-Disposition"] = "attachment; filename*=UTF-8''" + quote(nombre)
    respuesta.headers["Content-Length"] = str(fila["tamano"])
    return respuesta


# ---------- Resumen ----------
@app.route("/resumen")
def resumen():
    filas = obtener_empleados()
    completos = 0
    con_vencidos = 0
    en_proceso = 0
    sin_archivos = 0
    docs_subidos = 0
    docs_requeridos = 0
    detalle = []
    for fila in filas:
        docs_subidos = docs_subidos + fila["con_archivo"]
        docs_requeridos = docs_requeridos + fila["total"]
        if fila["total"] > 0 and fila["con_archivo"] == fila["total"] and fila["vencidos"] == 0:
            completos = completos + 1
            clase, estado = "completo", "Completo (todos subidos y vigentes)"
        elif fila["vencidos"] > 0:
            con_vencidos = con_vencidos + 1
            clase, estado = "vencidos", "Con documentos vencidos"
        elif fila["con_archivo"] > 0:
            en_proceso = en_proceso + 1
            clase, estado = "proceso", "Incompleto (en proceso)"
        else:
            sin_archivos = sin_archivos + 1
            clase, estado = "vacio", "Incompleto (sin archivos)"
        detalle.append({"datos": fila, "estado": estado, "clase": clase})
    return render_template("resumen.html", detalle=detalle, total=len(filas),
                           completos=completos, con_vencidos=con_vencidos,
                           en_proceso=en_proceso, sin_archivos=sin_archivos,
                           docs_subidos=docs_subidos, docs_requeridos=docs_requeridos)


if __name__ == "__main__":
    app.run(debug=True)
