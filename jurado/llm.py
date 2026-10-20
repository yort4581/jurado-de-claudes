"""Capa fina sobre la API de Claude.

Expone una sola función asíncrona, ``preguntar``, que recibe un prompt de
sistema y un mensaje de usuario y devuelve el texto de la respuesta.

Si la variable de entorno ``JURADO_MOCK=1`` está activa, no se llama a la
API: se devuelven respuestas simuladas (con algo de azar) para poder
desarrollar la interfaz, probar el flujo o hacer una demo sin gastar
tokens.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
from typing import Any

MODELO_PRINCIPAL = os.getenv("JURADO_MODELO_PRINCIPAL", "claude-sonnet-5-5")
MODELO_JURADO = os.getenv("JURADO_MODELO_JURADO", "claude-haiku-5-5")
MAX_PARALELO = int(os.getenv("JURADO_MAX_PARALELO", "6"))

_semaforo: asyncio.Semaphore | None = None
_cliente: Any = None


def modo_mock() -> bool:
    return os.getenv("JURADO_MOCK", "").strip() in {"1", "true", "yes"}


def _semaforo_global() -> asyncio.Semaphore:
    global _semaforo
    if _semaforo is None:
        _semaforo = asyncio.Semaphore(MAX_PARALELO)
    return _semaforo


def _cliente_global() -> Any:
    global _cliente
    if _cliente is None:
        from anthropic import AsyncAnthropic  # import perezoso: el mock no lo necesita

        _cliente = AsyncAnthropic()
    return _cliente


async def preguntar(
    sistema: str,
    usuario: str,
    *,
    modelo: str | None = None,
    max_tokens: int = 900,
    temperatura: float = 0.8,
) -> str:
    """Envía un mensaje a Claude y devuelve el texto de la respuesta."""
    if modo_mock():
        return await _respuesta_mock(sistema, usuario)

    cliente = _cliente_global()
    async with _semaforo_global():
        respuesta = await cliente.messages.create(
            model=modelo or MODELO_PRINCIPAL,
            max_tokens=max_tokens,
            temperature=temperatura,
            system=sistema,
            messages=[{"role": "user", "content": usuario}],
        )
    partes = [b.text for b in respuesta.content if getattr(b, "type", "") == "text"]
    return "".join(partes).strip()


def extraer_json(texto: str) -> dict[str, Any]:
    """Saca el primer objeto JSON de un texto, tolerando vallas de código."""
    limpio = texto.strip()
    limpio = re.sub(r"^```(?:json)?\s*|\s*```$", "", limpio, flags=re.S)
    try:
        return json.loads(limpio)
    except json.JSONDecodeError:
        pass
    inicio, fin = limpio.find("{"), limpio.rfind("}")
    if inicio != -1 and fin > inicio:
        return json.loads(limpio[inicio : fin + 1])
    raise ValueError(f"La respuesta no contiene JSON: {texto[:200]!r}")


# --------------------------------------------------------------------------
# Modo simulado
# --------------------------------------------------------------------------

_ARGUMENTOS_CULPABLE = [
    "Desde mi rol veo el mismo patrón de siempre: una solución buscando un problema. "
    "Nadie ha demostrado que alguien pague por esto.",
    "El coste de conseguir cada cliente se come el margen antes del segundo año. "
    "Los números no cierran tal como está planteado.",
    "Cualquier actor establecido puede copiar esto en un trimestre y con más "
    "distribución. No hay nada que proteja la idea.",
]
_ARGUMENTOS_INOCENTE = [
    "Hay un dolor real y mal atendido. Con reservas, creo que merece una "
    "versión mínima para comprobarlo con clientes de verdad.",
    "La idea es sencilla de explicar y de probar; eso ya la pone por delante "
    "de la mayoría. El riesgo es acotado.",
    "El momento es bueno: el sector acaba de cambiar y los grandes van lentos. "
    "Merece construirse, aunque con un alcance más estrecho.",
]
_PREGUNTAS = [
    "¿Cuántas personas te han dicho que pagarían, y cuántas han pagado?",
    "¿Qué hace hoy tu cliente para resolver esto sin ti?",
    "¿Qué pasa si vendes la mitad de lo previsto el primer año?",
    "¿Por qué no lo ha hecho ya el líder del mercado?",
]


async def _respuesta_mock(sistema: str, usuario: str) -> str:
    await asyncio.sleep(random.uniform(0.6, 2.2))
    if sistema.startswith("Eres el FISCAL"):
        return (
            "Señorías, lo que se nos presenta es una idea seductora y, "
            "precisamente por eso, peligrosa. El fundador asume que el "
            "problema es urgente para su cliente, pero no aporta una sola "
            "evidencia de que alguien haya pagado por resolverlo.\n\n"
            "Segundo: el mercado ya castigó propuestas parecidas. Las que "
            "sobrevivieron lo hicieron con distribución, no con producto, y "
            "aquí no se menciona ningún canal.\n\n"
            "Tercero: los costes ocultos. Soporte, cumplimiento normativo y "
            "mantenimiento aparecen después de la demo y matan el margen.\n\n"
            "Cargo principal: enamorarse de la solución sin haber validado "
            "que el problema duele lo suficiente como para pagar."
        )
    if sistema.startswith("Eres el ABOGADO DEFENSOR"):
        return (
            "Señorías, la fiscalía confunde ausencia de pruebas con prueba de "
            "ausencia. La idea ataca una fricción que cualquiera de ustedes "
            "ha sufrido, y lo hace con un alcance lo bastante estrecho como "
            "para probarse en semanas, no en años.\n\n"
            "Que existan competidores demuestra que hay mercado. Lo que mi "
            "cliente propone no es inventar la categoría, sino servir al "
            "segmento que los grandes ignoran porque les resulta pequeño.\n\n"
            "Y los costes ocultos existen en cualquier negocio: lo relevante "
            "es que aquí pueden medirse pronto y con poco dinero.\n\n"
            "Argumento central: un problema conocido, un segmento desatendido "
            "y una forma barata de comprobar si pagan."
        )
    if sistema.startswith("Eres el JUEZ"):
        m = re.search(r"INOCENTE:\s*(\d+)", usuario)
        inocentes = int(m.group(1)) if m else 6
        if inocentes >= 8:
            decision = "CONSTRUIR"
        elif inocentes <= 4:
            decision = "ARCHIVAR"
        else:
            decision = "PIVOTAR"
        return json.dumps(
            {
                "decision": decision,
                "veredicto": (
                    f"Este tribunal ha escuchado a las dos partes y ha contado "
                    f"{inocentes} papeletas de inocencia de doce. El jurado "
                    "coincide en que el problema existe; lo que divide a la "
                    "sala es si alguien pagará por resolverlo así. La decisión "
                    f"es {decision.lower()}."
                ),
                "lo_que_convence": [
                    "El problema es reconocible y fácil de explicar.",
                    "Se puede probar una versión mínima con poco dinero.",
                ],
                "lo_que_preocupa": [
                    "No hay evidencia de disposición a pagar.",
                    "Falta un canal de distribución claro.",
                    "Los costes de soporte y cumplimiento no se han estimado.",
                ],
                "siguiente_paso": (
                    "Habla con diez clientes potenciales esta semana y pide a "
                    "cinco de ellos una reserva de pago, aunque sea simbólica."
                ),
            },
            ensure_ascii=False,
        )
    # Jurado
    inocente = random.random() < 0.55
    return json.dumps(
        {
            "voto": "INOCENTE" if inocente else "CULPABLE",
            "confianza": random.randint(2, 5),
            "argumento": random.choice(
                _ARGUMENTOS_INOCENTE if inocente else _ARGUMENTOS_CULPABLE
            ),
            "pregunta": random.choice(_PREGUNTAS),
        },
        ensure_ascii=False,
    )
