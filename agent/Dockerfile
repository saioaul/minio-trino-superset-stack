# ---------------------------------------------------------------------------
# Agente web (BONUS): convierte un chat en un docker-compose.yml, lo valida
# con Docker y lo prueba de verdad.
#
# Se ejecuta como CONTENEDOR porque necesita hablar con el demonio de Docker.
# El servicio "agent" del docker-compose.yml le monta:
#   - /var/run/docker.sock          -> para poder lanzar "docker compose"
#   - ${PWD}:${PWD}                 -> el repositorio EN LA MISMA RUTA del host
#
# Lo segundo es imprescindible: el compose que genera el agente usa rutas
# relativas (./trino/catalog, ./superset, ./minio_init, ./data). Docker Compose
# las convierte en rutas absolutas del directorio del compose y se las pasa al
# demonio, que las busca en el HOST. Si el repositorio estuviera en otra ruta
# dentro del contenedor, esas rutas no existirian para el demonio.
#
# Uso:
#   docker compose --profile agent up -d --build agent
#   -> http://localhost:8000
# ---------------------------------------------------------------------------
FROM python:3.12-slim

# El cliente de Docker no viene en python:slim: se descarga el binario estatico
# oficial y el plugin "compose" (necesarios para validar y probar el compose).
ARG DOCKER_CLI_VERSION=27.3.1
ARG COMPOSE_VERSION=2.29.7
ARG ARQUITECTURA=x86_64

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && curl -fsSL "https://download.docker.com/linux/static/stable/${ARQUITECTURA}/docker-${DOCKER_CLI_VERSION}.tgz" -o /tmp/docker.tgz \
 && tar -xzf /tmp/docker.tgz --strip-components=1 -C /usr/local/bin docker/docker \
 && mkdir -p /usr/local/lib/docker/cli-plugins \
 && curl -fsSL "https://github.com/docker/compose/releases/download/v${COMPOSE_VERSION}/docker-compose-linux-${ARQUITECTURA}" -o /usr/local/lib/docker/cli-plugins/docker-compose \
 && chmod +x /usr/local/lib/docker/cli-plugins/docker-compose \
 && rm -f /tmp/docker.tgz \
 && apt-get purge -y curl \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONPATH=/opt/agent \
    PYTHONUNBUFFERED=1

WORKDIR /opt/agent

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py generator.py ./
COPY static ./static

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=6 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/ejemplos', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
