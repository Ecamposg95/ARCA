"""Registro de movimientos financieros — ÚNICO punto que muta saldos.

Patrón Atlas para estado mutable: lock → refresh → re-check, en ese orden.
El saldo nunca se asigna desde fuera; siempre se deriva del movimiento.
"""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.events import event_bus
from app.models.financial_account import FinancialAccount, is_liability
from app.models.transaction import INFLOW_TYPES, TRANSACTION_TYPES, FinancialTransaction
from app.services.accounting.engine import _quantize


def account_ledger_code(db: Session, organization_id: str, financial_account_id: str) -> str:
    """Cuenta contable del instrumento con el que se movió el dinero."""
    from app.services.accounting.coa import CODE_CASH_BANK, ledger_code_for

    account = (
        db.query(FinancialAccount)
        .filter(
            FinancialAccount.id == financial_account_id,
            FinancialAccount.organization_id == organization_id,
        )
        .first()
    )
    return ledger_code_for(account.type) if account else CODE_CASH_BANK


def default_payment_method(account_type: str) -> str:
    """Método implícito por el instrumento; el usuario puede sobreescribirlo."""
    return {"CASH": "EFECTIVO", "BANK": "TRANSFERENCIA", "CREDIT_CARD": "TARJETA_CREDITO"}.get(
        account_type, "OTRO"
    )


def get_locked_account(db: Session, organization_id: str, financial_account_id: str) -> FinancialAccount:
    """Obtiene la cuenta CON LOCK de fila (FOR UPDATE en PostgreSQL)."""
    account = (
        db.query(FinancialAccount)
        .filter(
            FinancialAccount.id == financial_account_id,
            FinancialAccount.organization_id == organization_id,
        )
        .with_for_update()
        .first()
    )
    if account is None:
        raise ValueError("La cuenta de dinero no existe.")
    if not account.active or account.deleted_at is not None:
        raise ValueError("La cuenta de dinero está inactiva.")
    return account


def record_transaction(
    db: Session,
    organization_id: str,
    financial_account_id: str,
    transaction_type: str,
    amount: Decimal,
    date: date_type,
    description: str,
    reference: str | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
    transfer_group_id: str | None = None,
    created_by: str | None = None,
    payment_method: str | None = None,
) -> FinancialTransaction:
    """Crea el movimiento y aplica el delta al saldo, en la transacción del caller. No hace commit."""
    if transaction_type not in TRANSACTION_TYPES:
        raise ValueError("Tipo de movimiento inválido.")
    amount = _quantize(amount)
    if amount <= 0:
        raise ValueError("El monto debe ser mayor a cero.")

    account = get_locked_account(db, organization_id, financial_account_id)

    # En un activo el saldo es lo que TIENES; en un pasivo es lo que DEBES,
    # así que un gasto con tarjeta sube la deuda en vez de bajar tu efectivo.
    inflow = transaction_type in INFLOW_TYPES
    if is_liability(account.type):
        delta = -amount if inflow else amount
    else:
        delta = amount if inflow else -amount
    account.current_balance = Decimal(account.current_balance) + delta

    transaction = FinancialTransaction(
        organization_id=organization_id,
        financial_account_id=account.id,
        payment_method=payment_method or default_payment_method(account.type),
        transaction_type=transaction_type,
        amount=amount,
        currency=account.currency,
        date=date,
        description=description,
        reference=reference,
        source_type=source_type,
        source_id=source_id,
        transfer_group_id=transfer_group_id,
        created_by=created_by,
    )
    db.add(transaction)
    db.flush()
    event_bus.publish(
        "transaction.created",
        {
            "transaction_id": transaction.id,
            "organization_id": organization_id,
            "type": transaction_type,
            "amount": str(amount),
        },
    )
    return transaction
