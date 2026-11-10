// Subida de documentos: arrastrar y soltar, validación en el navegador y barra de progreso.
(function () {
  var formulario = document.getElementById("form-subida");
  var zona = document.getElementById("zona");
  var campo = document.getElementById("archivo");
  var elegido = document.getElementById("elegido");
  var avance = document.getElementById("avance");
  var barra = document.getElementById("barra");
  var porcentaje = document.getElementById("porcentaje");
  var mensaje = document.getElementById("msg-js");
  var maximo = parseInt(formulario.dataset.max, 10);
  var permitidas = [".pdf", ".doc", ".docx"];

  function tamanoLegible(n) {
    if (n >= 1073741824) return (n / 1073741824).toFixed(2) + " GB";
    if (n >= 1048576) return (n / 1048576).toFixed(1) + " MB";
    if (n >= 1024) return Math.round(n / 1024) + " KB";
    return n + " B";
  }

  function avisar(texto) {
    mensaje.textContent = texto;
    mensaje.hidden = !texto;
  }

  // Devuelve un texto de error, o "" si el archivo sirve
  function revisar(archivo) {
    var punto = archivo.name.lastIndexOf(".");
    var extension = punto >= 0 ? archivo.name.slice(punto).toLowerCase() : "";
    if (permitidas.indexOf(extension) === -1) return "Solo se permiten archivos PDF, DOC o DOCX.";
    if (archivo.size === 0) return "El archivo está vacío.";
    if (archivo.size > maximo) return "El archivo supera el máximo de " + tamanoLegible(maximo) + ".";
    return "";
  }

  function mostrar() {
    if (campo.files.length === 0) {
      elegido.hidden = true;
      return;
    }
    var archivo = campo.files[0];
    elegido.textContent = archivo.name + " · " + tamanoLegible(archivo.size);
    elegido.hidden = false;
    avisar(revisar(archivo));
  }

  campo.addEventListener("change", mostrar);

  ["dragenter", "dragover"].forEach(function (nombre) {
    zona.addEventListener(nombre, function (ev) {
      ev.preventDefault();
      zona.classList.add("sobre");
    });
  });
  ["dragleave", "drop"].forEach(function (nombre) {
    zona.addEventListener(nombre, function (ev) {
      ev.preventDefault();
      zona.classList.remove("sobre");
    });
  });
  zona.addEventListener("drop", function (ev) {
    if (ev.dataTransfer.files.length === 0) return;
    // Solo se toma el primer archivo soltado
    var lista = new DataTransfer();
    lista.items.add(ev.dataTransfer.files[0]);
    campo.files = lista.files;
    mostrar();
  });
  // Si se suelta fuera de la zona, el navegador no debe abrir el archivo
  window.addEventListener("dragover", function (ev) { ev.preventDefault(); });
  window.addEventListener("drop", function (ev) { ev.preventDefault(); });

  formulario.addEventListener("submit", function (ev) {
    ev.preventDefault();
    if (campo.files.length === 0) {
      avisar("Selecciona un archivo.");
      return;
    }
    var problema = revisar(campo.files[0]);
    if (problema) {
      avisar(problema);
      return;
    }
    avisar("");
    var boton = formulario.querySelector("button[type=submit]");
    boton.disabled = true;
    avance.hidden = false;

    var peticion = new XMLHttpRequest();
    peticion.open("POST", formulario.action);
    peticion.upload.onprogress = function (e) {
      if (e.lengthComputable) {
        var pct = Math.round((e.loaded / e.total) * 100);
        barra.value = pct;
        porcentaje.textContent = pct + " %";
      }
    };
    peticion.onload = function () {
      // La respuesta es la página siguiente (o el formulario con su error): se muestra tal cual
      document.open();
      document.write(peticion.responseText);
      document.close();
      if (peticion.responseURL && peticion.responseURL !== location.href) {
        history.replaceState(null, "", peticion.responseURL);
      }
    };
    peticion.onerror = function () {
      boton.disabled = false;
      avance.hidden = true;
      avisar("No se pudo enviar el archivo. Revisa que Apache y MySQL sigan encendidos.");
    };
    peticion.send(new FormData(formulario));
  });
})();
