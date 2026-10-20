"""Pruebas del flujo completo en modo simulado (sin API key)."""

import asyncio
import os

import pytest

os.environ["JURADO_MOCK"] = "1"

from jurado import juzgar  # noqa: E402
from jurado.agentes import JURADOS  # noqa: E402
from jurado.juicio import VOTO_CULPABLE, VOTO_INOCENTE, celebrar_juicio  # noqa: E402
from jurado.llm import extraer_json  # noqa: E402


def test_hay_doce_jurados_con_roles_distintos():
    assert len(JURADOS) == 12
    assert len({j.id for j in JURADOS}) == 12
    assert len({j.rol for j in JURADOS}) == 12


def test_extraer_json_tolera_vallas_y_texto():
    assert extraer_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extraer_json('Claro, aquí va:\n{"voto": "INOCENTE"}\nGracias') == {"voto": "INOCENTE"}
    with pytest.raises(ValueError):
        extraer_json("sin json")


def test_el_juicio_emite_todos_los_eventos_en_orden():
    async def correr():
        return [e["tipo"] async for e in celebrar_juicio("Una idea de prueba suficientemente larga.")]

    tipos = asyncio.run(correr())
    assert tipos[:3] == ["apertura", "fiscal", "defensor"]
    assert tipos.count("papeleta") == 12
    assert tipos[-3:] == ["recuento", "veredicto", "fin"]


def test_juzgar_devuelve_un_veredicto_coherente():
    juicio = asyncio.run(juzgar("Una idea de prueba suficientemente larga."))
    assert len(juicio.papeletas) == 12
    assert juicio.culpables + juicio.inocentes == 12
    assert all(p.voto in {VOTO_CULPABLE, VOTO_INOCENTE} for p in juicio.papeletas)
    assert [p.jurado_id for p in juicio.papeletas] == [j.id for j in JURADOS]
    assert juicio.veredicto is not None
    assert juicio.veredicto.decision in {"CONSTRUIR", "PIVOTAR", "ARCHIVAR"}
    assert juicio.veredicto.siguiente_paso


def test_idea_vacia_se_rechaza():
    async def correr():
        async for _ in celebrar_juicio("   "):
            pass

    with pytest.raises(ValueError):
        asyncio.run(correr())
