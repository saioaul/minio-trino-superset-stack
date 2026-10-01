# ---------------------------------------------------------------------------
# Imagen de Superset con los drivers que necesita este stack:
#   - "trino"          -> driver SQLAlchemy para conectar con Trino
#   - "psycopg2-binary"-> driver de PostgreSQL (metadatos de Superset)
# ---------------------------------------------------------------------------
ARG SUPERSET_BASE=apache/superset:latest
FROM ${SUPERSET_BASE}

USER root

# OJO: el layout cambia segun la version de la imagen oficial:
#   - "latest" (6.x): Superset vive en la virtualenv /app/.venv, creada con "uv"
#     y SIN pip. Un `pip install` normal usa el Python del sistema y Superset
#     nunca ve los paquetes -> "ModuleNotFoundError: No module named 'psycopg2'".
#   - versiones fijadas (p.ej. 4.1.2): Python del sistema en /usr/local/bin con
#     pip, sin venv.
# Detectamos el layout y instalamos en el interprete correcto en cada caso.
RUN if [ -x /app/.venv/bin/python ]; then \
        PY=/app/.venv/bin/python; \
        if command -v uv >/dev/null 2>&1; then \
            uv pip install --python "$PY" --no-cache trino psycopg2-binary; \
        else \
            "$PY" -m ensurepip --upgrade \
            && "$PY" -m pip install --no-cache-dir trino psycopg2-binary; \
        fi; \
    else \
        PY=/usr/local/bin/python3; \
        "$PY" -m pip install --no-cache-dir trino psycopg2-binary; \
    fi \
 && "$PY" -c "import trino, psycopg2; print('Drivers trino + psycopg2 OK')"

USER superset
