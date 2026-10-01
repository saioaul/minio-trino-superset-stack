# ---------------------------------------------------------------------------
# Contenedor de inicializacion del almacenamiento de objetos.
# Instala boto3 y ejecuta init.py (crea el bucket y sube el CSV).
# ---------------------------------------------------------------------------
FROM python:3.12-alpine

RUN pip install --no-cache-dir boto3

COPY init.py /init.py

ENTRYPOINT ["python", "/init.py"]
