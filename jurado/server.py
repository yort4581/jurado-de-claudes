"""Servidor web: sirve la sala de juicio y transmite el juicio por SSE.

    uvicorn jurado.server:app --reload

Rutas:
    GET  /                 → interfaz web (web/index.html)
    POST /api/juicio       → {"idea": "..."}; responde un flujo
                             text/event-stream con un evento por agente.
    GET  /api/salud        → estado y modo (real o simulado).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import llm
from .juicio import celebrar_juicio

load_dotenv()

RAIZ = Path(__file__).resolve().parent.parent
WEB = RAIZ / "web"
MAX_CARACTERES = int(os.getenv("JURADO_MAX_CARACTERES", "4000"))

app = FastAPI(title="Jurado de Claudes", version="0.1.0")


class Caso(BaseModel):
    idea: str = Field(min_length=10, max_length=MAX_CARACTERES)


@app.get("/")
async def inicio() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/api/salud")
async def salud() -> dict:
    return {
        "ok": True,
        "modo": "simulado" if llm.modo_mock() else "real",
        "modelo_principal": llm.MODELO_PRINCIPAL,
        "modelo_jurado": llm.MODELO_JURADO,
        "api_key_configurada": bool(os.getenv("ANTHROPIC_API_KEY")),
    }


@app.post("/api/juicio")
async def juicio(caso: Caso) -> StreamingResponse:
    if not llm.modo_mock() and not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="Falta ANTHROPIC_API_KEY. Añádela al archivo .env o usa JURADO_MOCK=1.",
        )

    async def flujo():
        try:
            async for evento in celebrar_juicio(caso.idea):
                yield f"event: {evento['tipo']}\ndata: {json.dumps(evento, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001 - se lo contamos al navegador
            yield f"event: error\ndata: {json.dumps({'mensaje': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        flujo(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
