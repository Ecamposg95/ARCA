"""Semáforo de la cartera: qué tan urgente es voltear a ver una empresa.

Es una función pura a propósito: recibe los datos y la fecha, y no toca la base.
Así la regla del día 17 se prueba sin esperar al día 17.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

STATUS_RED = "red"
STATUS_AMBER = "amber"
STATUS_GREEN = "green"
# Orden de la cartera: lo urgente arriba.
STATUS_ORDER = {STATUS_RED: 0, STATUS_AMBER: 1, STATUS_GREEN: 2}

# Las declaraciones mensuales se presentan a más tardar el 17: pasado ese día,
# un mes sin cerrar ya no es un pendiente, es un retraso.
CLOSE_DEADLINE_DAY = 17

_MONTHS = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)  # fmt: skip


def previous_month(today: date) -> tuple[int, int]:
    index = today.year * 12 + (today.month - 1) - 1
    year, month = divmod(index, 12)
    return year, month + 1


def portfolio_status(
    *,
    today: date,
    previous_month_active: bool,
    previous_month_closed: bool,
    payable_overdue: Decimal,
    pending_proposals: int,
) -> tuple[str, list[str]]:
    """Color y TODAS las causas que aplican, no sólo la que decidió el color."""
    # Un mes sin pólizas no tiene nada que cerrar.
    close_pending = previous_month_active and not previous_month_closed

    reasons: list[str] = []
    if close_pending:
        _year, month = previous_month(today)
        reasons.append(f"{_MONTHS[month - 1]} sigue sin cerrar")
    if payable_overdue > 0:
        reasons.append(f"${payable_overdue:,.2f} por pagar vencidos")
    if pending_proposals == 1:
        reasons.append("1 propuesta por revisar")
    elif pending_proposals > 1:
        reasons.append(f"{pending_proposals} propuestas por revisar")

    if (close_pending and today.day > CLOSE_DEADLINE_DAY) or payable_overdue > 0:
        return STATUS_RED, reasons
    if close_pending or pending_proposals > 0:
        return STATUS_AMBER, reasons
    return STATUS_GREEN, reasons
