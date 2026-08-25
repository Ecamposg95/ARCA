from __future__ import annotations

from datetime import date as date_type
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.events import event_bus
from app.models.accounting import JournalEntry
from app.models.category import Category
from app.models.contact import Customer
from app.models.receivable import Receivable
from app.domains.income.service import resolve_tax
from app.services.accounting.engine import _quantize
from app.services.taxes import proportional_tax
from app.services.accounting.rules import (
    receivable_collected_entry,
    receivable_created_entry,
    reversal_of,
)
from app.services.transactions import record_transaction


def _validate_category(db: Session, org_id: str, category_id: str) -> Category:
    category = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            Category.organization_id == org_id,
            Category.kind == "INCOME",
            Category.active.is_(True),
        )
        .first()
    )
    if category is None:
        raise ValueError("La categoría de ingreso no es válida.")
    return category


def _validate_customer(db: Session, org_id: str, customer_id: str) -> None:
    exists = (
        db.query(Customer.id)
        .filter(
            Customer.id == customer_id,
            Customer.organization_id == org_id,
            Customer.deleted_at.is_(None),
        )
        .first()
    )
    if exists is None:
        raise ValueError("El cliente no existe.")


def create_receivable(db: Session, org_id: str, payload, created_by: str) -> Receivable:
    category = _validate_category(db, org_id, payload.category_id)
    _validate_customer(db, org_id, payload.customer_id)
    issue_date = payload.date or date.today()

    tax = resolve_tax(db, org_id, payload)
    receivable = Receivable(
        organization_id=org_id,
        customer_id=payload.customer_id,
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
    db.add(receivable)
    db.flush()

    # Devengo: la CxC reconoce el ingreso al emitirse (task pack §18)
    receivable_created_entry(
        db,
        org_id,
        description=receivable.description,
        amount=Decimal(receivable.amount),
        date=issue_date,
        revenue_account_code=category.account_code,
        source_id=receivable.id,
        created_by=created_by,
        tax_amount=Decimal(receivable.tax_amount),
    )
    event_bus.publish("receivable.created", {"receivable_id": receivable.id, "organization_id": org_id})
    db.commit()
    db.refresh(receivable)
    return receivable


def collect_receivable(
    db: Session,
    org_id: str,
    receivable: Receivable,
    amount: Decimal,
    financial_account_id: str,
    collection_date: date_type | None,
    user_id: str,
) -> Receivable:
    if receivable.status == "CANCELLED":
        raise ValueError("No puedes cobrar una cuenta cancelada.")
    if receivable.status == "PAID":
        raise ValueError("Esta cuenta ya está cobrada por completo.")

    amount = _quantize(amount)
    balance = Decimal(receivable.amount) - Decimal(receivable.amount_paid)
    if amount > balance:
        raise ValueError(f"El cobro excede el saldo pendiente (${balance}).")

    when = collection_date or date.today()
    # IVA que aún no se ha trasladado a "cobrado" para esta cuenta.
    remaining_tax = Decimal(receivable.tax_amount) - Decimal(receivable.tax_collected)
    tax_now = proportional_tax(
        Decimal(receivable.tax_amount), amount, Decimal(receivable.amount), remaining_tax
    )
    if Decimal(receivable.amount_paid) + amount >= Decimal(receivable.amount):
        tax_now = _quantize(remaining_tax)
    record_transaction(
        db,
        organization_id=org_id,
        financial_account_id=financial_account_id,
        transaction_type="RECEIVABLE_COLLECTION",
        amount=amount,
        date=when,
        description=f"Cobro: {receivable.description}",
        source_type="receivable",
        source_id=receivable.id,
        created_by=user_id,
    )
    receivable_collected_entry(
        db,
        org_id,
        description=f"Cobro: {receivable.description}",
        amount=amount,
        date=when,
        source_id=receivable.id,
        created_by=user_id,
        tax_amount=tax_now,
    )
    receivable.amount_paid = Decimal(receivable.amount_paid) + amount
    receivable.tax_collected = Decimal(receivable.tax_collected) + tax_now
    receivable.status = "PAID" if receivable.amount_paid >= Decimal(receivable.amount) else "PARTIAL"
    if receivable.status == "PAID":
        event_bus.publish("receivable.paid", {"receivable_id": receivable.id, "organization_id": org_id})
    db.commit()
    db.refresh(receivable)
    return receivable


def cancel_receivable(db: Session, org_id: str, receivable: Receivable, user_id: str, reason: str | None) -> Receivable:
    if receivable.status == "CANCELLED":
        raise ValueError("Esta cuenta ya está cancelada.")
    if Decimal(receivable.amount_paid) > 0:
        raise ValueError("No puedes cancelar una cuenta con cobros registrados; los reversos completos llegan pronto.")

    original = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.organization_id == org_id,
            JournalEntry.source_type == "receivable",
            JournalEntry.source_id == receivable.id,
        )
        .order_by(JournalEntry.created_at)
        .first()
    )
    if original is not None:
        reversal_of(
            db,
            org_id,
            original,
            description=f"Cancelación: {receivable.description}",
            date=date.today(),
            created_by=user_id,
        )
    receivable.status = "CANCELLED"
    receivable.cancelled_at = datetime.now(timezone.utc)
    receivable.cancelled_by = user_id
    receivable.cancellation_reason = reason
    db.commit()
    db.refresh(receivable)
    return receivable
