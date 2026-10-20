"""Orquestación del juicio.

``celebrar_juicio(idea)`` es un generador asíncrono que va emitiendo eventos
a medida que los agentes terminan, de forma que la interfaz (web o CLI)
pueda mostrar el proceso en directo:

1. ``apertura``      – el tribunal recibe la idea.
2. ``fiscal``        – alegato en contra.
3. ``defensor``      – alegato a favor.
4. ``papeleta``      – (x12) cada jurado deposita su voto secreto. Se emite
                       en cuanto cada uno termina; votan todos en paralelo.
5. ``recuento``      – todas las papeletas están dentro: votos totales.
6. ``veredicto``     – el juez lee la decisión final.
7. ``fin``           – resumen completo del juicio.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from typing import Any, AsyncIterator

from . import llm
from .agentes import (
    JURADOS,
    SISTEMA_DEFENSOR,
    SISTEMA_FISCAL,
    SISTEMA_JUEZ,
    Jurado,
    sistema_jurado,
)

VOTO_CULPABLE = "CULPABLE"
VOTO_INOCENTE = "INOCENTE"


@dataclass
class Papeleta:
    jurado_id: str
    nombre: str
    rol: str
    emoji: str
    voto: str
    confianza: int
    argumento: str
    pregunta: str


@dataclass
class Veredicto:
    decision: str
    veredicto: str
    lo_que_convence: list[str]
    lo_que_preocupa: list[str]
    siguiente_paso: str


@dataclass
class Juicio:
    idea: str
    fiscal: str = ""
    defensor: str = ""
    papeletas: list[Papeleta] = field(default_factory=list)
    veredicto: Veredicto | None = None

    @property
    def culpables(self) -> int:
        return sum(1 for p in self.papeletas if p.voto == VOTO_CULPABLE)

    @property
    def inocentes(self) -> int:
        return sum(1 for p in self.papeletas if p.voto == VOTO_INOCENTE)

    def a_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["culpables"] = self.culpables
        d["inocentes"] = self.inocentes
        return d


# --------------------------------------------------------------------------
# Agentes individuales
# --------------------------------------------------------------------------


async def alegato_fiscal(idea: str) -> str:
    return await llm.preguntar(
        SISTEMA_FISCAL, f"La idea que se juzga es la siguiente:\n\n{idea}"
    )


async def alegato_defensor(idea: str) -> str:
    return await llm.preguntar(
        SISTEMA_DEFENSOR, f"La idea que se juzga es la siguiente:\n\n{idea}"
    )


def _normalizar_voto(valor: Any) -> str:
    v = str(valor or "").strip().upper()
    if v.startswith("INOC") or v in {"NOT GUILTY", "NO CULPABLE"}:
        return VOTO_INOCENTE
    return VOTO_CULPABLE


async def votar(j: Jurado, idea: str, fiscal: str, defensor: str) -> Papeleta:
    usuario = (
        f"IDEA A JUICIO:\n{idea}\n\n"
        f"ALEGATO DEL FISCAL (en contra):\n{fiscal}\n\n"
        f"ALEGATO DEL DEFENSOR (a favor):\n{defensor}\n\n"
        "Emite ahora tu papeleta secreta en JSON."
    )
    texto = await llm.preguntar(
        sistema_jurado(j), usuario, modelo=llm.MODELO_JURADO, max_tokens=500
    )
    try:
        datos = llm.extraer_json(texto)
    except (ValueError, Exception):
        # Un jurado que no sabe rellenar la papeleta: la contamos como
        # abstención conservadora (CULPABLE) y guardamos lo que dijo.
        datos = {"voto": VOTO_CULPABLE, "confianza": 1, "argumento": texto[:400], "pregunta": ""}
    try:
        confianza = max(1, min(5, int(datos.get("confianza", 3))))
    except (TypeError, ValueError):
        confianza = 3
    return Papeleta(
        jurado_id=j.id,
        nombre=j.nombre,
        rol=j.rol,
        emoji=j.emoji,
        voto=_normalizar_voto(datos.get("voto")),
        confianza=confianza,
        argumento=str(datos.get("argumento", "")).strip(),
        pregunta=str(datos.get("pregunta", "")).strip(),
    )


async def dictar_veredicto(juicio: Juicio) -> Veredicto:
    papeletas = "\n".join(
        f"- {p.nombre} ({p.rol}) votó {p.voto} (confianza {p.confianza}/5): "
        f"{p.argumento} Pregunta: {p.pregunta}"
        for p in juicio.papeletas
    )
    usuario = (
        f"IDEA A JUICIO:\n{juicio.idea}\n\n"
        f"ALEGATO DEL FISCAL:\n{juicio.fiscal}\n\n"
        f"ALEGATO DEL DEFENSOR:\n{juicio.defensor}\n\n"
        f"RECUENTO: INOCENTE: {juicio.inocentes} · CULPABLE: {juicio.culpables}\n\n"
        f"PAPELETAS:\n{papeletas}\n\n"
        "Lee ahora el veredicto en JSON."
    )
    texto = await llm.preguntar(SISTEMA_JUEZ, usuario, max_tokens=1100, temperatura=0.5)
    datos = llm.extraer_json(texto)
    decision = str(datos.get("decision", "")).strip().upper()
    if decision not in {"CONSTRUIR", "PIVOTAR", "ARCHIVAR"}:
        decision = (
            "CONSTRUIR" if juicio.inocentes >= 8 else "ARCHIVAR" if juicio.culpables >= 8 else "PIVOTAR"
        )
    return Veredicto(
        decision=decision,
        veredicto=str(datos.get("veredicto", "")).strip(),
        lo_que_convence=[str(x) for x in datos.get("lo_que_convence", [])][:4],
        lo_que_preocupa=[str(x) for x in datos.get("lo_que_preocupa", [])][:4],
        siguiente_paso=str(datos.get("siguiente_paso", "")).strip(),
    )


# --------------------------------------------------------------------------
# El juicio completo, como flujo de eventos
# --------------------------------------------------------------------------


async def celebrar_juicio(idea: str) -> AsyncIterator[dict[str, Any]]:
    idea = idea.strip()
    if not idea:
        raise ValueError("El tribunal necesita una idea que juzgar.")

    juicio = Juicio(idea=idea)
    yield {"tipo": "apertura", "idea": idea, "jurados": [asdict(j) for j in JURADOS]}

    # Fiscal y defensor preparan sus alegatos a la vez.
    tarea_fiscal = asyncio.create_task(alegato_fiscal(idea))
    tarea_defensor = asyncio.create_task(alegato_defensor(idea))
    juicio.fiscal = await tarea_fiscal
    yield {"tipo": "fiscal", "texto": juicio.fiscal}
    juicio.defensor = await tarea_defensor
    yield {"tipo": "defensor", "texto": juicio.defensor}

    # Los 12 jurados deliberan en paralelo y en secreto.
    tareas = [
        asyncio.create_task(votar(j, idea, juicio.fiscal, juicio.defensor))
        for j in JURADOS
    ]
    for tarea in asyncio.as_completed(tareas):
        papeleta = await tarea
        juicio.papeletas.append(papeleta)
        yield {"tipo": "papeleta", "papeleta": asdict(papeleta)}

    # Se abren las urnas: reordenamos en el orden original del jurado.
    orden = {j.id: i for i, j in enumerate(JURADOS)}
    juicio.papeletas.sort(key=lambda p: orden[p.jurado_id])
    yield {
        "tipo": "recuento",
        "culpables": juicio.culpables,
        "inocentes": juicio.inocentes,
        "papeletas": [asdict(p) for p in juicio.papeletas],
    }

    juicio.veredicto = await dictar_veredicto(juicio)
    yield {"tipo": "veredicto", **asdict(juicio.veredicto)}
    yield {"tipo": "fin", "juicio": juicio.a_dict()}


async def juzgar(idea: str) -> Juicio:
    """Versión sin streaming: celebra el juicio y devuelve el resultado."""
    resultado: Juicio | None = None
    async for evento in celebrar_juicio(idea):
        if evento["tipo"] == "fin":
            j = evento["juicio"]
            resultado = Juicio(
                idea=j["idea"],
                fiscal=j["fiscal"],
                defensor=j["defensor"],
                papeletas=[Papeleta(**p) for p in j["papeletas"]],
                veredicto=Veredicto(**j["veredicto"]) if j["veredicto"] else None,
            )
    assert resultado is not None
    return resultado
