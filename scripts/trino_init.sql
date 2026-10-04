-- ---------------------------------------------------------------------------
-- trino-init.sql : define el esquema, la tabla externa "playas" y una vista
-- con los tipos ya convertidos.
--
-- La tabla NO copia datos: apunta al CSV que vive en MinIO.
--
-- IMPORTANTE (limitacion real de Hive, no de Trino):
--   El SerDe CSV de Hive (OpenCSVSerde) solo sabe leer columnas de texto.
--   Si declaras "longitud_m bigint" o "bandera_azul boolean" el CREATE TABLE
--   falla con:
--     "Hive CSV storage format only supports VARCHAR (unbounded).
--      Unsupported columns: ..."
--   Solucion: declarar todo como varchar y convertir los tipos en una VISTA.
--   (Con Parquet/Avro/ORC si se pueden declarar tipos reales directamente.)
--
-- OJO con el separador: el CSV de playas usa ";" (no ","). OpenCSVSerde lo
-- admite con csv_separator. El fichero se sube a MinIO ya convertido a UTF-8
-- (ver minio_init/init.py), porque el SerDe asume UTF-8 y el original es Latin-1.
-- ---------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS hive.default;

-- Se elimina primero la vista: depende de la tabla.
DROP VIEW IF EXISTS hive.default.playas_tipadas;
DROP TABLE IF EXISTS hive.default.playas;

-- 1) Tabla externa: el CSV crudo, tal cual, todo texto.
CREATE TABLE hive.default.playas (
  nombre            varchar,
  zona              varchar,
  bandera_azul      varchar,
  q_calidad         varchar,
  concejo           varchar,
  accesos           varchar,
  tipo_playa        varchar,
  salvamento        varchar,
  puntos_accesibles varchar,
  servicios         varchar,
  longitud_m        varchar,
  coordenadas       varchar
)
WITH (
  external_location        = 's3://playas/csv/',
  format                   = 'CSV',
  skip_header_line_count   = 1,
  csv_separator            = ';'
);

-- 2) Vista con los tipos ya convertidos: es la que se usa para consultar
--    y la que se registra como dataset en Superset.
--    - bandera_azul: "" -> false, "true" -> true
--    - longitud_m:   "1.500" -> 1500 (el punto es separador de miles)
CREATE OR REPLACE VIEW hive.default.playas_tipadas AS
SELECT
  nombre,
  zona,
  CASE
    WHEN lower(trim(bandera_azul)) = 'true' THEN true
    ELSE false
  END AS bandera_azul,
  q_calidad,
  concejo,
  accesos,
  tipo_playa,
  salvamento,
  puntos_accesibles,
  servicios,
  TRY_CAST(replace(longitud_m, '.', '') AS bigint) AS longitud_m,
  coordenadas
FROM hive.default.playas;
