from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.expense import Expense
from app.models.financial_account import (
    AVAILABLE_ACCOUNT_TYPES,
    IN_TRANSIT_ACCOUNT_TYPES,
    LIABILITY_ACCOUNT_TYPES,
    FinancialAccount,
)
from app.models.payable import Payable
from app.models.receivable import Receivable
from app.models.transaction import INFLOW_TYPES, FinancialTransaction
from app.services.accounting.engine import account_type_balance
from app.services.dimensions import transaction_filters


def _operation_filters(model, business_unit_id: str | None, fiscal_entity_id: str | None) -> list:
    """Filtros por dimensión sobre una operación (gasto, CxC, CxP)."""
    conditions = []
    if business_unit_id:
        conditions.append(model.business_unit_id == business_unit_id)
    if fiscal_entity_id:
        conditions.append(model.fiscal_entity_id == fiscal_entity_id)
    return conditions


def outstanding(
    db: Session,
    organization_id: str,
    model,
    overdue_only: bool = False,
    business_unit_id: str | None = None,
    fiscal_entity_id: str | None = None,
) -> Decimal:
    """Saldo pendiente (amount - amount_paid) de cuentas abiertas o parciales."""
    query = db.query(
        func.coalesce(func.sum(model.amount), 0),
        func.coalesce(func.sum(model.amount_paid), 0),
    ).filter(
        model.organization_id == organization_id,
        model.status.in_(("OPEN", "PARTIAL")),
        *_operation_filters(model, business_unit_id, fiscal_entity_id),
    )
    if overdue_only:
        query = query.filter(model.due_date < date.today())
    total, paid = query.one()
    return Decimal(total or 0) - Decimal(paid or 0)


def _account_balances(db: Session, organization_id: str, types: tuple[str, ...], business_unit_id: str | None) -> Decimal:
    query = db.query(func.coalesce(func.sum(FinancialAccount.current_balance), 0)).filter(
        FinancialAccount.organization_id == organization_id,
        FinancialAccount.deleted_at.is_(None),
        FinancialAccount.active.is_(True),
        FinancialAccount.type.in_(types),
    )
    # Las cajas son de una unidad; de un contribuyente no (el dinero es uno).
    if business_unit_id:
        query = query.filter(FinancialAccount.business_unit_id == business_unit_id)
    return Decimal(query.scalar() or 0)


def available_cash(db: Session, organization_id: str, business_unit_id: str | None = None) -> Decimal:
    """Efectivo disponible: sólo instrumentos de activo.

    Sumar el saldo de una tarjeta restaría deuda al efectivo y diría que tienes
    menos dinero del que tienes. Lo que trae un procesador de pagos tampoco
    cuenta: es tuyo, pero no lo puedes gastar hasta que liquide al banco.
    """
    return _account_balances(db, organization_id, AVAILABLE_ACCOUNT_TYPES, business_unit_id)


def in_transit_total(db: Session, organization_id: str, business_unit_id: str | None = None) -> Decimal:
    """Por recibir de procesadores: cobrado con tarjeta y aún no depositado."""
    return _account_balances(db, organization_id, IN_TRANSIT_ACCOUNT_TYPES, business_unit_id)


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _shift_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def cash_flow_series(
    db: Session,
    organization_id: str,
    granularity: str = "month",
    business_unit_id: str | None = None,
    fiscal_entity_id: str | None = None,
) -> dict:
    """Entradas y salidas por periodo, con el desglose que alimenta el tooltip.

    `month`: últimos 6 meses. `week`: últimas 12 semanas ISO. Cada punto trae
    entradas, salidas, neto y las 3 categorías de gasto más grandes del periodo
    — el tooltip debe explicar la barra, no repetirla.
    """
    today = date.today()

    if granularity == "week":
        # Lunes de la semana actual, 12 semanas hacia atrás.
        current_start = today - timedelta(days=today.weekday())
        starts = [current_start - timedelta(weeks=offset) for offset in range(11, -1, -1)]

        def bucket_of(day: date) -> str:
            year, week, _ = day.isocalendar()
            return f"{year}-W{week:02d}"

        buckets = [(bucket_of(start), start) for start in starts]
        series_start = starts[0]
    else:
        month_starts = [_shift_months(_month_start(today), -offset) for offset in range(5, -1, -1)]

        def bucket_of(day: date) -> str:
            return day.strftime("%Y-%m")

        buckets = [(bucket_of(start), start) for start in month_starts]
        series_start = month_starts[0]

    points: dict[str, dict] = {
        key: {
            "bucket": key,
            "start": start,
            "inflows": Decimal("0"),
            "outflows": Decimal("0"),
        }
        for key, start in buckets
    }

    rows = (
        db.query(
            FinancialTransaction.date,
            FinancialTransaction.transaction_type,
            FinancialTransaction.amount,
        )
        .filter(
            FinancialTransaction.organization_id == organization_id,
            FinancialTransaction.status == "ACTIVE",
            FinancialTransaction.date >= series_start,
            *transaction_filters(business_unit_id, fiscal_entity_id),
        )
        .all()
    )
    for row_date, transaction_type, amount in rows:
        key = bucket_of(row_date)
        if key not in points:
            continue
        amount = Decimal(amount or 0)
        if transaction_type in INFLOW_TYPES:
            points[key]["inflows"] += amount
        else:
            points[key]["outflows"] += amount

    # Top categorías de gasto PAGADO por periodo: una sola consulta agregada.
    expense_rows = (
        db.query(Expense.date, Category.name, Expense.amount)
        .join(Category, Category.id == Expense.category_id)
        .filter(
            Expense.organization_id == organization_id,
            Expense.status == "PAID",
            Expense.date >= series_start,
            *_operation_filters(Expense, business_unit_id, fiscal_entity_id),
        )
        .all()
    )
    by_bucket_category: dict[str, dict[str, Decimal]] = {}
    for row_date, category_name, amount in expense_rows:
        key = bucket_of(row_date)
        if key not in points:
            continue
        bucket = by_bucket_category.setdefault(key, {})
        bucket[category_name] = bucket.get(category_name, Decimal("0")) + Decimal(amount or 0)

    ordered = []
    for key, _start in buckets:
        top = sorted(
            by_bucket_category.get(key, {}).items(), key=lambda item: item[1], reverse=True
        )[:3]
        point = points[key]
        ordered.append(
            {
                **point,
                "net": point["inflows"] - point["outflows"],
                "top_expense_categories": [
                    {"category": name, "amount": amount} for name, amount in top
                ],
            }
        )

    return {"granularity": granularity, "points": ordered}


def summary(
    db: Session,
    organization_id: str,
    business_unit_id: str | None = None,
    fiscal_entity_id: str | None = None,
) -> dict:
    """El tablero de Inicio. Con unidad o contribuyente, cada cifra es sólo de
    esa dimensión; sin ellos, el negocio completo, como siempre."""
    today = date.today()
    month_start = _month_start(today)
    dims = {"business_unit_id": business_unit_id, "fiscal_entity_id": fiscal_entity_id}

    cash = available_cash(db, organization_id, business_unit_id)
    in_transit = in_transit_total(db, organization_id, business_unit_id)
    card_debt = _account_balances(db, organization_id, LIABILITY_ACCOUNT_TYPES, business_unit_id)

    monthly_revenue = account_type_balance(db, organization_id, "REVENUE", start=month_start, end=today, **dims)
    monthly_expenses = account_type_balance(db, organization_id, "EXPENSE", start=month_start, end=today, **dims)

    # Mismo periodo del mes anterior (hasta el mismo día) para comparar peras con peras:
    # comparar 10 días de este mes contra 30 del anterior sería engañoso.
    previous_start = _shift_months(month_start, -1)
    previous_end = min(
        _shift_months(previous_start, 1) - timedelta(days=1),
        previous_start + (today - month_start),
    )
    previous_revenue = account_type_balance(
        db, organization_id, "REVENUE", start=previous_start, end=previous_end, **dims
    )
    previous_expenses = account_type_balance(
        db, organization_id, "EXPENSE", start=previous_start, end=previous_end, **dims
    )

    # Series de 6 meses desde movimientos
    series_start = _shift_months(today, -5)
    rows = (
        db.query(
            FinancialTransaction.date,
            FinancialTransaction.transaction_type,
            FinancialTransaction.amount,
        )
        .filter(
            FinancialTransaction.organization_id == organization_id,
            FinancialTransaction.status == "ACTIVE",
            FinancialTransaction.date >= series_start,
            *transaction_filters(business_unit_id, fiscal_entity_id),
        )
        .all()
    )
    months: list[str] = []
    cursor = series_start
    while cursor <= today:
        months.append(cursor.strftime("%Y-%m"))
        cursor = _shift_months(cursor, 1)

    flow: dict[str, dict[str, Decimal]] = {m: {"inflows": Decimal("0"), "outflows": Decimal("0")} for m in months}
    operations: dict[str, dict[str, Decimal]] = {m: {"revenue": Decimal("0"), "expenses": Decimal("0")} for m in months}
    for row_date, transaction_type, amount in rows:
        key = row_date.strftime("%Y-%m")
        if key not in flow:
            continue
        amount = Decimal(amount or 0)
        if transaction_type in INFLOW_TYPES:
            flow[key]["inflows"] += amount
        else:
            flow[key]["outflows"] += amount
        if transaction_type == "INCOME":
            operations[key]["revenue"] += amount
        elif transaction_type == "EXPENSE":
            operations[key]["expenses"] += amount

    # Distribución de gastos pagados del mes por categoría
    expense_categories = (
        db.query(
            Category.name,
            func.coalesce(func.sum(Expense.amount), 0),
        )
        .join(Expense, Expense.category_id == Category.id)
        .filter(
            Expense.organization_id == organization_id,
            Expense.status == "PAID",
            Expense.date >= month_start,
            Expense.date <= today,
            *_operation_filters(Expense, business_unit_id, fiscal_entity_id),
        )
        .group_by(Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )

    return {
        "cash": cash,
        "in_transit_total": in_transit,
        "card_debt": card_debt,
        "monthly_revenue": monthly_revenue,
        "monthly_expenses": monthly_expenses,
        "monthly_profit": monthly_revenue - monthly_expenses,
        "previous_revenue": previous_revenue,
        "previous_expenses": previous_expenses,
        "previous_profit": previous_revenue - previous_expenses,
        "previous_period_end": previous_end,
        "receivables": outstanding(db, organization_id, Receivable, **dims),
        "overdue_receivables": outstanding(db, organization_id, Receivable, overdue_only=True, **dims),
        "payables": outstanding(db, organization_id, Payable, **dims),
        "cash_flow": [
            {"month": m, "inflows": flow[m]["inflows"], "outflows": flow[m]["outflows"]} for m in months
        ],
        "revenue_vs_expenses": [
            {"month": m, "revenue": operations[m]["revenue"], "expenses": operations[m]["expenses"]} for m in months
        ],
        "expense_categories": [
            {"category": name, "amount": Decimal(amount or 0)} for name, amount in expense_categories
        ],
    }
