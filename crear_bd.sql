-- Expedientes Digitales - Hospital de Diagnóstico
-- MariaDB / MySQL (XAMPP). Importar desde phpMyAdmin. Ojo: borra y vuelve a crear las tablas.
CREATE DATABASE IF NOT EXISTS hospital_hdd CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE hospital_hdd;
SET NAMES utf8mb4;

-- Primero las tablas hijas, al final las padres
DROP TABLE IF EXISTS archivo_partes;
DROP TABLE IF EXISTS archivos;
DROP TABLE IF EXISTS expediente;
DROP TABLE IF EXISTS documentos;
DROP TABLE IF EXISTS empleados;
DROP TABLE IF EXISTS secuencia_codigos;

-- Contador de códigos de empleado. Solo sube: aunque se borre un empleado, su número no se reutiliza.
CREATE TABLE secuencia_codigos (
    nombre VARCHAR(30) PRIMARY KEY,
    ultimo INT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE empleados (
    id INT AUTO_INCREMENT PRIMARY KEY,
    codigo VARCHAR(20) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    puesto VARCHAR(100) NOT NULL,
    area VARCHAR(100) NOT NULL,
    sucursal VARCHAR(50) NOT NULL,
    estado VARCHAR(30) NOT NULL DEFAULT 'Activo',
    fecha_ingreso DATE NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- requiere_vencimiento = 1: al subir este documento la fecha de vencimiento es obligatoria (DUI)
CREATE TABLE documentos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    requiere_vencimiento TINYINT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE expediente (
    empleado_id INT NOT NULL,
    documento_id INT NOT NULL,
    entregado TINYINT NOT NULL DEFAULT 0,
    PRIMARY KEY (empleado_id, documento_id),
    FOREIGN KEY (empleado_id) REFERENCES empleados(id) ON DELETE CASCADE,
    FOREIGN KEY (documento_id) REFERENCES documentos(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Cada subida es una fila nueva, así se conserva el historial de versiones.
-- El primer pedazo (256 KB) del archivo va en "contenido" y el resto, en archivo_partes.
-- Así un archivo de hasta 1 GB nunca llega en un solo paquete a MySQL.
CREATE TABLE archivos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    empleado_id INT NOT NULL,
    documento_id INT NOT NULL,
    version INT NOT NULL,
    nombre_original VARCHAR(255) NOT NULL,
    tamano BIGINT NOT NULL,
    contenido LONGBLOB NOT NULL,
    fecha_vencimiento DATE NULL,
    fecha_subida DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_version (empleado_id, documento_id, version),
    FOREIGN KEY (empleado_id) REFERENCES empleados(id) ON DELETE CASCADE,
    FOREIGN KEY (documento_id) REFERENCES documentos(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE archivo_partes (
    archivo_id INT NOT NULL,
    orden INT NOT NULL,
    contenido LONGBLOB NOT NULL,
    PRIMARY KEY (archivo_id, orden),
    FOREIGN KEY (archivo_id) REFERENCES archivos(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO documentos (nombre, requiere_vencimiento) VALUES
  ('2 fotografías tamaño cédula', 0),
  ('Título de último grado académico y certificaciones', 0),
  ('Carnet de Junta de Vigilancia (según aplique)', 0),
  ('Curriculum vitae', 0),
  ('Solvencia de la Policía Nacional Civil', 0),
  ('Antecedentes penales', 0),
  ('2 recomendaciones personales', 0),
  ('2 recomendaciones laborales', 0),
  ('Fotocopia de DUI', 1),
  ('Fotocopia de NIT', 0),
  ('Fotocopia de ISSS', 0),
  ('Fotocopia de AFP', 0);

INSERT INTO secuencia_codigos (nombre, ultimo) VALUES ('empleado', 6);

INSERT INTO empleados (codigo, nombre, puesto, area, sucursal, estado, fecha_ingreso) VALUES
  ('HDD-0001', 'Camila Herrera', 'Médico/a general', 'Consulta externa', 'Escalón', 'Activo', '2024-02-12'),
  ('HDD-0002', 'Andres Weil', 'Técnico/a de laboratorio', 'Laboratorio', 'Santa Elena', 'Activo', '2025-05-20'),
  ('HDD-0003', 'Hector Calderon', 'Recepcionista', 'Admisión', 'Colonia Médica', 'Activo', '2026-01-08'),
  ('HDD-0004', 'Herberth Barrera', 'Radiólogo/a', 'Imagenología', 'Escalón', 'Activo', '2023-09-01'),
  ('HDD-0005', 'Daniel Gregg', 'Enfermero/a', 'Emergencias', 'Santa Elena', 'Licencia médica', '2026-08-17'),
  ('HDD-0006', 'Belen Diaz', 'Analista de talento humano', 'Talento Humano', 'Colonia Médica', 'Activo', '2025-11-03');

INSERT INTO expediente (empleado_id, documento_id, entregado) VALUES
  (1, 1, 1),
  (1, 2, 1),
  (1, 3, 1),
  (1, 4, 1),
  (1, 5, 1),
  (1, 6, 1),
  (1, 7, 1),
  (1, 8, 1),
  (1, 9, 1),
  (1, 10, 1),
  (1, 11, 1),
  (1, 12, 1),
  (2, 1, 1),
  (2, 2, 1),
  (2, 3, 1),
  (2, 4, 1),
  (2, 5, 1),
  (2, 6, 1),
  (2, 7, 1),
  (2, 8, 1),
  (2, 9, 1),
  (2, 10, 0),
  (2, 11, 0),
  (2, 12, 0),
  (3, 1, 1),
  (3, 2, 1),
  (3, 3, 1),
  (3, 4, 1),
  (3, 5, 0),
  (3, 6, 0),
  (3, 7, 0),
  (3, 8, 0),
  (3, 9, 0),
  (3, 10, 0),
  (3, 11, 0),
  (3, 12, 0),
  (4, 1, 1),
  (4, 2, 1),
  (4, 3, 1),
  (4, 4, 1),
  (4, 5, 1),
  (4, 6, 1),
  (4, 7, 1),
  (4, 8, 1),
  (4, 9, 1),
  (4, 10, 1),
  (4, 11, 1),
  (4, 12, 1),
  (5, 1, 0),
  (5, 2, 0),
  (5, 3, 0),
  (5, 4, 0),
  (5, 5, 0),
  (5, 6, 0),
  (5, 7, 0),
  (5, 8, 0),
  (5, 9, 0),
  (5, 10, 0),
  (5, 11, 0),
  (5, 12, 0),
  (6, 1, 1),
  (6, 2, 1),
  (6, 3, 1),
  (6, 4, 1),
  (6, 5, 1),
  (6, 6, 1),
  (6, 7, 1),
  (6, 8, 1),
  (6, 9, 1),
  (6, 10, 1),
  (6, 11, 1),
  (6, 12, 1);

-- archivos y archivo_partes quedan vacías: los archivos se suben desde el navegador.
