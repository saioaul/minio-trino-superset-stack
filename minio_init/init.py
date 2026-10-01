#!/usr/bin/env python3
"""
Inicializa el almacenamiento de objetos: crea el bucket y sube el CSV.

Usa boto3 (API S3 estandar) en vez del cliente `mc`. Ventaja: funciona igual
con cualquier backend compatible con S3 -> MinIO, RustFS, Garage, SeaweedFS...
Basta con cambiar S3_ENDPOINT.
"""

from __future__ import annotations

import os
import time

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

ENDPOINT = os.environ.get("S3_ENDPOINT", "http://minio:9000")
ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "admin")
SECRET_KEY = os.environ.get("S3_SECRET_KEY", "minioadmin")
BUCKET = os.environ.get("S3_BUCKET", "ventas")
REGION = os.environ.get("S3_REGION", "us-east-1")
CSV_PATH = os.environ.get("CSV_PATH", "/data/ventas.csv")
OBJECT_KEY = os.environ.get("OBJECT_KEY", "csv/ventas.csv")
ESPERA_MAXIMA = int(os.environ.get("ESPERA_MAXIMA", "300"))
INTERVALO_REINTENTO = float(os.environ.get("INTERVALO_REINTENTO", "2"))


def cliente():
    return boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        region_name=REGION,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            # Desactivamos los reintentos internos de botocore: el bucle de
            # `esperar()` controla el ritmo y asi los mensajes son legibles.
            retries={"max_attempts": 1},
            connect_timeout=5,
            read_timeout=10,
        ),
    )


def _detalle(error: Exception) -> str:
    """Devuelve un texto corto y util a partir de una excepcion de botocore."""
    respuesta = getattr(error, "response", None)
    if isinstance(respuesta, dict):
        err = respuesta.get("Error", {})
        http = respuesta.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return f"HTTP {http} {err.get('Code')}: {err.get('Message')}"
    return type(error).__name__


def esperar(s3) -> None:
    """
    Espera a que el backend S3 este realmente operativo.

    Ojo: un MinIO recien arrancado puede responder 200 en /minio/health/live
    (el proceso vive) y aun asi devolver 503 XMinioServerNotInitialized en la
    API S3 mientras formatea los discos. Por eso no basta con el healthcheck.
    """
    print(f"[minio-init] Esperando a {ENDPOINT} (max {ESPERA_MAXIMA:.0f}s) ...", flush=True)
    inicio = time.monotonic()
    ultimo = ""
    while time.monotonic() - inicio < ESPERA_MAXIMA:
        try:
            s3.list_buckets()
            print("[minio-init] Almacenamiento disponible.", flush=True)
            return
        except Exception as error:  # noqa: BLE001
            ultimo = _detalle(error)
            print(f"[minio-init]   ...aun no listo ({ultimo})", flush=True)
            time.sleep(INTERVALO_REINTENTO)
    raise SystemExit(
        f"[minio-init] ERROR: {ENDPOINT} no esta operativo tras {ESPERA_MAXIMA:.0f}s. "
        f"Ultimo error -> {ultimo}"
    )


def asegurar_bucket(s3) -> None:
    try:
        s3.head_bucket(Bucket=BUCKET)
        print(f"[minio-init] El bucket '{BUCKET}' ya existe.", flush=True)
        return
    except ClientError as error:
        codigo = error.response.get("Error", {}).get("Code", "")
        estado = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if codigo not in {"404", "NoSuchBucket"} and estado != 404:
            raise
    # Solo se crea si realmente no existe.
    if REGION and REGION != "us-east-1":
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": REGION},
        )
    else:
        s3.create_bucket(Bucket=BUCKET)
    print(f"[minio-init] Bucket '{BUCKET}' creado.", flush=True)


def subir_csv(s3) -> None:
    if not os.path.isfile(CSV_PATH):
        raise SystemExit(f"[minio-init] ERROR: no existe {CSV_PATH}")
    s3.upload_file(CSV_PATH, BUCKET, OBJECT_KEY)
    print(f"[minio-init] Subido {CSV_PATH} -> s3://{BUCKET}/{OBJECT_KEY}", flush=True)


def resumen(s3) -> None:
    respuesta = s3.list_objects_v2(Bucket=BUCKET)
    print(f"[minio-init] Contenido de s3://{BUCKET}/:", flush=True)
    for objeto in respuesta.get("Contents", []):
        print(f"[minio-init]   {objeto['Key']}  ({objeto['Size']} bytes)", flush=True)


def main() -> None:
    s3 = cliente()
    esperar(s3)
    asegurar_bucket(s3)
    subir_csv(s3)
    resumen(s3)
    print("[minio-init] Hecho.", flush=True)


if __name__ == "__main__":
    main()
