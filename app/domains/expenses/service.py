from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.events import event_bus
from app.models.category import Category
from app.models.contact import Vendor
from app.models.expense import Expense
from app.domains.income.service import resolve_tax
from app.services.accounting.rules import expense_paid_entry
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


def create_expense(db: Session, org_id: str, payload, created_by: str) -> Expense:
    _validate_category(db, org_id, payload.category_id)
    if payload.vendor_id:
        _validate_vendor(db, org_id, payload.vendor_id)

    tax = resolve_tax(db, org_id, payload)
    expense = Expense(
        organization_id=org_id,
        date=payload.date,
        vendor_id=payload.vendor_id,
        description=payload.description.strip(),
        amount=tax.total,
        subtotal=tax.subtotal,
        tax_rate=tax.tax_rate,
        tax_amount=tax.tax_amount,
        category_id=payload.category_id,
        financial_account_id=payload.financial_account_id,
        payment_method=payload.payment_method,
        reference=payload.reference,
        notes=payload.notes,
        status="PENDING",
        created_by=created_by,
    )
    db.add(expense)
    db.flush()
    event_bus.publish("expense.created", {"expense_id": expense.id, "organization_id": org_id})

    if payload.status == "PAID":
        _apply_payment(db, org_id, expense, payload.financial_account_id, payload.date, created_by)

    db.commit()
    db.refresh(expense)
    return expense


def pay_expense(
    db: Session,
    org_id: str,
    expense: Expense,
    financial_account_id: str | None,
    paid_date: date_type | None,
    user_id: str,
) -> Expense:
    if expense.status == "PAID":
        raise ValueError("Este gasto ya está pagado.")
    if expense.status == "CANCELLED":
        raise ValueError("No puedes pagar un gasto cancelado.")
    _apply_payment(db, org_id, expense, financial_account_id, paid_date or expense.date, user_id)
    db.commit()
    db.refresh(expense)
    return expense


def _apply_payment(
    db: Session,
    org_id: str,
    expense: Expense,
    financial_account_id: str | None,
    paid_date: date_type,
    user_id: str,
) -> None:
    account_id = financial_account_id or expense.financial_account_id
    if not account_id:
        raise ValueError("Indica desde qué cuenta pagaste.")

    record_transaction(
        db,
        organization_id=org_id,
        financial_account_id=account_id,
        transaction_type="EXPENSE",
        amount=expense.amount,
        date=paid_date,
        description=expense.description,
        reference=expense.reference,
        source_type="expense",
        source_id=expense.id,
        created_by=user_id,
    )
    category = _validate_category(db, org_id, expense.category_id)
    expense_paid_entry(
        db,
        org_id,
        description=expense.description,
        amount=expense.amount,
        date=paid_date,
        expense_account_code=category.account_code,
        source_id=expense.id,
        created_by=user_id,
        cash_account_code=account_ledger_code(db, org_id, account_id),
        tax_amount=Decimal(expense.tax_amount),
    )
    expense.financial_account_id = account_id
    expense.status = "PAID"
    expense.paid_at = datetime.now(timezone.utc)
    event_bus.publish("expense.paid", {"expense_id": expense.id, "organization_id": org_id})


def cancel_expense(db: Session, expense: Expense, user_id: str, reason: str | None) -> Expense:
    if expense.status == "PAID":
        raise ValueError("Un gasto pagado no puede cancelarse todavía; los reversos llegan pronto.")
    if expense.status == "CANCELLED":
        raise ValueError("Este gasto ya está cancelado.")
    expense.status = "CANCELLED"
    expense.cancelled_at = datetime.now(timezone.utc)
    expense.cancelled_by = user_id
    expense.cancellation_reason = reason
    db.commit()
    db.refresh(expense)
    return expense
