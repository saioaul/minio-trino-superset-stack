"""Compila los catalogos gettext (.po) al JSON (formato Jed) que el frontend
de Superset descarga desde /superset/language_pack/<lang>/.

El tooling oficial de Superset hace esto con Node (gettext-parser + un script
po2json). Aqui hacemos el equivalente en Python con Babel, que ya viene en la
imagen, para no necesitar Node en tiempo de build.

El JSON generado tiene esta forma (la misma que produce el po2json oficial):

    {
      "domain": "superset",
      "locale_data": {
        "superset": {
          "": {"domain": "superset", "lang": "es", "plural_forms": "..."},
          "<msgid>": ["<traduccion singular>", "<traduccion plural>"],
          ...
        }
      }
    }

Uso:
    python compile_translations.py [locale ...]

Sin argumentos compila todos los locales que tengan un messages.po.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from babel.messages.pofile import read_po

# La imagen oficial deja los catalogos aqui. Se puede sobreescribir por si el
# layout cambiara en otra version.
TRANSLATIONS_DIR = Path(
    os.environ.get("SUPERSET_TRANSLATIONS_DIR", "/app/superset/translations")
)
DOMAIN = "superset"

# Correcciones a traducciones erroneas del catalogo oficial de Superset.
# Las aplicamos aqui (en vez de editar los .po de la imagen, que son de solo
# lectura y volverian con cada build) porque son fallos de traduccion upstream.
# Formato: {locale: {msgid: traduccion_correcta}}.
OVERRIDES: dict[str, dict[str, str]] = {
    "es": {
        # En el .po oficial de Superset 6.1.0, "Languages" (el menu de idioma
        # de la barra superior) aparece traducido como "Intervalos", que es
        # incorrecto y despista bastante.
        "Languages": "Idiomas",
    },
}


def _plural_forms(catalog) -> str:
    """Reconstruye la cabecera Plural-Forms que espera Jed.

    En Babel 2.x catalog.plural_forms ya es la cadena completa,
    p. ej. "nplurals=2; plural=(n != 1);". Si por version se expone
    de otra forma, la reconstruimos a partir de sus componentes.
    """
    plural = getattr(catalog, "plural_forms", None)
    if isinstance(plural, str) and plural.strip():
        return plural.strip()
    nplurals = getattr(catalog, "num_plural_forms", None) or 1
    expr = getattr(catalog, "plural_expr", None) or "(n != 1)"
    return f"nplurals={nplurals}; plural={expr};"


def compile_locale(locale: str) -> Path:
    """Convierte translations/<locale>/LC_MESSAGES/messages.po a messages.json."""
    po_path = TRANSLATIONS_DIR / locale / "LC_MESSAGES" / "messages.po"
    if not po_path.is_file():
        raise FileNotFoundError(po_path)

    with po_path.open(encoding="utf-8") as fh:
        catalog = read_po(fh)

    # El frontend (Jed) espera la cabecera bajo la clave "".
    data: dict[str, object] = {
        "": {
            "domain": DOMAIN,
            "lang": locale,
            "plural_forms": _plural_forms(catalog),
        }
    }

    for message in catalog:
        if not message.id:
            continue  # entrada de cabecera del .po, no es una cadena real

        # Un msgid plural llega como tupla (singular, plural); nos quedamos con
        # el singular como clave (igual que hace gettext-parser).
        msgid = message.id if isinstance(message.id, str) else message.id[0]

        # Jed guarda un array: [0] = forma singular, [1..] = formas plurales.
        if isinstance(message.string, dict):
            forms = [str(message.string[k] or "") for k in sorted(message.string)]
        elif isinstance(message.string, (tuple, list)):
            forms = [str(x or "") for x in message.string]
        else:
            forms = [str(message.string or "")]
        translations = forms or [""]

        # gettext-parser (y Jed) usan \x04 como delimitador de contexto.
        key = f"{message.context}\x04{msgid}" if message.context else msgid
        data[key] = translations

    # Aplica las correcciones de traducciones upstream conocidas.
    for msgid, value in OVERRIDES.get(locale, {}).items():
        data[msgid] = [value]

    out_path = po_path.parent / "messages.json"
    out_path.write_text(
        json.dumps(
            {"domain": DOMAIN, "locale_data": {DOMAIN: data}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return out_path


def main(argv: list[str]) -> int:
    locales = argv[1:]
    if not locales:
        locales = sorted(
            p.parent.parent.name
            for p in TRANSLATIONS_DIR.glob("*/LC_MESSAGES/messages.po")
        )

    for locale in locales:
        try:
            out = compile_locale(locale)
        except FileNotFoundError:
            print(f"[i18n] AVISO: no hay messages.po para '{locale}'", file=sys.stderr)
            continue
        print(f"[i18n] {locale} -> {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
