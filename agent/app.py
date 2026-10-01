"""
Agente web (bonus): convierte una conversacion en un docker-compose.yml,
lo valida con Docker y produce un pequeno informe.

Arranque:
    cd agent
    pip install -r requirements.txt
    uvicorn app:app --reload --port 8000
Luego abre http://localhost:8000
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import generator

app = FastAPI(title="Agente docker-compose", version="1.0.0")

DIR_ACTUAL = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(DIR_ACTUAL, "static")

# El compose generado se escribe en la raiz del repositorio para que las
# rutas relativas (./trino/catalog, ./superset, ./data) resuelvan bien.
COMPOSE_GENERADO = os.path.join(generator.REPO_ROOT, "agent-generated-compose.yml")
INFORME_GENERADO = os.path.join(generator.REPO_ROOT, "agent-generated-report.md")


class Peticion(BaseModel):
    prompt: str


class ConYaml(BaseModel):
    yaml: str


class ConYamlTimeout(BaseModel):
    yaml: str
    timeout: int = 600


def _guardar(yaml_text: str) -> None:
    with open(COMPOSE_GENERADO, "w", encoding="utf-8") as fichero:
        fichero.write(yaml_text)


@app.get("/")
def raiz() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/ejemplos")
def ejemplos() -> JSONResponse:
    return JSONResponse(
        {
            "ejemplos": [
                "Monta el stack completo de big data",
                "Quiero MinIO y Trino para leer CSV",
                "Solo Superset con PostgreSQL",
                "Stack completo pero sin Superset",
                "Dame MinIO en el puerto 9100 y Trino en el 8181",
            ]
        }
    )


@app.post("/api/generate")
def api_generate(peticion: Peticion) -> JSONResponse:
    resultado = generator.generate(peticion.prompt)
    _guardar(resultado["yaml"])

    validacion = generator.validate(COMPOSE_GENERADO)
    informe = generator.build_report(resultado["ctx"], resultado["yaml"], validacion)

    with open(INFORME_GENERADO, "w", encoding="utf-8") as fichero:
        fichero.write(informe)

    return JSONResponse(
        {
            "yaml": resultado["yaml"],
            "informe": informe,
            "validacion": validacion,
            "fichero": COMPOSE_GENERADO,
        }
    )


@app.post("/api/validate")
def api_validate(datos: ConYaml) -> JSONResponse:
    _guardar(datos.yaml)
    return JSONResponse(generator.validate(COMPOSE_GENERADO))


@app.post("/api/test")
def api_test(datos: ConYamlTimeout) -> JSONResponse:
    _guardar(datos.yaml)
    return JSONResponse(generator.run_test(COMPOSE_GENERADO, timeout=datos.timeout))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
