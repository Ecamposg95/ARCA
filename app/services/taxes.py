"""Desglose de IVA.

El usuario captura el TOTAL (lo que dice el ticket) y elige la tasa; aquí se
obtiene la base. El impuesto se calcula por DIFERENCIA, nunca recalculado:
así `subtotal + impuesto == total` es exacto y la partida doble no arrastra
centavos de deriva.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.accounting.engine import _quantize

# Tasas admitidas en México (general, frontera, tasa 0 / exento).
ALLOWED_RATES = (Decimal("0.16"), Decimal("0.08"), Decimal("0"))


@dataclass(frozen=True)
class TaxBreakdown:
    total: Decimal
    subtotal: Decimal
    tax_rate: Decimal
    tax_amount: Decimal


def split_total(total: Decimal, tax_rate: Decimal) -> TaxBreakdown:
    """Separa un total en base gravable e impuesto."""
    total = _quantize(total)
    rate = Decimal(tax_rate)
    if rate < 0 or rate > 1:
        raise ValueError("La tasa de impuesto no es válida.")
    if rate == 0:
        return TaxBreakdown(total=total, subtotal=total, tax_rate=Decimal("0"), tax_amount=Decimal("0"))
    subtotal = _quantize(total / (Decimal("1") + rate))
    return TaxBreakdown(total=total, subtotal=subtotal, tax_rate=rate, tax_amount=total - subtotal)


def proportional_tax(tax_amount: Decimal, paid: Decimal, total: Decimal, remaining_tax: Decimal) -> Decimal:
    """Impuesto que corresponde a un cobro/pago parcial.

    El último abono liquida el remanente exacto para que la cuenta de IVA
    pendiente cierre en cero, sin residuos de centavos.
    """
    tax_amount = Decimal(tax_amount)
    if tax_amount == 0:
        return Decimal("0")
    paid = Decimal(paid)
    total = Decimal(total)
    if paid >= total:
        return _quantize(remaining_tax)
    share = _quantize(tax_amount * paid / total)
    return min(share, _quantize(remaining_tax))
