"""Payloads de las propuestas que nacen de la autorización por monto.

Para INCOME/EXPENSE/RECEIVABLE/PAYABLE/TRANSFER el payload es exactamente el
schema Create del dominio. Pagar algo que ya existe necesita además saber qué:
el id viaja dentro del payload y se re-valida al aprobar.
"""

from __future__ import annotations

from app.domains.expenses.schemas import ExpensePay
from app.domains.payables.schemas import PaymentCreate


class ExpensePaymentPayload(ExpensePay):
    expense_id: str


class PayablePaymentPayload(PaymentCreate):
    payable_id: str
