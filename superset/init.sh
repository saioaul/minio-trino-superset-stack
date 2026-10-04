#!/bin/sh
# ---------------------------------------------------------------------------
# superset-init: prepara Superset antes de arrancar el servidor web.
#   1. espera a PostgreSQL
#   2. migra el esquema de metadatos
#   3. crea el usuario administrador
#   4. inicializa roles/permisos
#   5. registra la conexion a Trino y el dataset "playas"
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
  echo "[superset-init] Esperando a que Trino pueda ejecutar consultas ..."
  # OJO: abrir el puerto TCP NO significa que Trino este listo. Trino acepta
  # conexiones mientras arranca y responde SERVER_STARTING_UP a las consultas.
  # Por eso esperamos a que una consulta real (SELECT 1) funcione.
  if python - <<'PY'
import sys
import time

import trino

for _ in range(60):
    try:
        conn = trino.dbapi.connect(host="trino", port=8080, user="admin")
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchall()
        cur.close()
        conn.close()
        print("[superset-init] Trino listo para consultas.")
        sys.exit(0)
    except Exception:
        time.sleep(3)

print("[superset-init] Trino no esta listo para consultas.", file=sys.stderr)
sys.exit(1)
PY
  then
    echo "[superset-init] Registrando conexion a Trino y dataset ..."
    python /app/bootstrap.py \
      || echo "[superset-init] AVISO: bootstrap incompleto. Puedes crear la conexion a mano en la UI."

    echo "[superset-init] Creando dashboard con 3 graficos ..."
    python /app/create_dashboard.py \
      || echo "[superset-init] AVISO: no se pudo crear el dashboard. Puedes crearlo a mano en la UI."
  else
    echo "[superset-init] AVISO: se omite el bootstrap porque Trino no responde."
  fi
fi

echo "[superset-init] Listo."
