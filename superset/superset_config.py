"""
Configuracion de Superset para el stack local.

Se monta en /app/pythonpath/superset_config.py, que es la ruta que la imagen
oficial de Superset anade al PYTHONPATH.
"""

import os

# --- Seguridad ------------------------------------------------------------
SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "cambia-esta-clave")

# --- Base de datos de metadatos (PostgreSQL) ------------------------------
SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_DATABASE_URI")
SQLALCHEMY_TRACK_MODIFICATIONS = False

# --- Servidor web ---------------------------------------------------------
SUPERSET_WEBSERVER_PORT = 8088
ENABLE_PROXY_FIX = True

# --- Ajustes solo para desarrollo local -----------------------------------
# Talisman fuerza HTTPS; en localhost lo desactivamos para evitar redirecciones
# a https:// que rompen el acceso.
TALISMAN_ENABLED = False

# --- Otros ----------------------------------------------------------------
BABEL_DEFAULT_LOCALE = "es"

FEATURE_FLAGS = {
    "ENABLE_TEMPLATE_PROCESSING": True,
}
