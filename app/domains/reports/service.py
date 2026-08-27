"""Reportes financieros — SIEMPRE derivados del ledger, nunca almacenados."""

from __future__ import annotations

from datetime import date as date_type
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.accounting import Account, DEBIT_NORMAL_TYPES, JournalEntry, JournalEntryLine
from app.models.financial_account import FinancialAccount
from app.models.transaction import INFLOW_TYPES, FinancialTransaction
from app.services.accounting.engine import account_type_balance


def _lines_by_account(
    db: Session,
    organization_id: str,
    account_types: tuple[str, ...],
    start: date_type | None = None,
    end: date_type | None = None,
) -> list[dict]:
    query = (
        db.query(
            Account.code,
            Account.name,
            Account.type,
            func.coalesce(func.sum(JournalEntryLine.debit), 0).label("debit"),
            func.coalesce(func.sum(JournalEntryLine.credit), 0).label("credit"),
        )
        .join(JournalEntryLine, JournalEntryLine.account_id == Account.id)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .filter(
            Account.organization_id == organization_id,
            JournalEntry.status == "POSTED",
            Account.type.in_(account_types),
        )
        .group_by(Account.code, Account.name, Account.type)
        .order_by(Account.code)
    )
    if start is not None:
        query = query.filter(JournalEntry.date >= start)
    if end is not None:
        query = query.filter(JournalEntry.date <= end)

    rows = []
    for code, name, account_type, debit, credit in query.all():
        debit = Decimal(debit or 0)
        credit = Decimal(credit or 0)
        balance = debit - credit if account_type in DEBIT_NORMAL_TYPES else credit - debit
        if balance == 0:
            continue
        rows.append({"code": code, "name": name, "type": account_type, "amount": balance})
    return rows


def profit_loss(db: Session, organization_id: str, start: date_type, end: date_type) -> dict:
    revenue_lines = _lines_by_account(db, organization_id, ("REVENUE",), start, end)
    expense_lines = _lines_by_account(db, organization_id, ("EXPENSE",), start, end)
    total_revenue = sum((row["amount"] for row in revenue_lines), Decimal("0"))
    total_expenses = sum((row["amount"] for row in expense_lines), Decimal("0"))
    return {
        "start": start,
        "end": end,
        "revenue": revenue_lines,
        "expenses": expense_lines,
        "total_revenue": total_revenue,
        "total_expenses": total_expenses,
        "net_profit": total_revenue - total_expenses,
    }


def balance_sheet(db: Session, organization_id: str, as_of: date_type) -> dict:
    assets = _lines_by_account(db, organization_id, ("ASSET",), end=as_of)
    liabilities = _lines_by_account(db, organization_id, ("LIABILITY",), end=as_of)
    equity = _lines_by_account(db, organization_id, ("EQUITY",), end=as_of)

    total_assets = sum((row["amount"] for row in assets), Decimal("0"))
    total_liabilities = sum((row["amount"] for row in liabilities), Decimal("0"))
    total_equity_accounts = sum((row["amount"] for row in equity), Decimal("0"))

    # Resultado del ejercicio (ingresos - gastos) vive en capital hasta el cierre.
    revenue = account_type_balance(db, organization_id, "REVENUE", end=as_of)
    expenses = account_type_balance(db, organization_id, "EXPENSE", end=as_of)
    period_result = revenue - expenses
    if period_result != 0:
        equity = [*equity, {"code": "3999", "name": "Resultado del periodo", "type": "EQUITY", "amount": period_result}]
    total_equity = total_equity_accounts + period_result

    return {
        "as_of": as_of,
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_equity": total_equity,
        "balanced": total_assets == total_liabilities + total_equity,
    }


def cash_flow(db: Session, organization_id: str, start: date_type, end: date_type) -> dict:
    def _flows(until: date_type | None, since: date_type | None) -> tuple[Decimal, Decimal]:
        query = db.query(
            FinancialTransaction.transaction_type,
            func.coalesce(func.sum(FinancialTransaction.amount), 0),
        ).filter(
            FinancialTransaction.organization_id == organization_id,
            FinancialTransaction.status == "ACTIVE",
        )
        if since is not None:
            query = query.filter(FinancialTransaction.date >= since)
        if until is not None:
            query = query.filter(FinancialTransaction.date <= until)
        inflows = Decimal("0")
        outflows = Decimal("0")
        for transaction_type, amount in query.group_by(FinancialTransaction.transaction_type).all():
            if transaction_type in INFLOW_TYPES:
                inflows += Decimal(amount or 0)
            else:
                outflows += Decimal(amount or 0)
        return inflows, outflows

    opening_from_accounts = (
        db.query(func.coalesce(func.sum(FinancialAccount.opening_balance), 0))
        .filter(
            FinancialAccount.organization_id == organization_id,
            FinancialAccount.deleted_at.is_(None),
        )
        .scalar()
    )
    inflows_before, outflows_before = _flows(until=None, since=None)
    # opening = saldos iniciales + neto de movimientos ANTERIORES al periodo
    inflows_pre, outflows_pre = _flows(until=None, since=start)
    net_before_period = (inflows_before - outflows_before) - (inflows_pre - outflows_pre)
    opening_cash = Decimal(opening_from_accounts or 0) + net_before_period

    inflows, outflows = _flows(until=end, since=start)
    return {
        "start": start,
        "end": end,
        "opening_cash": opening_cash,
        "inflows": inflows,
        "outflows": outflows,
        "closing_cash": opening_cash + inflows - outflows,
    }


def vat_report(db: Session, organization_id: str, start: date_type, end: date_type) -> dict:
    """IVA del periodo por flujo de efectivo: sólo lo cobrado y lo pagado se declara."""
    from app.services.accounting.coa import (
        CODE_VAT_CHARGED_COLLECTED,
        CODE_VAT_CHARGED_PENDING,
        CODE_VAT_CREDITABLE_PAID,
        CODE_VAT_CREDITABLE_PENDING,
    )

    def movement(code: str, since: date_type | None, until: date_type) -> Decimal:
        """Saldo neto de una cuenta de IVA en el periodo (naturaleza de la cuenta)."""
        query = (
            db.query(
                func.coalesce(func.sum(JournalEntryLine.debit), 0),
                func.coalesce(func.sum(JournalEntryLine.credit), 0),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .join(Account, Account.id == JournalEntryLine.account_id)
            .filter(
                JournalEntry.organization_id == organization_id,
                JournalEntry.status == "POSTED",
                Account.code == code,
                JournalEntry.date <= until,
            )
        )
        if since is not None:
            query = query.filter(JournalEntry.date >= since)
        debit, credit = query.one()
        debit, credit = Decimal(debit or 0), Decimal(credit or 0)
        # 2190/2191 son pasivo (naturaleza acreedora); 1190/1191 activo (deudora).
        return credit - debit if code.startswith("2") else debit - credit

    charged = movement(CODE_VAT_CHARGED_COLLECTED, start, end)
    creditable = movement(CODE_VAT_CREDITABLE_PAID, start, end)
    difference = charged - creditable

    return {
        "start": start,
        "end": end,
        "vat_charged": charged,
        "vat_creditable": creditable,
        "difference": difference,
        "to_pay": difference if difference > 0 else Decimal("0"),
        "in_favor": -difference if difference < 0 else Decimal("0"),
        # Informativos: aún no se declaran porque no se han cobrado/pagado.
        "vat_pending_collection": movement(CODE_VAT_CHARGED_PENDING, None, end),
        "vat_pending_payment": movement(CODE_VAT_CREDITABLE_PENDING, None, end),
    }


def cash_projection(db: Session, organization_id: str, days: int = 90) -> dict:
    """Proyección de liquidez con lo YA comprometido: no es un pronóstico.

    Parte del efectivo de hoy y camina hacia adelante sumando los cobros
    esperados y restando los pagos comprometidos en su fecha de vencimiento.
    Lo vencido se considera exigible de inmediato.
    """
    from datetime import timedelta

    from app.models.financial_account import ASSET_ACCOUNT_TYPES, FinancialAccount
    from app.models.payable import Payable
    from app.models.receivable import Receivable

    today = date_type.today()
    horizon = today + timedelta(days=days)

    opening = Decimal(
        db.query(func.coalesce(func.sum(FinancialAccount.current_balance), 0))
        .filter(
            FinancialAccount.organization_id == organization_id,
            FinancialAccount.deleted_at.is_(None),
            FinancialAccount.active.is_(True),
            FinancialAccount.type.in_(ASSET_ACCOUNT_TYPES),
        )
        .scalar()
        or 0
    )

    def pending(model, sign: int) -> list[tuple[date_type, Decimal, str]]:
        rows = (
            db.query(model.due_date, model.amount, model.amount_paid, model.description)
            .filter(
                model.organization_id == organization_id,
                model.status.in_(("OPEN", "PARTIAL")),
                model.due_date <= horizon,
            )
            .all()
        )
        items = []
        for due_date, amount, paid, description in rows:
            balance = Decimal(amount) - Decimal(paid)
            if balance <= 0:
                continue
            # Lo vencido ya es exigible: se coloca en el día de hoy.
            when = max(due_date, today)
            items.append((when, balance * sign, description))
        return items

    movements = pending(Receivable, 1) + pending(Payable, -1)
    movements.sort(key=lambda item: item[0])

    balance = opening
    points: list[dict] = [{"date": today, "balance": balance, "change": Decimal("0")}]
    shortfall: date_type | None = None
    inflows = Decimal("0")
    outflows = Decimal("0")

    for when, change, _description in movements:
        balance += change
        if change > 0:
            inflows += change
        else:
            outflows += -change
        if shortfall is None and balance < 0:
            shortfall = when
        points.append({"date": when, "balance": balance, "change": change})

    return {
        "start": today,
        "end": horizon,
        "opening_cash": opening,
        "expected_inflows": inflows,
        "expected_outflows": outflows,
        "projected_cash": balance,
        # El día en que el dinero no alcanza: la alerta que nadie más da.
        "shortfall_date": shortfall,
        "points": points,
    }


# Tramos de antigüedad medidos desde el vencimiento. "Por vencer" es lo que
# todavía no es exigible: mezclarlo con lo vencido esconde el problema real.
AGING_BUCKETS = (
    ("Por vencer", 0),
    ("1-30", 30),
    ("31-60", 60),
    ("61-90", 90),
    ("+90", None),
)


def _average_days_as_of(
    db: Session,
    organization_id: str,
    model,
    collection_type: str,
    as_of: date_type,
) -> int | None:
    """Antigüedad promedio como estaba la cartera en `as_of`.

    Se reconstruye desde los movimientos: el saldo de entonces es el monto menos
    los cobros con fecha ≤ as_of. Una cuenta ya liquidada hoy cuenta si estaba
    abierta entonces; una emitida después, no existe en la foto.
    """
    from datetime import datetime, time, timezone

    from app.models.transaction import FinancialTransaction

    as_of_end = datetime.combine(as_of, time.max, tzinfo=timezone.utc)

    rows = (
        db.query(model.id, model.due_date, model.amount, model.cancelled_at)
        .filter(
            model.organization_id == organization_id,
            model.date <= as_of,
        )
        .all()
    )
    if not rows:
        # Sin cartera entonces no hay base: None, que no es lo mismo que 0 días.
        return None

    collected = dict(
        db.query(
            FinancialTransaction.source_id,
            func.coalesce(func.sum(FinancialTransaction.amount), 0),
        )
        .filter(
            FinancialTransaction.organization_id == organization_id,
            FinancialTransaction.transaction_type == collection_type,
            FinancialTransaction.status == "ACTIVE",
            FinancialTransaction.date <= as_of,
        )
        .group_by(FinancialTransaction.source_id)
        .all()
    )

    weighted = Decimal("0")
    total = Decimal("0")
    for row_id, due_date, amount, cancelled_at in rows:
        if cancelled_at is not None:
            cancelled = cancelled_at if cancelled_at.tzinfo else cancelled_at.replace(tzinfo=timezone.utc)
            if cancelled <= as_of_end:
                continue
        balance = Decimal(amount) - Decimal(collected.get(row_id, 0))
        if balance <= 0:
            continue
        days_late = max((as_of - due_date).days, 0)
        weighted += Decimal(days_late) * balance
        total += balance

    return int(weighted / total) if total > 0 else None


def aging_report(db: Session, organization_id: str, kind: str = "receivable") -> dict:
    """Antigüedad de saldos por contraparte, más los días promedio de cobro.

    `kind` es "receivable" (quién te debe) o "payable" (a quién le debes). Los
    tramos se miden desde el vencimiento: lo que aún no vence cae en 0-30 con
    días 0, porque todavía no es antigüedad.
    """
    from app.models.contact import Customer, Vendor
    from app.models.payable import Payable
    from app.models.receivable import Receivable

    if kind == "payable":
        model, contact_model, contact_field = Payable, Vendor, Payable.vendor_id
    else:
        model, contact_model, contact_field = Receivable, Customer, Receivable.customer_id

    today = date_type.today()

    rows = (
        db.query(
            contact_field,
            contact_model.name,
            model.due_date,
            model.date,
            model.amount,
            model.amount_paid,
        )
        .join(contact_model, contact_model.id == contact_field)
        .filter(
            model.organization_id == organization_id,
            model.status.in_(("OPEN", "PARTIAL")),
        )
        .all()
    )

    by_contact: dict[str, dict] = {}
    totals = {label: Decimal("0") for label, _limit in AGING_BUCKETS}
    grand_total = Decimal("0")
    overdue_total = Decimal("0")
    # Para el DSO: suma ponderada de (días de antigüedad × saldo).
    weighted_days = Decimal("0")

    for contact_id, contact_name, due_date, _issued, amount, paid in rows:
        balance = Decimal(amount) - Decimal(paid)
        if balance <= 0:
            continue

        days_late = max((today - due_date).days, 0)
        label = next(
            name for name, limit in AGING_BUCKETS if limit is None or days_late <= limit
        )

        entry = by_contact.setdefault(
            contact_id,
            {
                "contact_id": contact_id,
                "name": contact_name,
                "total": Decimal("0"),
                "oldest_days": 0,
                **{name: Decimal("0") for name, _limit in AGING_BUCKETS},
            },
        )
        entry[label] += balance
        entry["total"] += balance
        entry["oldest_days"] = max(entry["oldest_days"], days_late)

        totals[label] += balance
        grand_total += balance
        weighted_days += Decimal(days_late) * balance
        if days_late > 0:
            overdue_total += balance

    contacts = sorted(by_contact.values(), key=lambda item: item["total"], reverse=True)
    average_days = int(weighted_days / grand_total) if grand_total > 0 else 0

    collection_type = "PAYABLE_PAYMENT" if kind == "payable" else "RECEIVABLE_COLLECTION"
    previous_average_days = _average_days_as_of(
        db, organization_id, model, collection_type, today - timedelta(days=30)
    )

    return {
        "as_of": today,
        "kind": kind,
        "buckets": [name for name, _limit in AGING_BUCKETS],
        "contacts": contacts,
        "totals": totals,
        "total": grand_total,
        "overdue": overdue_total,
        # Días promedio ponderados por saldo: cuánto tarda en promedio tu dinero.
        "average_days": average_days,
        # La misma métrica hace 30 días: sin comparación, un número es un adorno.
        "previous_average_days": previous_average_days,
    }


def net_worth(db: Session, organization_id: str, months: int = 12) -> dict:
    """Patrimonio neto: lo que tienes menos lo que debes, y cómo ha evolucionado.

    Es el Balance General dicho en el idioma del dueño. Los saldos se toman del
    libro al cierre de cada mes, así que cuadran con la contabilidad por
    construcción — no son una tabla paralela.
    """
    from calendar import monthrange

    today = date_type.today()

    def month_end(offset: int) -> date_type:
        index = today.year * 12 + (today.month - 1) - offset
        year, month = divmod(index, 12)
        month += 1
        last_day = monthrange(year, month)[1]
        # El mes en curso se corta hoy: proyectar al día 31 inventaría saldos.
        return min(date_type(year, month, last_day), today)

    def snapshot(as_of: date_type) -> tuple[Decimal, Decimal]:
        assets = account_type_balance(db, organization_id, "ASSET", end=as_of)
        liabilities = account_type_balance(db, organization_id, "LIABILITY", end=as_of)
        return assets, liabilities

    series = []
    for offset in range(months - 1, -1, -1):
        as_of = month_end(offset)
        assets, liabilities = snapshot(as_of)
        series.append(
            {
                "month": as_of.strftime("%Y-%m"),
                "assets": assets,
                "liabilities": liabilities,
                "net_worth": assets - liabilities,
            }
        )

    current = balance_sheet(db, organization_id, today)
    net = Decimal(current["total_assets"]) - Decimal(current["total_liabilities"])

    previous = series[-2]["net_worth"] if len(series) > 1 else Decimal("0")
    change = net - Decimal(previous)

    return {
        "as_of": today,
        "assets": current["assets"],
        "liabilities": current["liabilities"],
        "total_assets": current["total_assets"],
        "total_liabilities": current["total_liabilities"],
        "net_worth": net,
        "change_vs_previous_month": change,
        "series": series,
    }


def cash_series(db: Session, organization_id: str, days: int = 90) -> dict:
    """La historia diaria del efectivo, reconstruida hacia atrás desde hoy.

    Se parte del saldo ACTUAL de las cuentas de activo —la cifra que el usuario
    puede verificar a ojo en su tablero— y se desanda con los movimientos por
    día. Así el último punto siempre cuadra con la realidad, y cualquier error
    quedaría en el pasado remoto, no en el número que importa.

    Las tarjetas no participan: son deuda, y mezclarlas dibujaría una curva de
    "efectivo" que nadie tiene.
    """
    from datetime import timedelta

    from app.models.financial_account import ASSET_ACCOUNT_TYPES, FinancialAccount
    from app.models.transaction import INFLOW_TYPES, FinancialTransaction

    today = date_type.today()
    start = today - timedelta(days=days - 1)

    accounts = (
        db.query(FinancialAccount)
        .filter(
            FinancialAccount.organization_id == organization_id,
            FinancialAccount.deleted_at.is_(None),
            FinancialAccount.active.is_(True),
            FinancialAccount.type.in_(ASSET_ACCOUNT_TYPES),
        )
        .order_by(FinancialAccount.created_at)
        .all()
    )
    account_ids = [account.id for account in accounts]

    # Un solo query agrupado por (cuenta, día): alimenta la curva global y las
    # sparklines por cuenta sin N consultas.
    rows = (
        db.query(
            FinancialTransaction.financial_account_id,
            FinancialTransaction.date,
            FinancialTransaction.transaction_type,
            func.coalesce(func.sum(FinancialTransaction.amount), 0),
        )
        .filter(
            FinancialTransaction.organization_id == organization_id,
            FinancialTransaction.financial_account_id.in_(account_ids or [""]),
            FinancialTransaction.date >= start,
        )
        .group_by(
            FinancialTransaction.financial_account_id,
            FinancialTransaction.date,
            FinancialTransaction.transaction_type,
        )
        .all()
    )

    per_account_delta: dict[str, dict[date_type, Decimal]] = {aid: {} for aid in account_ids}
    inflows_by_day: dict[date_type, Decimal] = {}
    outflows_by_day: dict[date_type, Decimal] = {}
    for account_id, day, tx_type, amount in rows:
        amount = Decimal(amount)
        signed = amount if tx_type in INFLOW_TYPES else -amount
        per_account_delta[account_id][day] = (
            per_account_delta[account_id].get(day, Decimal("0")) + signed
        )
        if tx_type in INFLOW_TYPES:
            inflows_by_day[day] = inflows_by_day.get(day, Decimal("0")) + amount
        else:
            outflows_by_day[day] = outflows_by_day.get(day, Decimal("0")) + amount

    day_list = [start + timedelta(days=offset) for offset in range(days)]

    def walk_back(current: Decimal, deltas: dict[date_type, Decimal]) -> list[Decimal]:
        balances: list[Decimal] = []
        running = current
        for day in reversed(day_list):
            balances.append(running)
            running -= deltas.get(day, Decimal("0"))
        balances.reverse()
        return balances

    total_now = sum((Decimal(a.current_balance) for a in accounts), Decimal("0"))
    total_deltas: dict[date_type, Decimal] = {}
    for deltas in per_account_delta.values():
        for day, value in deltas.items():
            total_deltas[day] = total_deltas.get(day, Decimal("0")) + value
    balances = walk_back(total_now, total_deltas)

    points = [
        {
            "date": day,
            "balance": balance,
            "inflow": inflows_by_day.get(day, Decimal("0")),
            "outflow": outflows_by_day.get(day, Decimal("0")),
        }
        for day, balance in zip(day_list, balances, strict=False)
    ]

    account_rows = []
    for account in accounts:
        series = walk_back(Decimal(account.current_balance), per_account_delta[account.id])
        account_rows.append(
            {
                "id": account.id,
                "name": account.name,
                "type": account.type,
                "balance": Decimal(account.current_balance),
                "series": series,
                "change": series[-1] - series[0],
            }
        )

    # Runway: cuántos meses aguanta el efectivo a la quema neta de los últimos
    # 90 días. Con flujo positivo no hay cuenta regresiva que inventar.
    burn_window = min(days, 90)
    window_start = today - timedelta(days=burn_window - 1)
    net = sum(
        (
            (p["inflow"] - p["outflow"])
            for p in points
            if p["date"] >= window_start
        ),
        Decimal("0"),
    )
    avg_monthly_burn = None
    runway_months = None
    if net < 0:
        avg_monthly_burn = (-net) * Decimal("30") / Decimal(burn_window)
        if avg_monthly_burn > 0:
            runway_months = total_now / avg_monthly_burn

    return {
        "start": start,
        "end": today,
        "points": points,
        "accounts": account_rows,
        "avg_monthly_burn": avg_monthly_burn,
        "runway_months": (
            runway_months.quantize(Decimal("0.1")) if runway_months is not None else None
        ),
    }


def category_series(db: Session, organization_id: str, months: int = 6) -> dict:
    """Gasto pagado por categoría y mes, SIN IVA — consistente con el P&L."""
    from app.models.category import Category
    from app.models.expense import Expense

    today = date_type.today()
    index = today.year * 12 + (today.month - 1) - (months - 1)
    year, month = divmod(index, 12)
    start = date_type(year, month + 1, 1)

    month_expr = (
        func.strftime("%Y-%m", Expense.date)
        if db.bind.dialect.name == "sqlite"
        else func.to_char(Expense.date, "YYYY-MM")
    ).label("month")
    rows = (
        db.query(
            Category.name,
            month_expr,
            func.coalesce(func.sum(Expense.subtotal), 0),
        )
        .join(Category, Category.id == Expense.category_id)
        .filter(
            Expense.organization_id == organization_id,
            Expense.status == "PAID",
            Expense.date >= start,
        )
        .group_by(Category.name, month_expr)
        .all()
    )

    month_keys = []
    for offset in range(months):
        idx = start.year * 12 + (start.month - 1) + offset
        y, m = divmod(idx, 12)
        month_keys.append(f"{y:04d}-{m + 1:02d}")

    categories = sorted({name for name, _month, _amount in rows})
    by_month: dict[str, dict] = {key: {"month": key} for key in month_keys}
    for name, month_key, amount in rows:
        if month_key in by_month:
            by_month[month_key][name] = Decimal(amount)
    for key in month_keys:
        for name in categories:
            by_month[key].setdefault(name, Decimal("0"))

    return {"categories": categories, "points": [by_month[key] for key in month_keys]}
