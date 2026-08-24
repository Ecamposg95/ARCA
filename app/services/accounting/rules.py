"""Motor de reglas contables (task pack §18) — centralizado.

Cada evento de negocio tiene UNA función aquí que construye su póliza.
Prohibido armar asientos en routers o en el frontend.
"""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.accounting import JournalEntry
from app.services.accounting.coa import CODE_CAPITAL, CODE_CASH_BANK
from app.services.accounting.engine import LineSpec, post_journal_entry


def opening_balance_entry(
    db: Session,
    organization_id: str,
    account_name: str,
    amount: Decimal,
    date: date_type,
    source_id: str,
    created_by: str | None = None,
) -> JournalEntry:
    """Alta de cuenta con saldo inicial: Cargo Caja y Bancos / Abono Capital."""
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=f"Saldo inicial de {account_name}",
        lines=[
            LineSpec(CODE_CASH_BANK, debit=amount, description=account_name),
            LineSpec(CODE_CAPITAL, credit=amount, description="Aportación inicial"),
        ],
        source_type="financial_account",
        source_id=source_id,
        created_by=created_by,
    )


def income_paid_entry(
    db: Session,
    organization_id: str,
    description: str,
    amount: Decimal,
    date: date_type,
    revenue_account_code: str,
    source_id: str,
    created_by: str | None = None,
) -> JournalEntry:
    """Ingreso pagado: Cargo Caja y Bancos / Abono Ingresos."""
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=[
            LineSpec(CODE_CASH_BANK, debit=amount),
            LineSpec(revenue_account_code, credit=amount),
        ],
        source_type="income",
        source_id=source_id,
        created_by=created_by,
    )


def expense_paid_entry(
    db: Session,
    organization_id: str,
    description: str,
    amount: Decimal,
    date: date_type,
    expense_account_code: str,
    source_id: str,
    created_by: str | None = None,
) -> JournalEntry:
    """Gasto pagado: Cargo Gastos / Abono Caja y Bancos."""
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=[
            LineSpec(expense_account_code, debit=amount),
            LineSpec(CODE_CASH_BANK, credit=amount),
        ],
        source_type="expense",
        source_id=source_id,
        created_by=created_by,
    )


def transfer_entry(
    db: Session,
    organization_id: str,
    description: str,
    amount: Decimal,
    date: date_type,
    from_account_name: str,
    to_account_name: str,
    source_id: str,
    created_by: str | None = None,
) -> JournalEntry:
    """Traspaso entre cuentas propias: neutro en 1100, se registra para auditoría."""
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=[
            LineSpec(CODE_CASH_BANK, debit=amount, description=f"Entrada a {to_account_name}"),
            LineSpec(CODE_CASH_BANK, credit=amount, description=f"Salida de {from_account_name}"),
        ],
        source_type="transfer",
        source_id=source_id,
        created_by=created_by,
    )
