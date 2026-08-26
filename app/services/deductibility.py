"""Deducibilidad del gasto (LISR 27-III).

Un pago en efectivo mayor a $2,000 no es deducible. La regla no bloquea nada
—el gasto es real y hay que registrarlo— pero avisar a tiempo vale más que
enterarse en la declaración anual, cuando ya no se puede cambiar la forma de
pago.
"""

from __future__ import annotations

from decimal import Decimal

# Límite del artículo 27 fracción III de la LISR.
CASH_DEDUCTION_LIMIT = Decimal("2000")


def cash_warning(amount: Decimal, payment_method: str | None) -> str | None:
    """Aviso en lenguaje de dueño, o None si no hay nada que advertir."""
    if payment_method != "EFECTIVO":
        return None
    if Decimal(amount) <= CASH_DEDUCTION_LIMIT:
        return None
    return (
        f"Pagado en efectivo por más de ${CASH_DEDUCTION_LIMIT:,.0f}: este gasto "
        "no será deducible. Si puedes, págalo con transferencia o tarjeta."
    )


def is_deductible(amount: Decimal, payment_method: str | None) -> bool:
    return cash_warning(amount, payment_method) is None
