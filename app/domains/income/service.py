from __future__ import annotations

from datetime import date as date_type
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.events import event_bus
from app.models.category import Category
from app.models.contact import Customer
from app.models.financial_account import FinancialAccount
from app.models.income import Income
from app.models.project import Project
from app.services.accounting.rules import income_paid_entry
from app.services.taxes import split_total
from app.services.change_log import record_change, snapshot
from app.services.reversals import reverse_operation
from app.services.dimensions import inherit_business_unit, tag_entry, validate_dimensions
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


def create_income(db: Session, org_id: str, payload, created_by: str, commit: bool = True) -> Income:
    """`commit=False` deja el ingreso dentro de la transacción del caller (una
    liquidación o un corte lo registran junto con otras operaciones)."""
    income = build_income(db, org_id, payload, created_by)
    if commit:
        db.commit()
        db.refresh(income)
    return income


def build_income(db: Session, org_id: str, payload, created_by: str) -> Income:
    """Crea el ingreso (y lo cobra si viene PAID) en la transacción del caller.

    No hace commit: la importación crea decenas en un solo lote, todos o ninguno.
    """
    _validate_category(db, org_id, payload.category_id)
    if payload.customer_id:
        _validate_customer(db, org_id, payload.customer_id)
    validate_dimensions(db, org_id, payload.business_unit_id, payload.fiscal_entity_id)

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
        business_unit_id=inherit_business_unit(
            db, org_id, payload.business_unit_id, payload.financial_account_id
        ),
        fiscal_entity_id=payload.fiscal_entity_id,
        financial_account_id=payload.financial_account_id,
        notes=payload.notes,
        status="PENDING",
        created_by=created_by,
    )
    db.add(income)
    db.flush()
    event_bus.publish("income.created", {"income_id": income.id, "organization_id": org_id})

    if payload.status == "PAID":
        _apply_payment(
            db,
            org_id,
            income,
            payload.financial_account_id,
            payload.date,
            created_by,
            payment_method=getattr(payload, "payment_method", None),
            reference=getattr(payload, "reference", None),
        )
    record_change(db, org_id, income, "CREATE", created_by)
    return income


def pay_income(
    db: Session,
    org_id: str,
    income: Income,
    financial_account_id: str | None,
    paid_date: date_type | None,
    user_id: str,
    payment_method: str | None = None,
) -> Income:
    if income.status == "PAID":
        raise ValueError("Este ingreso ya está cobrado.")
    if income.status == "CANCELLED":
        raise ValueError("No puedes cobrar un ingreso cancelado.")
    before = snapshot(income)
    _apply_payment(
        db, org_id, income, financial_account_id, paid_date or income.date, user_id, payment_method=payment_method
    )
    record_change(db, org_id, income, "PAY", user_id, before=before, after=snapshot(income))
    db.commit()
    db.refresh(income)
    return income


CARD_METHODS = ("TARJETA_DEBITO", "TARJETA_CREDITO")


def default_processor_id(db: Session, org_id: str) -> str | None:
    """El procesador de pagos de la empresa, si tiene uno activo (el más antiguo)."""
    return (
        db.query(FinancialAccount.id)
        .filter(
            FinancialAccount.organization_id == org_id,
            FinancialAccount.type == "PROCESSOR",
            FinancialAccount.active.is_(True),
            FinancialAccount.deleted_at.is_(None),
        )
        .order_by(FinancialAccount.created_at)
        .limit(1)
        .scalar()
    )


def _apply_payment(
    db: Session,
    org_id: str,
    income: Income,
    financial_account_id: str | None,
    paid_date: date_type,
    user_id: str,
    payment_method: str | None = None,
    reference: str | None = None,
) -> None:
    account_id = financial_account_id or income.financial_account_id
    if not account_id and payment_method in CARD_METHODS:
        # Un cobro con tarjeta no está en el banco: lo tiene el procesador
        # hasta que liquide. Si la empresa no tiene uno, que elija cuenta.
        account_id = default_processor_id(db, org_id)
    if not account_id:
        raise ValueError("Indica en qué cuenta recibiste el dinero.")
    # Un ingreso pendiente sin unidad la toma de la cuenta en la que se cobra.
    income.business_unit_id = inherit_business_unit(db, org_id, income.business_unit_id, account_id)

    record_transaction(
        db,
        organization_id=org_id,
        financial_account_id=account_id,
        transaction_type="INCOME",
        amount=income.amount,
        date=paid_date,
        description=income.description,
        reference=reference,
        source_type="income",
        source_id=income.id,
        created_by=user_id,
        payment_method=payment_method,
    )
    category = _validate_category(db, org_id, income.category_id)
    entry = income_paid_entry(
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
    tag_entry(entry, income.business_unit_id, income.fiscal_entity_id)
    income.financial_account_id = account_id
    income.status = "PAID"
    income.paid_at = datetime.now(timezone.utc)
    event_bus.publish("income.paid", {"income_id": income.id, "organization_id": org_id})


def cancel_income(
    db: Session,
    income: Income,
    user_id: str,
    reason: str | None,
    commit: bool = True,
    reversal_date: date_type | None = None,
) -> Income:
    if income.status == "CANCELLED":
        raise ValueError("Este ingreso ya está cancelado.")
    before = snapshot(income)

    # Si ya movió dinero, cancelar no basta: hay que revertir la contabilidad y
    # devolver el saldo. Nada se borra; se emite la póliza espejo.
    if income.status == "PAID":
        reverse_operation(
            db,
            income.organization_id,
            source_type="income",
            source_id=income.id,
            description=f"Reverso: {income.description}",
            date=reversal_date or date.today(),
            user_id=user_id,
        )

    income.status = "CANCELLED"
    income.cancelled_at = datetime.now(timezone.utc)
    income.cancelled_by = user_id
    income.cancellation_reason = reason
    record_change(
        db, income.organization_id, income, "CANCEL", user_id, before=before, after=snapshot(income), reason=reason
    )
    if not commit:
        return income
    db.commit()
    db.refresh(income)
    return income


def validate_project(db: Session, org_id: str, project_id: str | None) -> None:
    if project_id is None:
        return
    exists = (
        db.query(Project.id).filter(Project.id == project_id, Project.organization_id == org_id).first()
    )
    if exists is None:
        raise ValueError("Ese proyecto no existe en tu empresa.")


def validate_money_account(db: Session, org_id: str, account_id: str | None) -> None:
    if account_id is None:
        return
    exists = (
        db.query(FinancialAccount.id)
        .filter(
            FinancialAccount.id == account_id,
            FinancialAccount.organization_id == org_id,
            FinancialAccount.deleted_at.is_(None),
        )
        .first()
    )
    if exists is None:
        raise ValueError("Esa cuenta de dinero no existe en tu empresa.")


# Un ingreso pendiente no tiene movimiento ni póliza: corregirlo no toca la
# contabilidad. Ya cobrado o cancelado, sólo la etiqueta analítica es editable.
PENDING_EDITABLE = (
    "date",
    "description",
    "amount",
    "tax_rate",
    "category_id",
    "customer_id",
    "financial_account_id",
    "notes",
)


def update_income(db: Session, org_id: str, income: Income, changes: dict, user_id: str) -> Income:
    """Aplica una edición y la deja en la bitácora con sus valores anteriores."""
    locked = [field for field in changes if field in PENDING_EDITABLE]
    if locked and income.status != "PENDING":
        raise ValueError(
            "Un ingreso cobrado o cancelado sólo admite cambiar el proyecto. "
            "Para corregir otra cosa, cancélalo y regístralo de nuevo."
        )
    before = snapshot(income)
    if "project_id" in changes:
        validate_project(db, org_id, changes["project_id"])
        income.project_id = changes["project_id"]
    if changes.get("category_id"):
        _validate_category(db, org_id, changes["category_id"])
        income.category_id = changes["category_id"]
    if "customer_id" in changes:
        if changes["customer_id"]:
            _validate_customer(db, org_id, changes["customer_id"])
        income.customer_id = changes["customer_id"]
    if "financial_account_id" in changes:
        validate_money_account(db, org_id, changes["financial_account_id"])
        income.financial_account_id = changes["financial_account_id"]
    if changes.get("date"):
        income.date = changes["date"]
    if changes.get("description"):
        income.description = changes["description"].strip()
    if "notes" in changes:
        income.notes = changes["notes"]
    if changes.get("amount") is not None or changes.get("tax_rate") is not None:
        amount = changes.get("amount") or Decimal(income.amount)
        rate = changes["tax_rate"] if changes.get("tax_rate") is not None else Decimal(income.tax_rate)
        tax = split_total(amount, rate)
        income.amount = tax.total
        income.subtotal = tax.subtotal
        income.tax_rate = tax.tax_rate
        income.tax_amount = tax.tax_amount
    record_change(db, org_id, income, "UPDATE", user_id, before=before, after=snapshot(income))
    db.commit()
    db.refresh(income)
    return income
