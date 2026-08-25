"""Saldo corriente de una cuenta, al estilo de un estado de cuenta bancario.

Solo tiene sentido sobre UNA cuenta: acumular saldos de bancos distintos no
significa nada. Se calcula en el servidor con una función de ventana para que
la paginación no rompa el acumulado.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.financial_account import FinancialAccount
from app.models.transaction import INFLOW_TYPES, FinancialTransaction


def running_balances(
    db: Session,
    organization_id: str,
    financial_account_id: str,
    transaction_ids: list[str],
) -> dict[str, Decimal]:
    """Saldo de la cuenta DESPUÉS de cada movimiento pedido.

    Se parte del saldo actual y se descuentan los movimientos posteriores
    (la lista va del más reciente al más antiguo).
    """
    if not transaction_ids:
        return {}

    account = (
        db.query(FinancialAccount)
        .filter(
            FinancialAccount.id == financial_account_id,
            FinancialAccount.organization_id == organization_id,
        )
        .first()
    )
    if account is None:
        return {}

    signed = case(
        (FinancialTransaction.transaction_type.in_(INFLOW_TYPES), FinancialTransaction.amount),
        else_=-FinancialTransaction.amount,
    )
    # Acumulado desde el movimiento más reciente hasta cada fila, inclusive.
    cumulative = func.sum(signed).over(
        order_by=[
            FinancialTransaction.date.desc(),
            FinancialTransaction.created_at.desc(),
            FinancialTransaction.id.desc(),
        ]
    )
    rows = (
        db.query(
            FinancialTransaction.id,
            signed.label("delta"),
            cumulative.label("cumulative"),
        )
        .filter(
            FinancialTransaction.organization_id == organization_id,
            FinancialTransaction.financial_account_id == financial_account_id,
            FinancialTransaction.status == "ACTIVE",
        )
        .all()
    )

    wanted = set(transaction_ids)
    current = Decimal(account.current_balance)
    balances: dict[str, Decimal] = {}
    for row in rows:
        if row.id not in wanted:
            continue
        # Saldo tras este movimiento = saldo actual − los movimientos MÁS nuevos que él.
        newer = Decimal(row.cumulative) - Decimal(row.delta)
        balances[row.id] = current - newer
    return balances
