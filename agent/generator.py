"""
Generador de docker-compose a partir de lenguaje natural.

Enfoque: reglas + plantillas (sin LLM, sin claves de API). El "agente":
  1. interpreta qué servicios quiere el usuario,
  2. aplica puertos y credenciales,
  3. renderiza un docker-compose.yml,
  4. lo valida con "docker compose config",
  5. genera un pequeno informe en Markdown.
"""

from __future__ import annotations

import hashlib
import os
import re
import socket
import subprocess
from typing import Dict, List

import yaml

# Raiz del repositorio, donde vive docker-compose.yml y donde el agente deja el
# compose generado. Dentro de un contenedor se fija con AGENT_REPO_ROOT (el
# servicio "agent" lo monta en la MISMA ruta que tiene en el host, para que las
# rutas relativas ./trino/catalog, ./superset, ./data resuelvan bien).
REPO_ROOT = os.environ.get("AGENT_REPO_ROOT") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

ALL_SERVICES = ["minio", "postgres", "trino", "superset"]

SERVICE_ALIASES: Dict[str, List[str]] = {
    "minio": ["minio", "s3", "data lake", "datalake", "objetos", "almacenamiento"],
    "postgres": ["postgres", "postgresql", "metadatos", "metadata"],
    "trino": ["trino"],
    "superset": [
        "superset",
        "dashboard",
        "dashboards",
        "cuadro de mando",
        "bi",
        "grafico",
        "gráfico",
        "graficos",
        "gráficos",
        "visualizacion",
        "visualización",
    ],
}

DEFAULT_PORTS: Dict[str, Dict[str, int]] = {
    "minio": {"api": 9000, "consola": 9001},
    "postgres": {"db": 5432},
    "trino": {"http": 8080},
    "superset": {"http": 8088},
}

# ---------------------------------------------------------------------------
# Plantillas YAML. Se usa formato "%(...)s" para no chocar con los "${VAR}"
# de docker compose.
# ---------------------------------------------------------------------------

BLOQUE_MINIO = """  minio:
    image: ${MINIO_IMAGE:-%(minio_image)s}
    container_name: %(prefix)s-minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:-%(minio_user)s}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-%(minio_password)s}
    ports:
      - "%(minio_api_port)s:9000"
      - "%(minio_console_port)s:9001"
    volumes:
      - minio_data:/data
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:9000/minio/health/live"]
      interval: 5s
      timeout: 5s
      retries: 12
      start_period: 10s
    networks:
      - bigdata
"""

BLOQUE_MINIO_INIT = """  minio-init:
    build:
      context: ./minio_init
    image: %(prefix)s-minio-init:local
    container_name: %(prefix)s-minio-init
    depends_on:
      minio:
        condition: service_started
    environment:
      S3_ENDPOINT: http://minio:9000
      S3_ACCESS_KEY: ${MINIO_ROOT_USER:-%(minio_user)s}
      S3_SECRET_KEY: ${MINIO_ROOT_PASSWORD:-%(minio_password)s}
      S3_BUCKET: ${MINIO_BUCKET:-%(bucket)s}
      CSV_PATH: /data/ventas.csv
      OBJECT_KEY: csv/ventas.csv
    volumes:
      - ./data:/data:ro
    restart: "no"
    networks:
      - bigdata
"""

BLOQUE_POSTGRES = """  postgres:
    image: postgres:16-alpine
    container_name: %(prefix)s-postgres
    environment:
      POSTGRES_USER: %(postgres_user)s
      POSTGRES_PASSWORD: %(postgres_password)s
      POSTGRES_DB: %(postgres_db)s
    ports:
      - "%(postgres_port)s:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U %(postgres_user)s -d %(postgres_db)s"]
      interval: 5s
      timeout: 5s
      retries: 30
    networks:
      - bigdata
"""

BLOQUE_TRINO_META = """  trino-init-meta:
    image: busybox:latest
    container_name: %(prefix)s-trino-init-meta
    user: root
    command: ["sh", "-c", "mkdir -p /meta && chown -R 1000:1000 /meta"]
    volumes:
      - trino_metastore:/meta
    restart: "no"
    networks:
      - bigdata
"""

BLOQUE_TRINO_CON_MINIO = """  trino:
    image: trinodb/trino:latest
    container_name: %(prefix)s-trino
    depends_on:
      minio:
        condition: service_started
      trino-init-meta:
        condition: service_completed_successfully
    ports:
      - "%(trino_port)s:8080"
    volumes:
      - ./trino/catalog:/etc/trino/catalog:ro
      - trino_metastore:/var/lib/trino/metastore
    networks:
      - bigdata
"""

BLOQUE_TRINO_SOLO = """  trino:
    image: trinodb/trino:latest
    container_name: %(prefix)s-trino
    ports:
      - "%(trino_port)s:8080"
    networks:
      - bigdata
"""

BLOQUE_TRINO_INIT = """  trino-init:
    image: trinodb/trino:latest
    container_name: %(prefix)s-trino-init
    depends_on:
      trino:
        condition: service_started
      minio-init:
        condition: service_completed_successfully
    volumes:
      - ./scripts/trino_init.sql:/tmp/trino_init.sql:ro
      - ./scripts/trino_init.sh:/tmp/trino_init.sh:ro
    entrypoint: ["/bin/sh", "/tmp/trino_init.sh"]
    restart: "no"
    networks:
      - bigdata
"""

BLOQUE_SUPERSET_INIT = """  superset-init:
    build:
      context: ./superset
      args:
        SUPERSET_BASE: ${SUPERSET_IMAGE:-apache/superset:latest}
    image: %(prefix)s-superset:local
    container_name: %(prefix)s-superset-init
    depends_on:
      postgres:
        condition: service_healthy
      trino:
        condition: service_started
    environment:
      SUPERSET_SECRET_KEY: %(superset_secret)s
      SQLALCHEMY_DATABASE_URI: postgresql+psycopg2://%(postgres_user)s:%(postgres_password)s@postgres:5432/%(postgres_db)s
      SUPERSET_ADMIN_USER: %(superset_user)s
      SUPERSET_ADMIN_PASSWORD: %(superset_password)s
      SUPERSET_ADMIN_EMAIL: %(superset_email)s
      TRINO_SQLALCHEMY_URI: trino://admin@trino:8080/hive/default
      SUPERSET_BOOTSTRAP: "1"
    volumes:
      - ./superset/superset_config.py:/app/pythonpath/superset_config.py:ro
      - ./superset/init.sh:/app/init.sh:ro
      - ./superset/bootstrap.py:/app/bootstrap.py:ro
    entrypoint: ["/bin/sh", "/app/init.sh"]
    restart: "no"
    networks:
      - bigdata
"""

BLOQUE_SUPERSET = """  superset:
    build:
      context: ./superset
      args:
        SUPERSET_BASE: ${SUPERSET_IMAGE:-apache/superset:latest}
    image: %(prefix)s-superset:local
    container_name: %(prefix)s-superset
    depends_on:
      superset-init:
        condition: service_completed_successfully
    environment:
      SUPERSET_SECRET_KEY: %(superset_secret)s
      SQLALCHEMY_DATABASE_URI: postgresql+psycopg2://%(postgres_user)s:%(postgres_password)s@postgres:5432/%(postgres_db)s
      PYTHONPATH: /app/pythonpath
    ports:
      - "%(superset_port)s:8088"
    volumes:
      - ./superset/superset_config.py:/app/pythonpath/superset_config.py:ro
    networks:
      - bigdata
"""


# ---------------------------------------------------------------------------
# 1. Interpretacion del texto
# ---------------------------------------------------------------------------

def _excluidos(texto: str) -> List[str]:
    fuera = []
    for servicio, alias in SERVICE_ALIASES.items():
        for a in alias:
            patron = rf"\b(sin|no|quita|elimina|sin\s+el|sin\s+la)\s+(el\s+|la\s+)?{re.escape(a)}\b"
            if re.search(patron, texto):
                fuera.append(servicio)
    return fuera


def detect_services(prompt: str) -> List[str]:
    texto = prompt.lower()

    detectados = [s for s, alias in SERVICE_ALIASES.items() if any(a in texto for a in alias)]

    pide_todo = any(
        p in texto
        for p in ["completo", "todo el stack", "stack entero", "big data", "entero", "full stack", "los cuatro"]
    )

    if not detectados or pide_todo:
        detectados = list(ALL_SERVICES)

    excluidos = _excluidos(texto)
    detectados = [s for s in detectados if s not in excluidos]

    # Reglas de dependencia
    if "superset" in detectados and "postgres" not in detectados:
        detectados.append("postgres")
    if "superset" in detectados and "trino" not in detectados:
        detectados.append("trino")

    return [s for s in ALL_SERVICES if s in detectados]


def _menciones_servicios(texto: str, servicios: List[str]) -> List[tuple]:
    """Posiciones donde se nombra cada servicio, ordenadas."""
    menciones = set()
    for servicio in servicios:
        for alias in SERVICE_ALIASES[servicio]:
            for coincidencia in re.finditer(rf"\b{re.escape(alias)}\b", texto):
                menciones.add((coincidencia.start(), servicio))
    return sorted(menciones)


def _resolver_servicio(posicion: int, menciones: List[tuple], ventana: int = 60) -> str | None:
    """Devuelve el servicio mencionado mas cerca, por delante del numero."""
    candidatos = [
        (posicion - posicion_mencion, servicio)
        for posicion_mencion, servicio in menciones
        if posicion_mencion <= posicion and (posicion - posicion_mencion) <= ventana
    ]
    if not candidatos:
        return None
    return min(candidatos)[1]


def detect_ports(prompt: str, servicios: List[str]) -> Dict[str, Dict[str, int]]:
    """Detecta puertos personalizados asociando cada numero al servicio mas
    cercano (p.ej. "MinIO en el puerto 9100" -> minio)."""
    puertos = {s: dict(DEFAULT_PORTS[s]) for s in servicios}
    texto = prompt.lower()

    menciones = _menciones_servicios(texto, servicios)
    if not menciones:
        return puertos

    asignaciones: Dict[str, List[int]] = {s: [] for s in servicios}
    for coincidencia in re.finditer(r"\b(\d{2,5})\b", texto):
        posicion, numero = coincidencia.start(), int(coincidencia.group(1))
        servicio = _resolver_servicio(posicion, menciones)
        if servicio and numero not in asignaciones[servicio]:
            asignaciones[servicio].append(numero)

    for servicio, numeros in asignaciones.items():
        for indice, clave in enumerate(DEFAULT_PORTS[servicio]):
            if indice < len(numeros):
                puertos[servicio][clave] = numeros[indice]

    return puertos


# ---------------------------------------------------------------------------
# 2. Render del docker-compose
# ---------------------------------------------------------------------------

def build_context(prompt: str, servicios: List[str]) -> Dict[str, object]:
    digest = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:6]
    puertos = detect_ports(prompt, servicios)

    return {
        "prefix": f"agente-{digest}",
        "proyecto": f"agente-{digest}",
        "servicios": servicios,
        "minio_image": "pgsty/minio:latest",
        "minio_user": "admin",
        "minio_password": "minioadmin",
        "bucket": "ventas",
        "minio_api_port": puertos.get("minio", {}).get("api", 9000),
        "minio_console_port": puertos.get("minio", {}).get("consola", 9001),
        "postgres_user": "superset",
        "postgres_password": "superset",
        "postgres_db": "superset",
        "postgres_port": puertos.get("postgres", {}).get("db", 5432),
        "trino_port": puertos.get("trino", {}).get("http", 8080),
        "superset_port": puertos.get("superset", {}).get("http", 8088),
        "superset_secret": "clave-generada-por-el-agente",
        "superset_user": "admin",
        "superset_password": "admin",
        "superset_email": "admin@example.com",
    }


def render_compose(ctx: Dict[str, object]) -> str:
    servicios: List[str] = ctx["servicios"]  # type: ignore[assignment]
    partes: List[str] = []

    if "minio" in servicios:
        partes.append(BLOQUE_MINIO % ctx)
        partes.append(BLOQUE_MINIO_INIT % ctx)
    if "postgres" in servicios:
        partes.append(BLOQUE_POSTGRES % ctx)
    if "trino" in servicios:
        if "minio" in servicios:
            partes.append(BLOQUE_TRINO_META % ctx)
            partes.append(BLOQUE_TRINO_CON_MINIO % ctx)
            partes.append(BLOQUE_TRINO_INIT % ctx)
        else:
            partes.append(BLOQUE_TRINO_SOLO % ctx)
    if "superset" in servicios:
        partes.append(BLOQUE_SUPERSET_INIT % ctx)
        partes.append(BLOQUE_SUPERSET % ctx)

    volumenes = []
    if "minio" in servicios:
        volumenes.append("  minio_data:")
    if "postgres" in servicios:
        volumenes.append("  postgres_data:")
    if "minio" in servicios and "trino" in servicios:
        volumenes.append("  trino_metastore:")

    cabecera = (
        "# docker-compose.yml generado por el agente\n"
        f"# Peticion que lo origino: {ctx.get('peticion', '')}\n"
        f"name: {ctx['proyecto']}\n\nservices:\n"
    )
    cola = "\nnetworks:\n  bigdata:\n    driver: bridge\n"
    if volumenes:
        cola += "\nvolumes:\n" + "\n".join(volumenes) + "\n"

    return cabecera + "\n".join(partes) + cola


# ---------------------------------------------------------------------------
# 3. Validacion y prueba real
# ---------------------------------------------------------------------------

def _ejecutar(cmd: List[str], timeout: int = 120, cwd: str | None = None) -> Dict[str, object]:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd or REPO_ROOT
        )
        return {
            "ok": proc.returncode == 0,
            "codigo": proc.returncode,
            "salida": (proc.stdout + proc.stderr).strip(),
            "comando": " ".join(cmd),
        }
    except FileNotFoundError:
        return {"ok": False, "codigo": None, "salida": "No se encontro el comando 'docker'.", "comando": " ".join(cmd)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "codigo": None, "salida": f"Timeout tras {timeout}s.", "comando": " ".join(cmd)}


def validate(path: str) -> Dict[str, object]:
    """Valida el fichero con 'docker compose config'."""
    return _ejecutar(["docker", "compose", "-f", path, "config", "--quiet"])


def _puertos_host(yaml_text: str) -> List[int]:
    """Puertos del host que publicaria el compose generado (clave 'ports')."""
    try:
        datos = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError:
        return []
    puertos: List[int] = []
    for servicio in (datos.get("services") or {}).values():
        if not isinstance(servicio, dict):
            continue
        for entrada in servicio.get("ports") or []:
            campos = str(entrada).split("/")[0].split(":")
            if len(campos) >= 2 and campos[-2].strip().isdigit():
                puertos.append(int(campos[-2]))
    return sorted(set(puertos))


def _puerto_libre(puerto: int) -> bool:
    """True si nadie esta escuchando en 127.0.0.1:<puerto>."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", puerto)) != 0


def _puertos_publicados_por_docker() -> Dict[int, str]:
    """
    {puerto_host: contenedor} segun 'docker ps'.

    Se pregunta al demonio en lugar de mirar 127.0.0.1 porque el agente puede
    correr dentro de un contenedor, y ahi 127.0.0.1 no es el del host.
    """
    salida = _ejecutar(["docker", "ps", "--format", "{{.Names}}\t{{.Ports}}"], timeout=30)
    if not salida["ok"]:
        return {}
    mapa: Dict[int, str] = {}
    for linea in str(salida["salida"]).splitlines():
        nombre, _, publicados = linea.partition("\t")
        for trozo in publicados.replace(", ", ",").split(","):
            if "->" not in trozo:
                continue
            # Formatos vistos: "0.0.0.0:8080->8080/tcp", ":::8080->8080/tcp" y,
            # cuando hay puertos consecutivos, el rango "0.0.0.0:9000-9001->9000-9001/tcp".
            origen = trozo.split("->")[0]
            if ":" not in origen:
                continue
            rango = origen.rsplit(":", 1)[-1]
            inicio, guion, fin = rango.partition("-")
            if guion and inicio.isdigit() and fin.isdigit():
                for puerto in range(int(inicio), int(fin) + 1):
                    mapa.setdefault(puerto, nombre)
            elif rango.isdigit():
                mapa.setdefault(int(rango), nombre)
    return mapa


def _puertos_en_uso(puertos: List[int]) -> "tuple[List[int], List[str]]":
    """Devuelve (puertos ya ocupados, descripcion de quien los ocupa)."""
    publicados = _puertos_publicados_por_docker()
    if publicados:
        ocupados = [p for p in puertos if p in publicados]
        return ocupados, [f"{publicados[p]} (puerto {p})" for p in ocupados]

    # Sin acceso a 'docker ps' solo queda comprobar el socket local.
    return [p for p in puertos if not _puerto_libre(p)], []


def run_test(path: str, timeout: int = 600) -> Dict[str, object]:
    """
    Prueba real: levanta el stack generado, comprueba que arranca y lo baja.

    Antes de levantar nada comprueba que los puertos del host esten libres: si el
    stack del repositorio ya esta en marcha, los mismos puertos chocarian y el
    error de Docker seria confuso. En ese caso se devuelve un motivo legible.
    Es destructivo solo para el proyecto generado (se usa 'down -v').
    """
    ruta = path if os.path.isabs(path) else os.path.join(REPO_ROOT, path)
    try:
        with open(ruta, "r", encoding="utf-8") as manejador:
            yaml_text = manejador.read()
    except OSError:
        yaml_text = ""

    ocupados, ocupantes = _puertos_en_uso(_puertos_host(yaml_text))
    if ocupados:
        detalle = ", ".join(str(p) for p in ocupados)
        quien = (" Los usan: " + "; ".join(ocupantes) + ".") if ocupantes else ""
        return {
            "ok": False,
            "puertos_ocupados": ocupados,
            "ocupantes": ocupantes,
            "motivo": (
                f"Los puertos {detalle} ya estan en uso, asi que el stack generado no "
                f"podria publicarlos.{quien} Baja el stack que los ocupa "
                f"(por ejemplo `docker compose down`) y vuelve a pulsar Probar."
            ),
            "pasos": [],
        }

    pasos: List[Dict[str, object]] = []

    arriba = _ejecutar(["docker", "compose", "-f", path, "up", "-d"], timeout=timeout)
    pasos.append({"paso": "up -d", **arriba})

    if not arriba["ok"]:
        _ejecutar(["docker", "compose", "-f", path, "down", "-v"], timeout=120)
        return {"ok": False, "pasos": pasos}

    estado = _ejecutar(["docker", "compose", "-f", path, "ps", "--format", "json"], timeout=60)
    pasos.append({"paso": "ps", **estado})

    abajo = _ejecutar(["docker", "compose", "-f", path, "down", "-v"], timeout=180)
    pasos.append({"paso": "down -v", **abajo})

    return {"ok": arriba["ok"] and estado["ok"] and abajo["ok"], "pasos": pasos}


# ---------------------------------------------------------------------------
# 4. Informe
# ---------------------------------------------------------------------------

def build_report(ctx: Dict[str, object], yaml_text: str, validacion: Dict[str, object] | None = None) -> str:
    servicios: List[str] = ctx["servicios"]  # type: ignore[assignment]
    lineas = [
        "## Informe del agente",
        "",
        f"- **Servicios incluidos:** {', '.join(servicios)}",
        f"- **Proyecto Compose:** `{ctx['proyecto']}`",
        f"- **Lineas de YAML generado:** {len(yaml_text.splitlines())}",
        "",
        "### Puertos publicados",
        "",
        "| Servicio | Puerto host | Puerto contenedor |",
        "| --- | --- | --- |",
    ]

    if "minio" in servicios:
        lineas.append(f"| MinIO (API S3) | {ctx['minio_api_port']} | 9000 |")
        lineas.append(f"| MinIO (consola) | {ctx['minio_console_port']} | 9001 |")
    if "postgres" in servicios:
        lineas.append(f"| PostgreSQL | {ctx['postgres_port']} | 5432 |")
    if "trino" in servicios:
        lineas.append(f"| Trino | {ctx['trino_port']} | 8080 |")
    if "superset" in servicios:
        lineas.append(f"| Superset | {ctx['superset_port']} | 8088 |")

    lineas += ["", "### Volumenes persistentes", ""]
    if "minio" in servicios:
        lineas.append("- `minio_data` - objetos del data lake")
    if "postgres" in servicios:
        lineas.append("- `postgres_data` - metadatos de Superset")
    if "minio" in servicios and "trino" in servicios:
        lineas.append("- `trino_metastore` - catalogo del conector Hive")
    if not any(s in servicios for s in ("minio", "postgres")):
        lineas.append("- (ninguno)")

    lineas += ["", "### Avisos", ""]
    avisos: List[str] = []
    if "minio" in servicios and "trino" in servicios:
        avisos.append(
            "Trino monta `./trino/catalog` y `./scripts/trino_init.sh`: el fichero "
            "generado debe vivir en la raiz del repositorio."
        )
    if "superset" in servicios:
        avisos.append(
            "Superset se construye desde `./superset` (Dockerfile con el driver de Trino). "
            "La primera construccion tarda varios minutos."
        )
    avisos.append("Las credenciales son de desarrollo: cambialas antes de exponer el stack.")
    for a in avisos:
        lineas.append(f"- {a}")

    if validacion is not None:
        lineas += ["", "### Validacion (`docker compose config`)", ""]
        lineas.append("Resultado: **" + ("valido" if validacion.get("ok") else "con errores") + "**")
        if validacion.get("salida"):
            lineas += ["", "```", str(validacion["salida"])[:1500], "```"]

    return "\n".join(lineas)


def generate(prompt: str) -> Dict[str, object]:
    """Punto de entrada: peticion en texto -> compose + informe."""
    servicios = detect_services(prompt)
    ctx = build_context(prompt, servicios)
    ctx["peticion"] = prompt.replace("\n", " ")[:160]

    yaml_text = render_compose(ctx)

    return {
        "yaml": yaml_text,
        "ctx": ctx,
        "informe": build_report(ctx, yaml_text),
    }
