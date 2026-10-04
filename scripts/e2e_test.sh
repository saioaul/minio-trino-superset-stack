#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Prueba end-to-end del stack:
#   1. Contenedores en marcha
#   2. MinIO contiene el CSV
#   3. Trino lee el CSV y responde SQL
#   4. Superset responde y tiene el dataset
#
# Uso:  ./scripts/e2e_test.sh
# ---------------------------------------------------------------------------
set -uo pipefail

cd "$(dirname "$0")/.."

if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a; . ./.env; set +a
fi

TRINO_PORT="${TRINO_PORT:-8080}"
SUPERSET_PORT="${SUPERSET_PORT:-8088}"
BUCKET="${MINIO_BUCKET:-playas}"

OK=0
FALLOS=0

paso() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
bien()  { printf '\033[1;32m  [OK]\033[0m %s\n' "$1"; OK=$((OK + 1)); }
mal()   { printf '\033[1;31m  [FALLO]\033[0m %s\n' "$1"; FALLOS=$((FALLOS + 1)); }

# ---------------------------------------------------------------------------
paso "1/4  Contenedores del stack"
docker compose ps --format 'table {{.Name}}\t{{.Service}}\t{{.Status}}'
if docker compose ps --status running --services | grep -q .; then
  bien "Hay contenedores en marcha."
else
  mal "No hay contenedores en marcha. Ejecuta: docker compose up -d"
fi

# ---------------------------------------------------------------------------
paso "2/4  MinIO: el CSV esta en el bucket ${BUCKET}"
# Se reutiliza el contenedor minio-init: es idempotente y ya imprime el listado.
LISTADO=$(docker compose run --rm --no-deps minio-init 2>&1)
echo "$LISTADO" | sed 's/^/    /'
if echo "$LISTADO" | grep -q 'csv/playas_Asturias.csv'; then
  bien "El objeto csv/playas_Asturias.csv esta en MinIO."
else
  mal "No se encuentra csv/playas_Asturias.csv en el bucket."
fi

# ---------------------------------------------------------------------------
paso "3/4  Trino: lectura del CSV via SQL"
TOTAL=$(docker compose exec -T trino trino --execute \
  "SELECT count(*) FROM hive.default.playas_tipadas" 2>&1 | tr -d '"[:space:]')
if [ "${TOTAL:-0}" -gt 0 ] 2>/dev/null; then
  bien "Trino lee ${TOTAL} filas desde MinIO."
else
  mal "Trino no ha podido leer la tabla. Salida: ${TOTAL}"
fi

echo "  Resumen por zona:"
docker compose exec -T trino trino --execute \
  "SELECT zona, count(*) AS playas, sum(longitud_m) AS metros_totales
     FROM hive.default.playas_tipadas GROUP BY zona ORDER BY playas DESC" 2>&1 \
  | sed 's/^/    /'

# ---------------------------------------------------------------------------
paso "4/4  Superset: servicio web y dataset"
if curl -sf "http://localhost:${SUPERSET_PORT}/health" >/dev/null; then
  bien "Superset responde en http://localhost:${SUPERSET_PORT}"
else
  mal "Superset no responde en http://localhost:${SUPERSET_PORT}"
fi

if docker compose exec -T superset python -c \
  "import sys; from superset.app import create_app; app=create_app();
with app.app_context():
    from superset import db
    from superset.connectors.sqla.models import SqlaTable
    n = db.session.query(SqlaTable).filter_by(table_name='playas_tipadas').count()
    sys.exit(0 if n else 1)" >/dev/null 2>&1; then
  bien "El dataset 'playas_tipadas' existe en Superset."
else
  mal "El dataset 'playas_tipadas' no existe (crea la conexion y el dataset a mano en la UI)."
fi

# ---------------------------------------------------------------------------
printf '\n\033[1m--- Resumen ---\033[0m\n'
printf '  Comprobaciones OK : %d\n' "$OK"
printf '  Fallos            : %d\n' "$FALLOS"
printf '\n  Siguiente paso: abre el dashboard en http://localhost:%s\n' "$SUPERSET_PORT"
printf '    (Dashboards > Playas de Asturias)\n\n'

[ "$FALLOS" -eq 0 ]
