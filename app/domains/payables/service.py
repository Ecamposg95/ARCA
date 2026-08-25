from __future__ import annotations

from datetime import date as date_type
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.events import event_bus
from app.models.accounting import JournalEntry
from app.models.category import Category
from app.models.contact import Vendor
from app.models.payable import Payable
from app.domains.income.service import resolve_tax
from app.services.accounting.engine import _quantize
from app.services.taxes import proportional_tax
from app.services.accounting.rules import (
    payable_created_entry,
    payable_payment_entry,
    reversal_of,
)
from app.services.transactions import account_ledger_code, record_transaction


def _validate_category(db: Session, org_id: str, category_id: str) -> Category:
    category = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            Category.organization_id == org_id,
            Category.kind == "EXPENSE",
            Category.active.is_(True),
        )
        .first()
    )
    if category is None:
        raise ValueError("La categoría de gasto no es válida.")
    return category


def _validate_vendor(db: Session, org_id: str, vendor_id: str) -> None:
    exists = (
        db.query(Vendor.id)
        .filter(
            Vendor.id == vendor_id,
            Vendor.organization_id == org_id,
            Vendor.deleted_at.is_(None),
        )
        .first()
    )
    if exists is None:
        raise ValueError("El proveedor no existe.")


def create_payable(db: Session, org_id: str, payload, created_by: str) -> Payable:
    category = _validate_category(db, org_id, payload.category_id)
    _validate_vendor(db, org_id, payload.vendor_id)
    issue_date = payload.date or date.today()

    tax = resolve_tax(db, org_id, payload)
    payable = Payable(
        organization_id=org_id,
        vendor_id=payload.vendor_id,
        description=payload.description.strip(),
        amount=tax.total,
        subtotal=tax.subtotal,
        tax_rate=tax.tax_rate,
        tax_amount=tax.tax_amount,
        date=issue_date,
        due_date=payload.due_date,
        category_id=payload.category_id,
        notes=payload.notes,
        created_by=created_by,
    )
    db.add(payable)
    db.flush()

    # Devengo: el gasto se reconoce al registrar el compromiso (task pack §18)
    payable_created_entry(
        db,
        org_id,
        description=payable.description,
        amount=Decimal(payable.amount),
        date=issue_date,
        expense_account_code=category.account_code,
        source_id=payable.id,
        created_by=created_by,
        tax_amount=Decimal(payable.tax_amount),
    )
    event_bus.publish("payable.created", {"payable_id": payable.id, "organization_id": org_id})
    db.commit()
    db.refresh(payable)
    return payable


def pay_payable(
    db: Session,
    org_id: str,
    payable: Payable,
    amount: Decimal,
    financial_account_id: str,
    payment_date: date_type | None,
    user_id: str,
) -> Payable:
    if payable.status == "CANCELLED":
        raise ValueError("No puedes pagar una cuenta cancelada.")
    if payable.status == "PAID":
        raise ValueError("Esta cuenta ya está pagada por completo.")

    amount = _quantize(amount)
    balance = Decimal(payable.amount) - Decimal(payable.amount_paid)
    if amount > balance:
        raise ValueError(f"El pago excede el saldo pendiente (${balance}).")

    when = payment_date or date.today()
    remaining_tax = Decimal(payable.tax_amount) - Decimal(payable.tax_paid)
    tax_now = proportional_tax(
        Decimal(payable.tax_amount), amount, Decimal(payable.amount), remaining_tax
    )
    if Decimal(payable.amount_paid) + amount >= Decimal(payable.amount):
        tax_now = _quantize(remaining_tax)
    record_transaction(
        db,
        organization_id=org_id,
        financial_account_id=financial_account_id,
        transaction_type="PAYABLE_PAYMENT",
        amount=amount,
        date=when,
        description=f"Pago: {payable.description}",
        source_type="payable",
        source_id=payable.id,
        created_by=user_id,
    )
    payable_payment_entry(
        db,
        org_id,
        description=f"Pago: {payable.description}",
        amount=amount,
        date=when,
        source_id=payable.id,
        created_by=user_id,
        cash_account_code=account_ledger_code(db, org_id, financial_account_id),
        tax_amount=tax_now,
    )
    payable.amount_paid = Decimal(payable.amount_paid) + amount
    payable.tax_paid = Decimal(payable.tax_paid) + tax_now
    payable.status = "PAID" if payable.amount_paid >= Decimal(payable.amount) else "PARTIAL"
    if payable.status == "PAID":
        event_bus.publish("payable.paid", {"payable_id": payable.id, "organization_id": org_id})
    db.commit()
    db.refresh(payable)
    return payable


def cancel_payable(db: Session, org_id: str, payable: Payable, user_id: str, reason: str | None) -> Payable:
    if payable.status == "CANCELLED":
        raise ValueError("Esta cuenta ya está cancelada.")
    if Decimal(payable.amount_paid) > 0:
        raise ValueError("No puedes cancelar una cuenta con pagos registrados; los reversos completos llegan pronto.")

    original = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.organization_id == org_id,
            JournalEntry.source_type == "payable",
            JournalEntry.source_id == payable.id,
        )
        .order_by(JournalEntry.created_at)
        .first()
    )
    if original is not None:
        reversal_of(
            db,
            org_id,
            original,
            description=f"Cancelación: {payable.description}",
            date=date.today(),
            created_by=user_id,
        )
    payable.status = "CANCELLED"
    payable.cancelled_at = datetime.now(timezone.utc)
    payable.cancelled_by = user_id
    payable.cancellation_reason = reason
    db.commit()
    db.refresh(payable)
    return payable
