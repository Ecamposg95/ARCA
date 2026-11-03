"""Lista filtrada de ingresos y su descarga: un solo query para ambas.

La forma de cobro y la referencia de un ingreso no viven en el ingreso sino en
su movimiento (`source_type="income"`): ahí se filtran y de ahí se leen.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import exists, or_
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.contact import Customer
from app.models.financial_account import FinancialAccount
from app.models.income import Income
from app.models.transaction import FinancialTransaction
from app.models.user import User
from app.services.listing import OperationFilters, name_map, payment_label

STATUS_LABELS = {"PENDING": "Pendiente", "PAID": "Cobrado", "CANCELLED": "Cancelado"}


def _collection_of_income(org_id: str):
    """El movimiento de cobro de un ingreso (no su reverso)."""
    return (
        FinancialTransaction.organization_id == org_id,
        FinancialTransaction.source_type == "income",
        FinancialTransaction.source_id == Income.id,
        FinancialTransaction.transaction_type == "INCOME",
    )


def filter_incomes(db: Session, org_id: str, filters: OperationFilters):
    """El único query de la lista de ingresos: lo usan la página y la descarga.

    Sin filtro de estado incluye lo cancelado, igual que la pantalla en "Todos".
    """
    query = db.query(Income).filter(Income.organization_id == org_id)
    if filters.status:
        query = query.filter(Income.status == filters.status)
    if filters.start:
        query = query.filter(Income.date >= filters.start)
    if filters.end:
        query = query.filter(Income.date <= filters.end)
    if filters.q:
        # Concepto, cliente o referencia del cobro.
        pattern = f"%{filters.q}%"
        query = query.filter(
            or_(
                Income.description.ilike(pattern),
                exists().where(
                    Customer.id == Income.customer_id,
                    Customer.organization_id == org_id,
                    Customer.name.ilike(pattern),
                ),
                exists().where(*_collection_of_income(org_id), FinancialTransaction.reference.ilike(pattern)),
            )
        )
    if filters.category_id:
        query = query.filter(Income.category_id == filters.category_id)
    if filters.project_id:
        query = query.filter(Income.project_id == filters.project_id)
    if filters.business_unit_id:
        query = query.filter(Income.business_unit_id == filters.business_unit_id)
    if filters.fiscal_entity_id:
        query = query.filter(Income.fiscal_entity_id == filters.fiscal_entity_id)
    if filters.financial_account_id:
        query = query.filter(Income.financial_account_id == filters.financial_account_id)
    if filters.payment_method:
        query = query.filter(
            exists().where(
                *_collection_of_income(org_id),
                FinancialTransaction.payment_method == filters.payment_method,
            )
        )
    if filters.created_by:
        query = query.filter(Income.created_by == filters.created_by)
    if filters.contact:
        query = query.filter(Income.customer_id == filters.contact)
    if filters.min_amount is not None:
        query = query.filter(Income.amount >= filters.min_amount)
    if filters.max_amount is not None:
        query = query.filter(Income.amount <= filters.max_amount)
    return query


def income_export_rows(db: Session, org_id: str, query) -> list[list]:
    """Renglones en el orden de `EXPORT_HEADERS`."""
    incomes = query.all()
    categories = name_map(db, Category, org_id, (i.category_id for i in incomes))
    accounts = name_map(db, FinancialAccount, org_id, (i.financial_account_id for i in incomes))
    customers = name_map(db, Customer, org_id, (i.customer_id for i in incomes))
    users = name_map(db, User, None, (i.created_by for i in incomes))
    # Forma de cobro y referencia, de los movimientos de cobro del mismo filtro.
    ids = query.with_entities(Income.id).order_by(None).scalar_subquery()
    collections = {
        source_id: (method, reference)
        for source_id, method, reference in db.query(
            FinancialTransaction.source_id,
            FinancialTransaction.payment_method,
            FinancialTransaction.reference,
        )
        .filter(
            FinancialTransaction.organization_id == org_id,
            FinancialTransaction.source_type == "income",
            FinancialTransaction.transaction_type == "INCOME",
            FinancialTransaction.source_id.in_(ids),
        )
        .all()
    }
    rows = []
    for income in incomes:
        method, reference = collections.get(income.id, (None, None))
        rows.append(
            [
                income.date,
                income.description,
                categories.get(income.category_id),
                accounts.get(income.financial_account_id),
                income.business_unit_name,
                income.fiscal_entity_name,
                customers.get(income.customer_id),
                payment_label(method),
                STATUS_LABELS.get(income.status, income.status),
                Decimal(income.subtotal or 0),
                Decimal(income.tax_amount or 0),
                Decimal(income.amount),
                users.get(income.created_by),
                reference,
            ]
        )
    return rows
