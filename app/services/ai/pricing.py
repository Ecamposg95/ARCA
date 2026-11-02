"""Precios del API de Claude en USD por millón de tokens (spec 2026-11-02 §Costo).

La tabla se usa para cobrar cada llamada al API contra el presupuesto mensual
de la empresa. Un modelo desconocido cobra como Opus: equivocarse hacia
arriba protege el presupuesto; hacia abajo lo agotaría sin avisar.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

MILLION = Decimal("1000000")


@dataclass(frozen=True)
class ModelPrice:
    input: Decimal
    output: Decimal
    cache_read: Decimal
    cache_write: Decimal


def _price(input: str, output: str, cache_read: str, cache_write: str) -> ModelPrice:
    return ModelPrice(Decimal(input), Decimal(output), Decimal(cache_read), Decimal(cache_write))


PRICES: dict[str, ModelPrice] = {
    "claude-opus-5-5": _price("4", "20", "0.20", "5"),
    "claude-sonnet-5-5": _price("2", "10", "0.20", "2.5"),
    "claude-haiku-5-5": _price("0.10", "0.50", "0.01", "0.125"),
}

# Si `AI_MODEL` apunta a otra versión de la misma familia ("claude-sonnet-5"),
# se cobra con la tarifa de la familia; cualquier otra cosa, como Opus.
_FAMILIES = (("claude-opus", "claude-opus-5-5"), ("claude-sonnet", "claude-sonnet-5-5"), ("claude-haiku", "claude-haiku-5-5"))
DEFAULT_MODEL_PRICE = "claude-opus-5-5"


def price_for(model: str | None) -> ModelPrice:
    model = model or ""
    if model in PRICES:
        return PRICES[model]
    for prefix, key in _FAMILIES:
        if model.startswith(prefix):
            return PRICES[key]
    return PRICES[DEFAULT_MODEL_PRICE]


def _tokens(usage: Any, *names: str) -> int:
    """`usage` es el objeto del SDK, un SimpleNamespace de prueba o un dict."""
    for name in names:
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        if value:
            return int(value)
    return 0


def usage_tokens(usage: Any) -> dict[str, int]:
    return {
        "input_tokens": _tokens(usage, "input_tokens"),
        "output_tokens": _tokens(usage, "output_tokens"),
        "cache_read_tokens": _tokens(usage, "cache_read_input_tokens", "cache_read_tokens"),
        "cache_write_tokens": _tokens(usage, "cache_creation_input_tokens", "cache_write_tokens"),
    }


def cost_usd(model: str | None, usage: Any) -> Decimal:
    """Costo de UNA llamada, en USD con seis decimales (Numeric(10,6))."""
    price = price_for(model)
    tokens = usage_tokens(usage)
    total = (
        Decimal(tokens["input_tokens"]) * price.input
        + Decimal(tokens["output_tokens"]) * price.output
        + Decimal(tokens["cache_read_tokens"]) * price.cache_read
        + Decimal(tokens["cache_write_tokens"]) * price.cache_write
    ) / MILLION
    return total.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
