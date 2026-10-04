"""
Registra en Superset:
  * la conexion SQLAlchemy a Trino  (trino://admin@trino:8080/hive/default)
  * el dataset "hive.default.playas_tipadas"

Se usa la VISTA playas_tipadas, no la tabla cruda: el SerDe CSV de Hive
devuelve todas las columnas como texto, y la vista ya las convierte a
boolean / bigint. Asi Superset ve "longitud_m" como numero y puede
ofrecer la metrica SUM(longitud_m) sin escribir SQL a mano.

Es idempotente: si ya existen, no hace nada.
Se ejecuta dentro del contenedor superset-init.
"""

import os
import sys
import time
import traceback

TRINO_URI = os.environ.get(
    "TRINO_SQLALCHEMY_URI", "trino://admin@trino:8080/hive/default"
)
DB_NAME = os.environ.get("SUPERSET_TRINO_DB_NAME", "Trino (MinIO)")
SCHEMA = os.environ.get("SUPERSET_TRINO_SCHEMA", "default")
TABLE = os.environ.get("SUPERSET_TRINO_TABLE", "playas_tipadas")


def fetch_columns_with_retry(table, attempts: int = 20, delay: int = 3) -> None:
    """Lee las columnas desde Trino y las persiste, reintentando.

    Trino puede aceptar la conexion TCP y aun asi responder
    SERVER_STARTING_UP a las consultas. Reintentamos hasta que responda.
    """
    from superset import db

    last_error: Exception | None = None
    for intento in range(1, attempts + 1):
        try:
            result = table.fetch_metadata()
            db.session.commit()
            print(
                "[bootstrap] Columnas anadidas: "
                f"{result.added or 'ninguna'} | "
                f"modificadas: {result.modified or 'ninguna'} | "
                f"eliminadas: {result.removed or 'ninguna'}"
            )
            return
        except Exception as exc:  # noqa: BLE001 - queremos reintentar cualquier fallo
            last_error = exc
            db.session.rollback()
            print(
                f"[bootstrap] Intento {intento}/{attempts} de leer columnas "
                f"fallido: {exc}"
            )
            time.sleep(delay)

    raise RuntimeError(
        f"No se pudieron leer las columnas de {SCHEMA}.{TABLE} tras "
        f"{attempts} intentos"
    ) from last_error


def main() -> None:
    from superset.app import create_app

    app = create_app()

    with app.app_context():
        from superset import db
        from superset.connectors.sqla.models import SqlaTable
        from superset.models.core import Database

        # --- 1. Conexion a Trino ------------------------------------------
        database = (
            db.session.query(Database)
            .filter_by(database_name=DB_NAME)
            .one_or_none()
        )
        if database is None:
            database = Database(
                database_name=DB_NAME,
                sqlalchemy_uri=TRINO_URI,
                expose_in_sqllab=True,
            )
            db.session.add(database)
            db.session.commit()
            print(f"[bootstrap] Conexion '{DB_NAME}' creada -> {TRINO_URI}")
        else:
            print(f"[bootstrap] La conexion '{DB_NAME}' ya existia.")

        # --- 2. Dataset ---------------------------------------------------
        table = (
            db.session.query(SqlaTable)
            .filter_by(table_name=TABLE, schema=SCHEMA, database_id=database.id)
            .one_or_none()
        )
        if table is None:
            table = SqlaTable(
                table_name=TABLE,
                schema=SCHEMA,
                database=database,
            )
            db.session.add(table)
            db.session.commit()
            print(f"[bootstrap] Dataset '{SCHEMA}.{TABLE}' creado.")
        else:
            print(f"[bootstrap] El dataset '{SCHEMA}.{TABLE}' ya existia.")

        # --- 3. Columnas --------------------------------------------------
        # Se leen SIEMPRE (no solo al crear el dataset): asi se arregla un
        # dataset que se quedo sin columnas porque Trino aun no estaba listo.
        if table.columns:
            print(
                "[bootstrap] El dataset ya tiene columnas: "
                + ", ".join(column.column_name for column in table.columns)
            )
        else:
            print("[bootstrap] Leyendo columnas desde Trino ...")
            fetch_columns_with_retry(table)

        columnas = ", ".join(column.column_name for column in table.columns)
        print(f"[bootstrap] Columnas del dataset: {columnas}")


if __name__ == "__main__":
    try:
        main()
        print("[bootstrap] Completado.")
    except Exception:
        traceback.print_exc()
        sys.exit(1)
