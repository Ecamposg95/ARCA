"""Liquidaciones de un procesador de pagos (NetPay deposita al banco).

Una liquidación no es una operación contable nueva: es un traspaso procesador
→ banco por el neto más un gasto de comisión pagado desde el procesador.
Así el procesador baja el bruto, el banco sube el neto y la comisión queda en
resultados, sin duplicar el cobro que ya se registró con la venta.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domains.expenses.schemas import ExpenseCreate
from app.domains.expenses.service import cancel_expense, create_expense
from app.domains.transactions.service import create_transfer, reverse_transfer
from app.models.expense import Expense
from app.models.financial_account import FinancialAccount
from app.models.settlement import ProcessorSettlement
from app.services.accounting.coa import CODE_OTHER_EXPENSES
from app.services.accounting.engine import _quantize
from app.services.categories import ensure_system_category

# La categoría del gasto de comisión. No hay cuenta de comisiones bancarias
# en el catálogo sembrado, así que cae en Otros Gastos; el contador puede
# reapuntar la categoría a su cuenta de gastos financieros.
FEE_CATEGORY = ("Comisiones de terminal", "EXPENSE", CODE_OTHER_EXPENSES)


class SettlementConflictError(ValueError):
    """Misma referencia para el mismo procesador: ya está registrada (409)."""


def get_processor(db: Session, organization_id: str, account_id: str) -> FinancialAccount:
    account = (
        db.query(FinancialAccount)
        .filter(
            FinancialAccount.id == account_id,
            FinancialAccount.organization_id == organization_id,
            FinancialAccount.deleted_at.is_(None),
        )
        .first()
    )
    if account is None:
        raise LookupError("La cuenta de dinero no existe.")
    if account.type != "PROCESSOR":
        raise ValueError("Sólo un procesador de pagos tiene liquidaciones.")
    return account


def _money(value: Decimal) -> str:
    return f"${value:,.2f}"


def create_settlement(
    db: Session,
    organization_id: str,
    processor: FinancialAccount,
    *,
    date: date_type,
    gross_amount: Decimal,
    fee_amount: Decimal,
    bank_account_id: str | None,
    reference: str | None,
    notes: str | None,
    user_id: str,
) -> ProcessorSettlement:
    """Registra la liquidación: traspaso del neto y gasto de la comisión. No hace commit."""
    gross = _quantize(gross_amount)
    fee = _quantize(fee_amount)
    if gross <= 0:
        raise ValueError("El bruto debe ser mayor a cero.")
    if fee < 0:
        raise ValueError("La comisión no puede ser negativa.")
    net = gross - fee
    if net <= 0:
        raise ValueError("La comisión no puede comerse todo el bruto.")

    bank_id = bank_account_id or processor.settlement_account_id
    if not bank_id:
        raise ValueError("Elige el banco donde liquida.")
    bank = (
        db.query(FinancialAccount)
        .filter(
            FinancialAccount.id == bank_id,
            FinancialAccount.organization_id == organization_id,
            FinancialAccount.deleted_at.is_(None),
        )
        .first()
    )
    if bank is None or not bank.active:
        raise ValueError("El banco donde liquida no existe.")
    if bank.type != "BANK":
        raise ValueError("Un procesador liquida a una cuenta de banco.")

    reference = (reference or "").strip() or None
    if reference and _reference_taken(db, organization_id, processor.id, reference):
        raise SettlementConflictError("Esa liquidación ya está registrada.")

    available = Decimal(processor.current_balance)
    if gross > available:
        raise ValueError(f"{processor.name} sólo tiene {_money(available)} por liquidar.")

    label = f"Liquidación {processor.name}" + (f" · {reference}" if reference else "")
    transfer = create_transfer(
        db,
        organization_id,
        from_account_id=processor.id,
        to_account_id=bank.id,
        amount=net,
        date=date,
        description=f"{label} → {bank.name}",
        user_id=user_id,
    )

    expense_id = None
    if fee > 0:
        category = ensure_system_category(db, organization_id, *FEE_CATEGORY)
        expense = create_expense(
            db,
            organization_id,
            ExpenseCreate(
                date=date,
                description=f"Comisión {processor.name}" + (f" · {reference}" if reference else ""),
                amount=fee,
                category_id=category.id,
                financial_account_id=processor.id,
                reference=reference,
                status="PAID",
            ),
            created_by=user_id,
            commit=False,
        )
        expense_id = expense.id

    settlement = ProcessorSettlement(
        organization_id=organization_id,
        processor_account_id=processor.id,
        bank_account_id=bank.id,
        date=date,
        gross_amount=gross,
        fee_amount=fee,
        net_amount=net,
        reference=reference,
        notes=notes,
        transfer_group_id=transfer.group_id,
        expense_id=expense_id,
        created_by=user_id,
    )
    db.add(settlement)
    db.flush()
    return settlement


def _reference_taken(db: Session, organization_id: str, processor_id: str, reference: str) -> bool:
    return (
        db.query(ProcessorSettlement.id)
        .filter(
            ProcessorSettlement.organization_id == organization_id,
            ProcessorSettlement.processor_account_id == processor_id,
            ProcessorSettlement.reference == reference,
            ProcessorSettlement.status == "ACTIVE",
        )
        .first()
        is not None
    )


def get_settlement(db: Session, organization_id: str, processor_id: str, settlement_id: str) -> ProcessorSettlement:
    settlement = (
        db.query(ProcessorSettlement)
        .filter(
            ProcessorSettlement.id == settlement_id,
            ProcessorSettlement.organization_id == organization_id,
            ProcessorSettlement.processor_account_id == processor_id,
        )
        .first()
    )
    if settlement is None:
        raise LookupError("La liquidación no existe.")
    return settlement


def cancel_settlement(
    db: Session, organization_id: str, settlement: ProcessorSettlement, user_id: str
) -> ProcessorSettlement:
    """Deshace el traspaso y el gasto con pólizas espejo; la fila queda CANCELLED. No hace commit."""
    if settlement.status == "CANCELLED":
        raise ValueError("Esta liquidación ya está cancelada.")
    today = date_type.today()
    reverse_transfer(
        db,
        organization_id,
        settlement.transfer_group_id,
        description=f"Reverso: liquidación {settlement.reference or settlement.date.isoformat()}",
        date=today,
        user_id=user_id,
    )
    if settlement.expense_id:
        expense = db.get(Expense, settlement.expense_id)
        if expense is not None and expense.organization_id == organization_id:
            cancel_expense(db, expense, user_id, "Liquidación cancelada", commit=False, reversal_date=today)
    settlement.status = "CANCELLED"
    settlement.cancelled_at = datetime.now(timezone.utc)
    settlement.cancelled_by = user_id
    db.flush()
    return settlement


def settlements_query(db: Session, organization_id: str, processor_id: str):
    return (
        db.query(ProcessorSettlement)
        .filter(
            ProcessorSettlement.organization_id == organization_id,
            ProcessorSettlement.processor_account_id == processor_id,
        )
        .order_by(ProcessorSettlement.date.desc(), ProcessorSettlement.created_at.desc())
    )
