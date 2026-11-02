"""Cliente de Anthropic: existe sólo si hay llave.

Toda la plataforma se construye y despliega sin `ANTHROPIC_API_KEY`; cuando
la llave aparece en Railway el asistente se enciende sin tocar código. La
llave se lee al construir, no al arrancar, y el import del SDK es perezoso
para que las pruebas (cliente falso) no lo necesiten.
"""

from __future__ import annotations

import os

ENV_KEY = "ANTHROPIC_API_KEY"


def api_key_present() -> bool:
    return bool(os.getenv(ENV_KEY, "").strip())


def build_client():
    """`anthropic.Anthropic()` con llave; `None` sin ella (nunca levanta)."""
    if not api_key_present():
        return None
    import anthropic

    return anthropic.Anthropic()
