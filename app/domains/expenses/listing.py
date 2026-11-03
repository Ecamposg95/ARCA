"""Lista filtrada de gastos y su descarga: un solo query para ambas."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import exists, or_
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.contact import Vendor
from app.models.expense import Expense
from app.models.financial_account import FinancialAccount
from app.models.user import User
from app.services.listing import OperationFilters, name_map, payment_label

STATUS_LABELS = {"PENDING": "Pendiente", "PAID": "Pagado", "CANCELLED": "Cancelado"}


def filter_expenses(db: Session, org_id: str, filters: OperationFilters, *, non_deductible: bool = False):
    """El único query de la lista de gastos: lo usan la página y la descarga.

    Sin filtro de estado incluye lo cancelado, igual que la pantalla en "Todos".
    """
    query = db.query(Expense).filter(Expense.organization_id == org_id)
    if filters.status:
        query = query.filter(Expense.status == filters.status)
    if filters.start:
        query = query.filter(Expense.date >= filters.start)
    if filters.end:
        query = query.filter(Expense.date <= filters.end)
    if filters.q:
        # Concepto, referencia o proveedor: así recuerda la gente una operación.
        pattern = f"%{filters.q}%"
        query = query.filter(
            or_(
                Expense.description.ilike(pattern),
                Expense.reference.ilike(pattern),
                exists().where(
                    Vendor.id == Expense.vendor_id,
                    Vendor.organization_id == org_id,
                    Vendor.name.ilike(pattern),
                ),
            )
        )
    if filters.category_id:
        query = query.filter(Expense.category_id == filters.category_id)
    if filters.project_id:
        query = query.filter(Expense.project_id == filters.project_id)
    if filters.business_unit_id:
        query = query.filter(Expense.business_unit_id == filters.business_unit_id)
    if filters.fiscal_entity_id:
        query = query.filter(Expense.fiscal_entity_id == filters.fiscal_entity_id)
    if filters.financial_account_id:
        query = query.filter(Expense.financial_account_id == filters.financial_account_id)
    if filters.payment_method:
        query = query.filter(Expense.payment_method == filters.payment_method)
    if filters.created_by:
        query = query.filter(Expense.created_by == filters.created_by)
    if filters.contact:
        query = query.filter(Expense.vendor_id == filters.contact)
    if filters.min_amount is not None:
        query = query.filter(Expense.amount >= filters.min_amount)
    if filters.max_amount is not None:
        query = query.filter(Expense.amount <= filters.max_amount)
    if non_deductible:
        # LISR 27-III: efectivo por más de $2,000. El mismo criterio que calcula
        # el aviso en el schema, expresado como filtro.
        query = query.filter(Expense.payment_method == "EFECTIVO", Expense.amount > 2000)
    return query


def expense_export_rows(db: Session, org_id: str, query) -> list[list]:
    """Renglones en el orden de `EXPORT_HEADERS`. Los nombres salen de una
    consulta por catálogo, no de una por renglón."""
    expenses = query.all()
    categories = name_map(db, Category, org_id, (e.category_id for e in expenses))
    accounts = name_map(db, FinancialAccount, org_id, (e.financial_account_id for e in expenses))
    vendors = name_map(db, Vendor, org_id, (e.vendor_id for e in expenses))
    users = name_map(db, User, None, (e.created_by for e in expenses))
    return [
        [
            expense.date,
            expense.description,
            categories.get(expense.category_id),
            accounts.get(expense.financial_account_id),
            expense.business_unit_name,
            expense.fiscal_entity_name,
            vendors.get(expense.vendor_id),
            payment_label(expense.payment_method),
            STATUS_LABELS.get(expense.status, expense.status),
            Decimal(expense.subtotal or 0),
            Decimal(expense.tax_amount or 0),
            Decimal(expense.amount),
            users.get(expense.created_by),
            expense.reference,
        ]
        for expense in expenses
    ]
