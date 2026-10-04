"""
Crea en Superset un DASHBOARD con 3 graficos de distinto tipo sobre el
dataset "playas_tipadas" (la vista tipada de Trino).

Graficos:
  1. Barras     -> numero de playas por zona
  2. Tarta      -> numero de playas por tipo de playa
  3. Big Number -> metros totales de playa (SUM(longitud_m))

Es idempotente: si el dashboard o los graficos ya existen (mismo nombre),
no los duplica; solo se asegura de que esten enlazados al dashboard.

Se ejecuta dentro del contenedor superset-init (o a mano con):

    docker exec bigdata-superset python /app/create_dashboard.py
"""

import json
import os
import sys
import traceback

DASHBOARD_TITLE = os.environ.get("SUPERSET_DASHBOARD_TITLE", "Playas de Asturias")
DATASET_NAME = os.environ.get("SUPERSET_TRINO_TABLE", "playas_tipadas")
SCHEMA = os.environ.get("SUPERSET_TRINO_SCHEMA", "default")


def _metric(column: str, aggregate: str = "SUM") -> dict:
    """Metrica simple de Superset (SUM/COUNT/AVG...) sobre una columna."""
    return {
        "expressionType": "SIMPLE",
        "column": {"column_name": column},
        "aggregate": aggregate,
        "label": f"{aggregate}({column})",
    }


def _get_or_create_chart(db, Slice, table, name: str, viz_type: str, params: dict):
    """Devuelve el grafico existente o lo crea. Idempotente por nombre."""
    chart = db.session.query(Slice).filter_by(slice_name=name).one_or_none()
    if chart is not None:
        print(f"[dashboard] El grafico '{name}' ya existia (id={chart.id}).")
        return chart

    chart = Slice(
        slice_name=name,
        viz_type=viz_type,
        datasource_type="table",
        datasource_id=table.id,
        datasource_name=table.table_name,
        params=json.dumps(params),
    )
    db.session.add(chart)
    db.session.commit()
    print(f"[dashboard] Grafico '{name}' creado (id={chart.id}).")
    return chart


def _build_position_json(charts) -> str:
    """Construye el layout del dashboard (position_json) con los 3 graficos.

    Se usa el formato de grid de Superset: un ROW con 3 CHART dentro.
    """
    # ids de los nodos del layout (deben ser unicos dentro del dashboard)
    row_id = "ROW-1"
    chart_ids = [f"CHART-{i}" for i in range(1, len(charts) + 1)]

    position = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {
            "type": "GRID",
            "id": "GRID_ID",
            "children": [row_id],
            "parents": ["ROOT_ID"],
        },
        row_id: {
            "type": "ROW",
            "id": row_id,
            "children": chart_ids,
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
    }

    for node_id, chart in zip(chart_ids, charts):
        position[node_id] = {
            "type": "CHART",
            "id": node_id,
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row_id],
            "meta": {
                "chartId": chart.id,
                "width": 4,
                "height": 50,
                "sliceName": chart.slice_name,
            },
        }

    return json.dumps(position)


def main() -> None:
    from superset.app import create_app

    app = create_app()

    with app.app_context():
        from superset import db
        from superset.connectors.sqla.models import SqlaTable
        from superset.models.dashboard import Dashboard
        from superset.models.slice import Slice

        table = (
            db.session.query(SqlaTable)
            .filter_by(table_name=DATASET_NAME, schema=SCHEMA)
            .one_or_none()
        )
        if table is None:
            raise RuntimeError(
                f"No existe el dataset '{SCHEMA}.{DATASET_NAME}'. "
                "Ejecuta antes bootstrap.py."
            )

        # --- 1. Grafico de BARRAS: numero de playas por zona --------------
        bar = _get_or_create_chart(
            db,
            Slice,
            table,
            name="Playas por zona (barras)",
            viz_type="echarts_timeseries_bar",
            params={
                "viz_type": "echarts_timeseries_bar",
                "datasource": f"{table.id}__table",
                "x_axis": "zona",
                "metrics": [_metric("nombre", "COUNT")],
                "groupby": [],
                "adhoc_filters": [],
                "row_limit": 10000,
                "order_desc": True,
                "show_legend": True,
                "x_axis_title": "Zona",
                "y_axis_title": "Numero de playas",
            },
        )

        # --- 2. Grafico de TARTA: playas por tipo de playa ----------------
        pie = _get_or_create_chart(
            db,
            Slice,
            table,
            name="Playas por tipo (tarta)",
            viz_type="pie",
            params={
                "viz_type": "pie",
                "datasource": f"{table.id}__table",
                "groupby": ["tipo_playa"],
                "metric": _metric("nombre", "COUNT"),
                "adhoc_filters": [],
                "row_limit": 10000,
                "show_legend": True,
                "label_type": "key_value",
                "donut": False,
            },
        )

        # --- 3. BIG NUMBER: metros totales de playa -----------------------
        big_number = _get_or_create_chart(
            db,
            Slice,
            table,
            name="Longitud total (metros)",
            viz_type="big_number_total",
            params={
                "viz_type": "big_number_total",
                "datasource": f"{table.id}__table",
                "metric": _metric("longitud_m"),
                "adhoc_filters": [],
                "subheader": "Metros totales de playa",
                "y_axis_format": "SMART_NUMBER",
            },
        )

        charts = [bar, pie, big_number]

        # --- 4. Dashboard -------------------------------------------------
        dashboard = (
            db.session.query(Dashboard)
            .filter_by(dashboard_title=DASHBOARD_TITLE)
            .one_or_none()
        )
        if dashboard is None:
            dashboard = Dashboard(
                dashboard_title=DASHBOARD_TITLE,
                slug="playas-asturias-dashboard",
                published=True,
                position_json=_build_position_json(charts),
            )
            db.session.add(dashboard)
            db.session.commit()
            print(f"[dashboard] Dashboard '{DASHBOARD_TITLE}' creado (id={dashboard.id}).")
        else:
            # Nos aseguramos de que el layout incluya los 3 graficos.
            dashboard.position_json = _build_position_json(charts)
            db.session.commit()
            print(
                f"[dashboard] El dashboard '{DASHBOARD_TITLE}' ya existia "
                f"(id={dashboard.id}); layout actualizado."
            )

        # --- 5. Enlazar graficos al dashboard (relacion N:M) --------------
        for chart in charts:
            if chart not in dashboard.slices:
                dashboard.slices.append(chart)
        db.session.commit()

        print(
            "[dashboard] Graficos en el dashboard: "
            + ", ".join(c.slice_name for c in dashboard.slices)
        )
        print(f"[dashboard] URL: /superset/dashboard/{dashboard.id}/")


if __name__ == "__main__":
    try:
        main()
        print("[dashboard] Completado.")
    except Exception:
        traceback.print_exc()
        sys.exit(1)
