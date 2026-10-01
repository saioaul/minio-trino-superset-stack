#!/bin/sh
# ---------------------------------------------------------------------------
# superset-init: prepara Superset antes de arrancar el servidor web.
#   1. espera a PostgreSQL
#   2. migra el esquema de metadatos
#   3. crea el usuario administrador
#   4. inicializa roles/permisos
#   5. registra la conexion a Trino y el dataset "ventas"
# ---------------------------------------------------------------------------
set -e

echo "[superset-init] Esperando a PostgreSQL ..."
python - <<'PY'
import os
import sys
import time

import psycopg2

uri = os.environ["SQLALCHEMY_DATABASE_URI"]
dsn = uri.replace("postgresql+psycopg2://", "postgresql://", 1)

for _ in range(60):
    try:
        psycopg2.connect(dsn).close()
        print("[superset-init] PostgreSQL disponible.")
        sys.exit(0)
    except Exception:
        time.sleep(2)

print("[superset-init] ERROR: no se pudo conectar a PostgreSQL", file=sys.stderr)
sys.exit(1)
PY

echo "[superset-init] Migrando metadatos de Superset ..."
superset db upgrade

echo "[superset-init] Creando usuario administrador ..."
superset fab create-admin \
  --username "${SUPERSET_ADMIN_USER}" \
  --firstname Admin \
  --lastname Admin \
  --email "${SUPERSET_ADMIN_EMAIL}" \
  --password "${SUPERSET_ADMIN_PASSWORD}" \
  || echo "[superset-init] El usuario administrador ya existia."

echo "[superset-init] Inicializando roles y permisos ..."
superset init

if [ "${SUPERSET_BOOTSTRAP:-1}" = "1" ]; then
  echo "[superset-init] Esperando a Trino ..."
  if python - <<'PY'
import socket
import sys
import time

for _ in range(60):
    try:
        with socket.create_connection(("trino", 8080), timeout=3):
            print("[superset-init] Trino disponible.")
            sys.exit(0)
    except OSError:
        time.sleep(3)

print("[superset-init] Trino no responde todavia.", file=sys.stderr)
sys.exit(1)
PY
  then
    echo "[superset-init] Registrando conexion a Trino y dataset ..."
    python /app/bootstrap.py \
      || echo "[superset-init] AVISO: bootstrap incompleto. Puedes crear la conexion a mano en la UI."
  else
    echo "[superset-init] AVISO: se omite el bootstrap porque Trino no responde."
  fi
fi

echo "[superset-init] Listo."
