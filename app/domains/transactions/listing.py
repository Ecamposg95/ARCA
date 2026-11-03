"""Lista filtrada de movimientos y su descarga: un solo query para ambas.

Un movimiento no tiene categoría ni proveedor propios: los toma de la
operación que lo originó (`source_type`/`source_id`), igual que la entidad
fiscal se toma de la póliza.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from decimal import Decimal

from fastapi import Query
from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import Session

from app.models.accounting import JournalEntry
from app.models.category import Category
from app.models.contact import Customer, Vendor
from app.models.expense import Expense
from app.models.financial_account import FinancialAccount
from app.models.fiscal_entity import FiscalEntity
from app.models.income import Income
from app.models.transaction import INFLOW_TYPES, FinancialTransaction
from app.models.user import User
from app.services.dimensions import transaction_filters
from app.services.listing import EXPORT_HEADERS, name_map, payment_label

STATUS_LABELS = {"ACTIVE": "Aplicado", "CANCELLED": "Cancelado"}

TYPE_LABELS = {
    "INCOME": "Ingreso",
    "EXPENSE": "Gasto",
    "TRANSFER_IN": "Traspaso (entrada)",
    "TRANSFER_OUT": "Traspaso (salida)",
    "RECEIVABLE_COLLECTION": "Cobro",
    "PAYABLE_PAYMENT": "Pago",
    "ADJUSTMENT": "Ajuste",
    "REVERSAL_IN": "Reverso (entrada)",
    "REVERSAL_OUT": "Reverso (salida)",
}

# Los mismos encabezados de gastos e ingresos más el tipo: en movimientos
# conviven entradas y salidas.
TRANSACTION_HEADERS = [*EXPORT_HEADERS[:2], "Tipo", *EXPORT_HEADERS[2:]]
TRANSACTION_MONEY_COLUMNS = {10, 11, 12}
TRANSACTION_STATUS_INDEX = 9


@dataclass
class TransactionFilters:
    account_id: str | None = None
    transaction_type: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    start: date_type | None = None
    end: date_type | None = None
    business_unit_id: str | None = None
    fiscal_entity_id: str | None = None
    status: str | None = None
    payment_method: str | None = None
    created_by: str | None = None
    category_id: str | None = None
    contact: str | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    q: str | None = None


def transaction_list_filters(
    account_id: str | None = None,
    # Alias con el nombre de gastos e ingresos: el mismo filtro se llama igual.
    financial_account_id: str | None = None,
    transaction_type: str | None = Query(default=None, max_length=30),
    # Origen: "los cobros de ESTA factura". Ambos o ninguno — un source_id
    # suelto cruzaría tipos de entidad distintos.
    source_type: str | None = Query(default=None, max_length=50),
    source_id: str | None = Query(default=None, max_length=64),
    start: date_type | None = None,
    end: date_type | None = None,
    business_unit_id: str | None = None,
    fiscal_entity_id: str | None = None,
    status: str | None = Query(default=None, pattern="^(ACTIVE|CANCELLED)$"),
    payment_method: str | None = Query(default=None, max_length=30),
    created_by: str | None = Query(default=None, max_length=36),
    category_id: str | None = None,
    contact: str | None = Query(default=None, max_length=36, description="Proveedor o cliente (id)."),
    min_amount: Decimal | None = Query(default=None, ge=0, allow_inf_nan=False),
    max_amount: Decimal | None = Query(default=None, ge=0, allow_inf_nan=False),
    q: str | None = Query(default=None, max_length=200),
) -> TransactionFilters:
    return TransactionFilters(
        account_id=account_id or financial_account_id,
        transaction_type=transaction_type,
        source_type=source_type,
        source_id=source_id,
        start=start,
        end=end,
        business_unit_id=business_unit_id,
        fiscal_entity_id=fiscal_entity_id,
        status=status,
        payment_method=payment_method,
        created_by=created_by,
        category_id=category_id,
        contact=contact,
        min_amount=min_amount,
        max_amount=max_amount,
        q=q,
    )


def _from_operation(org_id: str, expense_condition, income_condition):
    """El movimiento viene de un gasto o un ingreso que cumple la condición."""
    return or_(
        and_(
            FinancialTransaction.source_type == "expense",
            exists().where(
                Expense.id == FinancialTransaction.source_id,
                Expense.organization_id == org_id,
                expense_condition,
            ),
        ),
        and_(
            FinancialTransaction.source_type == "income",
            exists().where(
                Income.id == FinancialTransaction.source_id,
                Income.organization_id == org_id,
                income_condition,
            ),
        ),
    )


def filter_transactions(db: Session, org_id: str, filters: TransactionFilters):
    """El único query de Movimientos: lo usan la página y la descarga."""
    query = db.query(FinancialTransaction).filter(
        FinancialTransaction.organization_id == org_id,
        *transaction_filters(filters.business_unit_id, filters.fiscal_entity_id),
    )
    if filters.account_id:
        query = query.filter(FinancialTransaction.financial_account_id == filters.account_id)
    if filters.transaction_type:
        query = query.filter(FinancialTransaction.transaction_type == filters.transaction_type)
    if filters.source_type:
        query = query.filter(FinancialTransaction.source_type == filters.source_type)
    if filters.source_id:
        query = query.filter(FinancialTransaction.source_id == filters.source_id)
    if filters.start:
        query = query.filter(FinancialTransaction.date >= filters.start)
    if filters.end:
        query = query.filter(FinancialTransaction.date <= filters.end)
    if filters.status:
        query = query.filter(FinancialTransaction.status == filters.status)
    if filters.payment_method:
        query = query.filter(FinancialTransaction.payment_method == filters.payment_method)
    if filters.created_by:
        query = query.filter(FinancialTransaction.created_by == filters.created_by)
    if filters.min_amount is not None:
        query = query.filter(FinancialTransaction.amount >= filters.min_amount)
    if filters.max_amount is not None:
        query = query.filter(FinancialTransaction.amount <= filters.max_amount)
    if filters.category_id:
        query = query.filter(
            _from_operation(org_id, Expense.category_id == filters.category_id, Income.category_id == filters.category_id)
        )
    if filters.contact:
        query = query.filter(
            _from_operation(org_id, Expense.vendor_id == filters.contact, Income.customer_id == filters.contact)
        )
    if filters.q:
        pattern = f"%{filters.q}%"
        query = query.filter(
            or_(
                FinancialTransaction.description.ilike(pattern),
                FinancialTransaction.reference.ilike(pattern),
            )
        )
    return query


def sorted_transactions(query):
    return query.order_by(
        FinancialTransaction.date.desc(),
        FinancialTransaction.created_at.desc(),
        FinancialTransaction.id.desc(),
    )


def transaction_export_rows(db: Session, org_id: str, query) -> list[list]:
    """Renglones en el orden de `TRANSACTION_HEADERS`. Las cifras llevan signo:
    lo que entra suma, lo que sale resta, y el total es el flujo neto."""
    movements = query.all()
    ids = query.with_entities(FinancialTransaction.source_id).order_by(None).scalar_subquery()
    expenses = {
        e.id: e
        for e in db.query(Expense).filter(Expense.organization_id == org_id, Expense.id.in_(ids)).all()
    }
    incomes = {
        i.id: i for i in db.query(Income).filter(Income.organization_id == org_id, Income.id.in_(ids)).all()
    }
    entities = dict(
        db.query(JournalEntry.source_id, FiscalEntity.name)
        .join(FiscalEntity, FiscalEntity.id == JournalEntry.fiscal_entity_id)
        .filter(JournalEntry.organization_id == org_id, JournalEntry.source_id.in_(ids))
        .all()
    )
    categories = name_map(
        db,
        Category,
        org_id,
        [e.category_id for e in expenses.values()] + [i.category_id for i in incomes.values()],
    )
    vendors = name_map(db, Vendor, org_id, (e.vendor_id for e in expenses.values()))
    customers = name_map(db, Customer, org_id, (i.customer_id for i in incomes.values()))
    accounts = name_map(db, FinancialAccount, org_id, (m.financial_account_id for m in movements))
    users = name_map(db, User, None, (m.created_by for m in movements))

    rows = []
    for movement in movements:
        sign = Decimal("1") if movement.transaction_type in INFLOW_TYPES else Decimal("-1")
        operation = None
        contact = None
        if movement.source_type == "expense":
            operation = expenses.get(movement.source_id)
            contact = vendors.get(operation.vendor_id) if operation else None
        elif movement.source_type == "income":
            operation = incomes.get(movement.source_id)
            contact = customers.get(operation.customer_id) if operation else None
        # Sólo si el movimiento es la operación completa tiene sentido su desglose.
        full = operation is not None and Decimal(operation.amount) == Decimal(movement.amount)
        subtotal = sign * Decimal(operation.subtotal or 0) if full else None
        tax = sign * Decimal(operation.tax_amount or 0) if full else None
        rows.append(
            [
                movement.date,
                movement.description,
                TYPE_LABELS.get(movement.transaction_type, movement.transaction_type),
                categories.get(operation.category_id) if operation else None,
                accounts.get(movement.financial_account_id),
                movement.business_unit_name,
                entities.get(movement.source_id),
                contact,
                payment_label(movement.payment_method),
                STATUS_LABELS.get(movement.status, movement.status),
                subtotal,
                tax,
                sign * Decimal(movement.amount),
                users.get(movement.created_by),
                movement.reference,
            ]
        )
    return rows
