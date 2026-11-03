from __future__ import annotations

from datetime import date as date_type
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.events import event_bus
from app.models.category import Category
from app.models.contact import Vendor
from app.models.expense import Expense
from app.domains.income.service import resolve_tax, validate_money_account, validate_project
from app.services.accounting.rules import expense_paid_entry
from app.services.change_log import record_change, snapshot
from app.services.taxes import split_total
from app.services.reversals import reverse_operation
from app.models.financial_account import FinancialAccount
from app.services.dimensions import inherit_business_unit, tag_entry, validate_dimensions
from app.services.transactions import (
    account_ledger_code,
    default_payment_method,
    record_transaction,
)


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


def create_expense(db: Session, org_id: str, payload, created_by: str, commit: bool = True) -> Expense:
    """`commit=False` deja el gasto dentro de la transacción del caller (una
    liquidación o un corte lo registran junto con otras operaciones)."""
    expense = build_expense(db, org_id, payload, created_by)
    if commit:
        db.commit()
        db.refresh(expense)
    return expense


def build_expense(db: Session, org_id: str, payload, created_by: str) -> Expense:
    """Crea el gasto (y lo paga si viene PAID) en la transacción del caller, sin commit."""
    _validate_category(db, org_id, payload.category_id)
    if payload.vendor_id:
        _validate_vendor(db, org_id, payload.vendor_id)
    validate_dimensions(db, org_id, payload.business_unit_id, payload.fiscal_entity_id)

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
        project_id=payload.project_id,
        business_unit_id=inherit_business_unit(
            db, org_id, payload.business_unit_id, payload.financial_account_id
        ),
        fiscal_entity_id=payload.fiscal_entity_id,
        retention_isr=payload.retention_isr,
        retention_iva=payload.retention_iva,
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
    record_change(db, org_id, expense, "CREATE", created_by)
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
    before = snapshot(expense)
    _apply_payment(db, org_id, expense, financial_account_id, paid_date or expense.date, user_id)
    record_change(db, org_id, expense, "PAY", user_id, before=before, after=snapshot(expense))
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
    # Un gasto pendiente sin unidad la toma de la cuenta con la que se paga.
    expense.business_unit_id = inherit_business_unit(db, org_id, expense.business_unit_id, account_id)

    # Del banco sale el total MENOS lo retenido: esa parte no llega al proveedor,
    # se queda como deuda con el SAT hasta que se entera.
    withheld = Decimal(expense.retention_isr) + Decimal(expense.retention_iva)
    record_transaction(
        db,
        organization_id=org_id,
        financial_account_id=account_id,
        transaction_type="EXPENSE",
        amount=Decimal(expense.amount) - withheld,
        date=paid_date,
        description=expense.description,
        reference=expense.reference,
        source_type="expense",
        source_id=expense.id,
        created_by=user_id,
    )
    category = _validate_category(db, org_id, expense.category_id)
    entry = expense_paid_entry(
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
        retention_isr=Decimal(expense.retention_isr),
        retention_iva=Decimal(expense.retention_iva),
    )
    tag_entry(entry, expense.business_unit_id, expense.fiscal_entity_id)
    expense.financial_account_id = account_id
    # Cómo se pagó vive también en el gasto, no sólo en el movimiento: sin esto
    # el aviso de deducibilidad no tiene con qué decidir.
    if not expense.payment_method:
        account = db.get(FinancialAccount, account_id)
        if account is not None:
            expense.payment_method = default_payment_method(account.type)
    expense.status = "PAID"
    expense.paid_at = datetime.now(timezone.utc)
    event_bus.publish("expense.paid", {"expense_id": expense.id, "organization_id": org_id})


def cancel_expense(
    db: Session,
    expense: Expense,
    user_id: str,
    reason: str | None,
    commit: bool = True,
    reversal_date: date_type | None = None,
) -> Expense:
    """`reversal_date`: el reverso se fecha hoy salvo que el caller necesite
    otra (el ajuste de un corte se deshace en el día del corte)."""
    if expense.status == "CANCELLED":
        raise ValueError("Este gasto ya está cancelado.")
    before = snapshot(expense)
    if expense.status == "PAID":
        reverse_operation(
            db,
            expense.organization_id,
            source_type="expense",
            source_id=expense.id,
            description=f"Reverso: {expense.description}",
            date=reversal_date or date.today(),
            user_id=user_id,
        )
    expense.status = "CANCELLED"
    expense.cancelled_at = datetime.now(timezone.utc)
    expense.cancelled_by = user_id
    expense.cancellation_reason = reason
    record_change(
        db, expense.organization_id, expense, "CANCEL", user_id, before=before, after=snapshot(expense), reason=reason
    )
    if not commit:
        return expense
    db.commit()
    db.refresh(expense)
    return expense


# Mientras no se paga, un gasto no tiene movimiento ni póliza: corregirlo no
# toca la contabilidad. Una vez pagado, sólo la etiqueta analítica es editable;
# lo demás exige cancelar (reverso) y volver a registrar.
PENDING_EDITABLE = (
    "date",
    "description",
    "amount",
    "tax_rate",
    "category_id",
    "vendor_id",
    "financial_account_id",
    "payment_method",
    "reference",
    "notes",
)


def update_expense(db: Session, org_id: str, expense: Expense, changes: dict, user_id: str) -> Expense:
    """Aplica una edición y la deja en la bitácora con sus valores anteriores."""
    locked = [field for field in changes if field in PENDING_EDITABLE]
    if locked and expense.status != "PENDING":
        raise ValueError(
            "Un gasto pagado o cancelado sólo admite cambiar el proyecto. "
            "Para corregir otra cosa, cancélalo y regístralo de nuevo."
        )
    before = snapshot(expense)
    if "project_id" in changes:
        validate_project(db, org_id, changes["project_id"])
        expense.project_id = changes["project_id"]
    if changes.get("category_id"):
        _validate_category(db, org_id, changes["category_id"])
        expense.category_id = changes["category_id"]
    if "vendor_id" in changes:
        if changes["vendor_id"]:
            _validate_vendor(db, org_id, changes["vendor_id"])
        expense.vendor_id = changes["vendor_id"]
    if "financial_account_id" in changes:
        validate_money_account(db, org_id, changes["financial_account_id"])
        expense.financial_account_id = changes["financial_account_id"]
    if changes.get("date"):
        expense.date = changes["date"]
    if changes.get("description"):
        expense.description = changes["description"].strip()
    for field in ("payment_method", "reference", "notes"):
        if field in changes:
            setattr(expense, field, changes[field])
    if changes.get("amount") is not None or changes.get("tax_rate") is not None:
        amount = changes.get("amount") or Decimal(expense.amount)
        rate = changes["tax_rate"] if changes.get("tax_rate") is not None else Decimal(expense.tax_rate)
        tax = split_total(amount, rate)
        expense.amount = tax.total
        expense.subtotal = tax.subtotal
        expense.tax_rate = tax.tax_rate
        expense.tax_amount = tax.tax_amount
    record_change(db, org_id, expense, "UPDATE", user_id, before=before, after=snapshot(expense))
    db.commit()
    db.refresh(expense)
    return expense
