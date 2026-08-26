"""Reversos: la única forma correcta de deshacer contabilidad.

No se borra ni se edita nada. Se emite la póliza espejo y el movimiento de
dinero inverso, de modo que el libro conserve la historia completa: lo que pasó
y lo que se corrigió. Un auditor puede ver ambas.
"""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.accounting import JournalEntry
from app.models.transaction import FinancialTransaction
from app.services.accounting.rules import reversal_of
from app.services.transactions import record_transaction

# Qué movimiento deshace a cuál. Un reverso no es un gasto ni un ingreso.
OPPOSITE_TYPE = {
    "INCOME": "REVERSAL_OUT",
    "RECEIVABLE_COLLECTION": "REVERSAL_OUT",
    "TRANSFER_IN": "REVERSAL_OUT",
    "EXPENSE": "REVERSAL_IN",
    "PAYABLE_PAYMENT": "REVERSAL_IN",
    "TRANSFER_OUT": "REVERSAL_IN",
    "ADJUSTMENT": "REVERSAL_IN",
}


def already_reversed(db: Session, organization_id: str, source_type: str, source_id: str) -> bool:
    return (
        db.query(JournalEntry)
        .filter(
            JournalEntry.organization_id == organization_id,
            JournalEntry.source_type == source_type,
            JournalEntry.source_id == source_id,
            JournalEntry.reference.like("reversal:%"),
        )
        .first()
        is not None
    )


def reverse_operation(
    db: Session,
    organization_id: str,
    *,
    source_type: str,
    source_id: str,
    description: str,
    date: date_type,
    user_id: str | None = None,
) -> dict:
    """Revierte todas las pólizas y movimientos de una operación.

    Devuelve cuántos asientos y movimientos se emitieron. No hace commit: el
    caller decide cuándo cerrar la transacción.
    """
    if already_reversed(db, organization_id, source_type, source_id):
        raise ValueError("Esta operación ya fue revertida.")

    entries = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.organization_id == organization_id,
            JournalEntry.source_type == source_type,
            JournalEntry.source_id == source_id,
            JournalEntry.status == "POSTED",
        )
        .order_by(JournalEntry.date)
        .all()
    )
    for entry in entries:
        reversal_of(db, organization_id, entry, description, date, created_by=user_id)

    movements = (
        db.query(FinancialTransaction)
        .filter(
            FinancialTransaction.organization_id == organization_id,
            FinancialTransaction.source_type == source_type,
            FinancialTransaction.source_id == source_id,
        )
        .all()
    )
    for movement in movements:
        opposite = OPPOSITE_TYPE.get(movement.transaction_type)
        if opposite is None:
            continue
        record_transaction(
            db,
            organization_id=organization_id,
            financial_account_id=movement.financial_account_id,
            transaction_type=opposite,
            amount=Decimal(movement.amount),
            date=date,
            description=description,
            source_type=f"{source_type}_reversal",
            source_id=source_id,
            created_by=user_id,
        )

    return {"entries": len(entries), "movements": len(movements)}
