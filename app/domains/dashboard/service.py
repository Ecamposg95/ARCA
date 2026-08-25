from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.expense import Expense
from app.models.financial_account import ASSET_ACCOUNT_TYPES, FinancialAccount
from app.models.payable import Payable
from app.models.receivable import Receivable
from app.models.transaction import INFLOW_TYPES, FinancialTransaction
from app.services.accounting.engine import account_type_balance


def _outstanding(db: Session, organization_id: str, model, overdue_only: bool = False) -> Decimal:
    """Saldo pendiente (amount - amount_paid) de cuentas abiertas o parciales."""
    query = db.query(
        func.coalesce(func.sum(model.amount), 0),
        func.coalesce(func.sum(model.amount_paid), 0),
    ).filter(
        model.organization_id == organization_id,
        model.status.in_(("OPEN", "PARTIAL")),
    )
    if overdue_only:
        query = query.filter(model.due_date < date.today())
    total, paid = query.one()
    return Decimal(total or 0) - Decimal(paid or 0)


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _shift_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def summary(db: Session, organization_id: str) -> dict:
    today = date.today()
    month_start = _month_start(today)

    # Sólo instrumentos de activo: sumar el saldo de una tarjeta restaría deuda
    # al efectivo disponible y diría que tienes menos dinero del que tienes.
    cash = (
        db.query(func.coalesce(func.sum(FinancialAccount.current_balance), 0))
        .filter(
            FinancialAccount.organization_id == organization_id,
            FinancialAccount.deleted_at.is_(None),
            FinancialAccount.active.is_(True),
            FinancialAccount.type.in_(ASSET_ACCOUNT_TYPES),
        )
        .scalar()
    )

    card_debt = (
        db.query(func.coalesce(func.sum(FinancialAccount.current_balance), 0))
        .filter(
            FinancialAccount.organization_id == organization_id,
            FinancialAccount.deleted_at.is_(None),
            FinancialAccount.active.is_(True),
            FinancialAccount.type.notin_(ASSET_ACCOUNT_TYPES),
        )
        .scalar()
    )

    monthly_revenue = account_type_balance(db, organization_id, "REVENUE", start=month_start, end=today)
    monthly_expenses = account_type_balance(db, organization_id, "EXPENSE", start=month_start, end=today)

    # Mismo periodo del mes anterior (hasta el mismo día) para comparar peras con peras:
    # comparar 10 días de este mes contra 30 del anterior sería engañoso.
    previous_start = _shift_months(month_start, -1)
    previous_end = min(
        _shift_months(previous_start, 1) - timedelta(days=1),
        previous_start + (today - month_start),
    )
    previous_revenue = account_type_balance(db, organization_id, "REVENUE", start=previous_start, end=previous_end)
    previous_expenses = account_type_balance(db, organization_id, "EXPENSE", start=previous_start, end=previous_end)

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
        )
        .group_by(Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )

    return {
        "cash": Decimal(cash or 0),
        "card_debt": Decimal(card_debt or 0),
        "monthly_revenue": monthly_revenue,
        "monthly_expenses": monthly_expenses,
        "monthly_profit": monthly_revenue - monthly_expenses,
        "previous_revenue": previous_revenue,
        "previous_expenses": previous_expenses,
        "previous_profit": previous_revenue - previous_expenses,
        "previous_period_end": previous_end,
        "receivables": _outstanding(db, organization_id, Receivable),
        "overdue_receivables": _outstanding(db, organization_id, Receivable, overdue_only=True),
        "payables": _outstanding(db, organization_id, Payable),
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
