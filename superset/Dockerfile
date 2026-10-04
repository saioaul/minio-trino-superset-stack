# ---------------------------------------------------------------------------
# Imagen de Superset con lo que necesita este stack:
#   - "trino"          -> driver SQLAlchemy para conectar con Trino
#   - "psycopg2-binary"-> driver de PostgreSQL (metadatos de Superset)
#   - i18n: compila los catalogos .po a messages.json (formato Jed) para que
#     el frontend pueda cargar idiomas distintos del ingles.
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

# ---------------------------------------------------------------------------
# i18n: la imagen oficial solo trae los catalogos gettext (messages.po), pero el
# frontend de Superset descarga en runtime /superset/language_pack/<locale>/, que
# sirve messages.json (formato Jed). Sin ese JSON el frontend no puede cargar
# NINGUN idioma distinto del ingles y la UI se queda en blanco si el locale
# activo no es "en". El tooling oficial de Superset genera ese JSON con Node
# (po2json); aqui lo generamos con Babel, que ya viene en la imagen.
# Se compilan TODOS los locales disponibles y se dejan los ficheros propiedad
# del usuario "superset" (el proceso web corre como ese usuario).
COPY compile_translations.py /tmp/compile_translations.py
RUN /app/.venv/bin/python /tmp/compile_translations.py \
 && rm -f /tmp/compile_translations.py \
 && chown -R superset:superset /app/superset/translations \
 && echo "Packs i18n generados:" \
 && find /app/superset/translations -name messages.json | sort

USER superset
