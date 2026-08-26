from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.events import event_bus
from app.models.category import Category
from app.models.contact import Customer
from app.models.income import Income
from app.services.accounting.rules import income_paid_entry
from app.services.taxes import split_total
from app.services.transactions import account_ledger_code, record_transaction


def resolve_tax(db: Session, org_id: str, payload):
    """Desglose de la operación.

    Si el cliente NO manda tasa, se asume 0. La tasa por defecto de la
    organización es una preferencia de la interfaz (el formulario la
    preselecciona), no del servidor: aplicar IVA en silencio a quien no lo
    pidió cambiaría montos de dinero sin que nadie lo decida.
    """
    return split_total(payload.amount, payload.tax_rate or 0)


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


def create_income(db: Session, org_id: str, payload, created_by: str) -> Income:
    _validate_category(db, org_id, payload.category_id)
    if payload.customer_id:
        _validate_customer(db, org_id, payload.customer_id)

    tax = resolve_tax(db, org_id, payload)
    income = Income(
        organization_id=org_id,
        date=payload.date,
        customer_id=payload.customer_id,
        description=payload.description.strip(),
        amount=tax.total,
        subtotal=tax.subtotal,
        tax_rate=tax.tax_rate,
        tax_amount=tax.tax_amount,
        category_id=payload.category_id,
        project_id=payload.project_id,
        financial_account_id=payload.financial_account_id,
        notes=payload.notes,
        status="PENDING",
        created_by=created_by,
    )
    db.add(income)
    db.flush()
    event_bus.publish("income.created", {"income_id": income.id, "organization_id": org_id})

    if payload.status == "PAID":
        _apply_payment(db, org_id, income, payload.financial_account_id, payload.date, created_by)

    db.commit()
    db.refresh(income)
    return income


def pay_income(
    db: Session,
    org_id: str,
    income: Income,
    financial_account_id: str | None,
    paid_date: date_type | None,
    user_id: str,
) -> Income:
    if income.status == "PAID":
        raise ValueError("Este ingreso ya está cobrado.")
    if income.status == "CANCELLED":
        raise ValueError("No puedes cobrar un ingreso cancelado.")
    _apply_payment(db, org_id, income, financial_account_id, paid_date or income.date, user_id)
    db.commit()
    db.refresh(income)
    return income


def _apply_payment(
    db: Session,
    org_id: str,
    income: Income,
    financial_account_id: str | None,
    paid_date: date_type,
    user_id: str,
) -> None:
    account_id = financial_account_id or income.financial_account_id
    if not account_id:
        raise ValueError("Indica en qué cuenta recibiste el dinero.")

    record_transaction(
        db,
        organization_id=org_id,
        financial_account_id=account_id,
        transaction_type="INCOME",
        amount=income.amount,
        date=paid_date,
        description=income.description,
        source_type="income",
        source_id=income.id,
        created_by=user_id,
    )
    category = _validate_category(db, org_id, income.category_id)
    income_paid_entry(
        db,
        org_id,
        description=income.description,
        amount=income.amount,
        date=paid_date,
        revenue_account_code=category.account_code,
        source_id=income.id,
        created_by=user_id,
        cash_account_code=account_ledger_code(db, org_id, account_id),
        tax_amount=Decimal(income.tax_amount),
    )
    income.financial_account_id = account_id
    income.status = "PAID"
    income.paid_at = datetime.now(timezone.utc)
    event_bus.publish("income.paid", {"income_id": income.id, "organization_id": org_id})


def cancel_income(db: Session, income: Income, user_id: str, reason: str | None) -> Income:
    if income.status == "PAID":
        raise ValueError("Un ingreso cobrado no puede cancelarse todavía; los reversos llegan pronto.")
    if income.status == "CANCELLED":
        raise ValueError("Este ingreso ya está cancelado.")
    income.status = "CANCELLED"
    income.cancelled_at = datetime.now(timezone.utc)
    income.cancelled_by = user_id
    income.cancellation_reason = reason
    db.commit()
    db.refresh(income)
    return income
