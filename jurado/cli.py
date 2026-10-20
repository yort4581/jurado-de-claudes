"""Juicio desde la terminal.

    python -m jurado "Una app que..."
    python -m jurado            # pide la idea de forma interactiva
    python -m jurado --json "…" # imprime solo el resultado en JSON
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import textwrap

from dotenv import load_dotenv

from .juicio import VOTO_INOCENTE, celebrar_juicio

ROJO, VERDE, AMARILLO, GRIS, NEGRITA, FIN = (
    "\033[31m", "\033[32m", "\033[33m", "\033[90m", "\033[1m", "\033[0m",
)


def _ancho() -> int:
    return min(shutil.get_terminal_size((88, 24)).columns, 88)


def _parrafo(texto: str, sangria: str = "  ") -> str:
    return "\n".join(
        textwrap.fill(p, width=_ancho(), initial_indent=sangria, subsequent_indent=sangria)
        for p in texto.split("\n")
        if p.strip()
    )


def _titulo(texto: str) -> None:
    print(f"\n{NEGRITA}{texto}{FIN}")
    print(GRIS + "─" * _ancho() + FIN)


async def _ejecutar(idea: str, solo_json: bool) -> int:
    resultado = None
    async for ev in celebrar_juicio(idea):
        t = ev["tipo"]
        if solo_json:
            if t == "fin":
                resultado = ev["juicio"]
            continue
        if t == "apertura":
            _titulo("🏛️  Se abre la sesión. Idea a juicio:")
            print(_parrafo(ev["idea"]))
            print(f"\n{GRIS}El fiscal y la defensa preparan sus alegatos…{FIN}")
        elif t == "fiscal":
            _titulo(f"{ROJO}⚔️  El fiscal, en contra{FIN}")
            print(_parrafo(ev["texto"]))
        elif t == "defensor":
            _titulo(f"{VERDE}🛡️  La defensa, a favor{FIN}")
            print(_parrafo(ev["texto"]))
            print(f"\n{GRIS}Los 12 jurados deliberan en secreto…{FIN}")
        elif t == "papeleta":
            p = ev["papeleta"]
            print(f"  {GRIS}🗳️  {p['emoji']} {p['nombre']} ha depositado su papeleta.{FIN}")
        elif t == "recuento":
            _titulo("📦  Se abren las urnas")
            for p in ev["papeletas"]:
                color = VERDE if p["voto"] == VOTO_INOCENTE else ROJO
                print(
                    f"  {p['emoji']} {NEGRITA}{p['nombre']}{FIN} ({p['rol']}) → "
                    f"{color}{p['voto']}{FIN} {GRIS}{'●' * p['confianza']}{'○' * (5 - p['confianza'])}{FIN}"
                )
                print(_parrafo(p["argumento"], sangria="      "))
                if p["pregunta"]:
                    print(_parrafo(f"❓ {p['pregunta']}", sangria="      "))
            print(
                f"\n  Recuento: {VERDE}{NEGRITA}INOCENTE {ev['inocentes']}{FIN}  ·  "
                f"{ROJO}{NEGRITA}CULPABLE {ev['culpables']}{FIN}"
            )
            print(f"\n{GRIS}El juez redacta el veredicto…{FIN}")
        elif t == "veredicto":
            color = {"CONSTRUIR": VERDE, "PIVOTAR": AMARILLO, "ARCHIVAR": ROJO}[ev["decision"]]
            _titulo(f"👨‍⚖️  Veredicto: {color}{ev['decision']}{FIN}")
            print(_parrafo(ev["veredicto"]))
            if ev["lo_que_convence"]:
                print(f"\n  {VERDE}Lo que convence al jurado:{FIN}")
                for x in ev["lo_que_convence"]:
                    print(_parrafo(f"✔ {x}", sangria="    "))
            if ev["lo_que_preocupa"]:
                print(f"\n  {ROJO}Lo que preocupa al jurado:{FIN}")
                for x in ev["lo_que_preocupa"]:
                    print(_parrafo(f"✘ {x}", sangria="    "))
            print(f"\n  {NEGRITA}Siguiente paso esta semana:{FIN}")
            print(_parrafo(ev["siguiente_paso"], sangria="    "))
            print()
    if solo_json and resultado is not None:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="jurado", description="12 Claudes ponen tu idea a juicio."
    )
    parser.add_argument("idea", nargs="?", help="La idea a juzgar (si falta, se pide por teclado).")
    parser.add_argument("--json", action="store_true", help="Imprimir solo el resultado en JSON.")
    args = parser.parse_args(argv)

    idea = args.idea
    if not idea:
        if not sys.stdin.isatty():
            idea = sys.stdin.read()
        else:
            print("Describe tu idea (termina con una línea vacía):")
            lineas: list[str] = []
            while True:
                try:
                    linea = input()
                except EOFError:
                    break
                if not linea.strip():
                    break
                lineas.append(linea)
            idea = "\n".join(lineas)
    if not idea or not idea.strip():
        parser.error("hace falta una idea que juzgar.")
    try:
        return asyncio.run(_ejecutar(idea, args.json))
    except KeyboardInterrupt:
        print("\nSe levanta la sesión.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
