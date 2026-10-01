-- ---------------------------------------------------------------------------
-- trino-init.sql : define el esquema, la tabla externa "ventas" y una vista
-- con los tipos ya convertidos.
--
-- La tabla NO copia datos: apunta al CSV que vive en MinIO.
--
-- IMPORTANTE (limitacion real de Hive, no de Trino):
--   El SerDe CSV de Hive (OpenCSVSerde) solo sabe leer columnas de texto.
--   Si declaras "fecha date" o "importe double" el CREATE TABLE falla con:
--     "Hive CSV storage format only supports VARCHAR (unbounded).
--      Unsupported columns: fecha date, unidades bigint, importe double"
--   Solucion: declarar todo como varchar y convertir los tipos en una VISTA.
--   (Con Parquet/Avro/ORC si se pueden declarar tipos reales directamente.)
-- ---------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS hive.default;

-- Se elimina primero la vista: depende de la tabla.
DROP VIEW IF EXISTS hive.default.ventas_tipadas;
DROP TABLE IF EXISTS hive.default.ventas;

-- 1) Tabla externa: el CSV crudo, tal cual, todo texto.
CREATE TABLE hive.default.ventas (
  fecha      varchar,
  producto   varchar,
  categoria  varchar,
  ciudad     varchar,
  unidades   varchar,
  importe    varchar
)
WITH (
  external_location        = 's3://ventas/csv/',
  format                   = 'CSV',
  skip_header_line_count   = 1
);

-- 2) Vista con los tipos ya convertidos: es la que se usa para consultar
--    y la que se registra como dataset en Superset.
CREATE OR REPLACE VIEW hive.default.ventas_tipadas AS
SELECT
  CAST(fecha    AS date)   AS fecha,
  producto,
  categoria,
  ciudad,
  CAST(unidades AS bigint) AS unidades,
  CAST(importe  AS double) AS importe
FROM hive.default.ventas;
