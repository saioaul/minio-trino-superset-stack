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

# --- Idioma ---------------------------------------------------------------
# OJO (leccion aprendida): Superset 6.x trae el i18n DESACTIVADO por defecto
# (en su config.py, LANGUAGES = {}). Con LANGUAGES vacio, si pones un locale
# distinto de "en" en BABEL_DEFAULT_LOCALE, el frontend intenta descargar
# /superset/language_pack/<locale>/, pero ese endpoint devuelve 302 al login
# (exige sesion) y en la imagen solo habia messages.po (sin messages.json) ->
# el JS recibe HTML en vez de JSON, falla el parseo y la UI queda EN BLANCO.
#
# Para poder usar espanol hay que hacer LAS DOS COSAS a la vez:
#   1. habilitar los idiomas aqui con LANGUAGES (si no, no se sirven packs), y
#   2. que existan los messages.json en /app/superset/translations/<locale>/
#      (lo genera superset/Dockerfile en tiempo de build con Babel).
# Con ambas cosas hechas, el idioma se puede cambiar tambien desde la UI
# (Ajustes -> Idioma) sin tocar esta configuracion.
BABEL_DEFAULT_LOCALE = "es"

# Idiomas que ofrece Superset (mismo catalogo que su config.py oficial).
LANGUAGES = {
    "en": {"flag": "us", "name": "English"},
    "es": {"flag": "es", "name": "Spanish"},
    "it": {"flag": "it", "name": "Italian"},
    "fr": {"flag": "fr", "name": "French"},
    "zh": {"flag": "cn", "name": "Chinese"},
    "zh_TW": {"flag": "tw", "name": "Traditional Chinese"},
    "ja": {"flag": "jp", "name": "Japanese"},
    "de": {"flag": "de", "name": "German"},
    "pl": {"flag": "pl", "name": "Polish"},
    "pt": {"flag": "pt", "name": "Portuguese"},
    "pt_BR": {"flag": "br", "name": "Brazilian Portuguese"},
    "ru": {"flag": "ru", "name": "Russian"},
    "ko": {"flag": "kr", "name": "Korean"},
    "sk": {"flag": "sk", "name": "Slovak"},
    "sl": {"flag": "si", "name": "Slovenian"},
    "nl": {"flag": "nl", "name": "Dutch"},
    "uk": {"flag": "uk", "name": "Ukranian"},
    "mi": {"flag": "nz", "name": "Māori"},
}

FEATURE_FLAGS = {
    "ENABLE_TEMPLATE_PROCESSING": True,
}
