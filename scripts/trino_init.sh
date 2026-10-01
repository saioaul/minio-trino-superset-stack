#!/bin/sh
# ---------------------------------------------------------------------------
# trino-init: espera a Trino y ejecuta trino_init.sql (esquema + tabla externa).
# Se ejecuta dentro de la imagen trinodb/trino, que ya incluye el CLI "trino".
# ---------------------------------------------------------------------------
set -e

SERVER="http://trino:8080"

echo "[trino-init] Esperando a Trino en ${SERVER} ..."
i=0
until trino --server "$SERVER" --execute "SELECT 1" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 60 ]; then
    echo "[trino-init] ERROR: Trino no responde tras 180s" >&2
    exit 1
  fi
  sleep 3
done
echo "[trino-init] Trino disponible."

echo "[trino-init] Creando esquema, tabla externa y vista tipada ..."
trino --server "$SERVER" --file /tmp/trino_init.sql

echo "[trino-init] Comprobando lectura del CSV desde MinIO:"
trino --server "$SERVER" --execute \
  "SELECT ciudad, count(*) AS filas, sum(importe) AS importe_total
     FROM hive.default.ventas_tipadas
    GROUP BY ciudad
    ORDER BY importe_total DESC"

echo "[trino-init] Hecho."
