"""
Registra en Superset:
  * la conexion SQLAlchemy a Trino  (trino://admin@trino:8080/hive/default)
  * el dataset "hive.default.ventas_tipadas"

Se usa la VISTA ventas_tipadas, no la tabla cruda: el SerDe CSV de Hive
devuelve todas las columnas como texto, y la vista ya las convierte a
date / bigint / double. Asi Superset ve "importe" como numero y puede
ofrecer la metrica SUM(importe) sin escribir SQL a mano.

Es idempotente: si ya existen, no hace nada.
Se ejecuta dentro del contenedor superset-init.
"""

import os
import sys
import traceback

TRINO_URI = os.environ.get(
    "TRINO_SQLALCHEMY_URI", "trino://admin@trino:8080/hive/default"
)
DB_NAME = os.environ.get("SUPERSET_TRINO_DB_NAME", "Trino (MinIO)")
SCHEMA = os.environ.get("SUPERSET_TRINO_SCHEMA", "default")
TABLE = os.environ.get("SUPERSET_TRINO_TABLE", "ventas_tipadas")


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
            print("[bootstrap] Leyendo columnas desde Trino ...")
            table.fetch_metadata()
            db.session.commit()

        columnas = ", ".join(column.column_name for column in table.columns)
        print(f"[bootstrap] Columnas del dataset: {columnas}")


if __name__ == "__main__":
    try:
        main()
        print("[bootstrap] Completado.")
    except Exception:
        traceback.print_exc()
        sys.exit(1)
