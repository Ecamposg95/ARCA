"""Inicio «Tablero del día»: cuánto dinero hay, qué hay que pagar esta semana,
qué espera autorización y cómo van las sucursales (Task 9).

Sólo lee. Las reglas vienen de la spec 2026-11-03 (Definiciones 3, 4 y 5).
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.analytics.series import sales_by_unit_day
from app.models.agent import AgentProposal
from app.models.business_unit import BusinessUnit
from app.models.cash_cut import CashCut
from app.models.contact import Vendor
from app.models.financial_account import FinancialAccount
from app.models.organization import OPENING_CONFIRMED, OPENING_PROVISIONAL, Organization, OrganizationMember
from app.models.payable import Payable
from app.models.transaction import INFLOW_TYPES, FinancialTransaction
from app.models.user import User
from app.services import approvals

ZERO = Decimal("0.00")
ROW_LABELS = {
    "central": "Caja central",
    "branches": "Cajas sucursal",
    "banks": "Bancos",
    "processor": "En tránsito",
}


def _money(value) -> Decimal:
    return Decimal(value or 0).quantize(ZERO)


def previous_business_day(day: date) -> date:
    """El día hábil anterior: un lunes (o fin de semana) compara contra el viernes."""
    previous = day - timedelta(days=1)
    while previous.weekday() >= 5:
        previous -= timedelta(days=1)
    return previous


def _group_of(account: FinancialAccount) -> str | None:
    if account.type == "CASH":
        return "branches" if account.business_unit_id else "central"
    if account.type in ("BANK", "OTHER"):
        return "banks"
    if account.type == "PROCESSOR":
        return "processor"
    return None


def money_panel(db: Session, organization: Organization, business_unit_id: str | None, today: date) -> dict:
    query = db.query(FinancialAccount).filter(
        FinancialAccount.organization_id == organization.id,
        FinancialAccount.active.is_(True),
        FinancialAccount.deleted_at.is_(None),
    )
    if business_unit_id:
        query = query.filter(FinancialAccount.business_unit_id == business_unit_id)
    accounts = [account for account in query.all() if _group_of(account) is not None]

    groups: dict[str, list[FinancialAccount]] = {key: [] for key in ROW_LABELS}
    for account in accounts:
        groups[_group_of(account)].append(account)
    provisional_company = organization.opening_status == OPENING_PROVISIONAL

    def status(key: str) -> str | None:
        members = groups[key]
        if not members:
            return None
        if key == "branches":
            return "TO_COLLECT"
        if key == "processor":
            return "TO_DEPOSIT"
        if provisional_company and any(account.opening_status != OPENING_CONFIRMED for account in members):
            return "PROVISIONAL"
        return "CONFIRMED"

    amounts = {key: _money(sum((Decimal(a.current_balance or 0) for a in members), Decimal("0"))) for key, members in groups.items()}
    rows = [{"key": key, "label": ROW_LABELS[key], "amount": amounts[key], "status": status(key)} for key in ROW_LABELS]
    total = _money(sum(amounts.values(), Decimal("0")))
    in_transit = amounts["processor"]

    # Cierre del día hábil anterior = saldo actual − lo que se movió después de ese día.
    account_ids = [account.id for account in accounts]
    moved_since = Decimal("0")
    if account_ids:
        rows_since = (
            db.query(FinancialTransaction.transaction_type, func.coalesce(func.sum(FinancialTransaction.amount), 0))
            .filter(
                FinancialTransaction.organization_id == organization.id,
                FinancialTransaction.financial_account_id.in_(account_ids),
                FinancialTransaction.status == "ACTIVE",
                FinancialTransaction.date > previous_business_day(today),
            )
            .group_by(FinancialTransaction.transaction_type)
            .all()
        )
        for kind, amount in rows_since:
            moved_since += Decimal(amount or 0) if kind in INFLOW_TYPES else -Decimal(amount or 0)
    previous_close = _money(total - moved_since)

    settlements = [
        {
            "account": account.name,
            "amount": _money(account.current_balance),
            "expected_on": today + timedelta(days=account.settlement_days),
        }
        for account in groups["processor"]
        if account.settlement_days is not None and Decimal(account.current_balance or 0) > 0
    ]
    next_settlement = min(settlements, key=lambda s: (s["expected_on"], -s["amount"])) if settlements else None

    banks = [a for a in groups["banks"] if a.type == "BANK"]
    needs_opening = provisional_company and all(Decimal(a.current_balance or 0) == 0 for a in banks)

    return {
        "total": total,
        "available": _money(amounts["central"] + amounts["branches"] + amounts["banks"]),
        "in_transit": in_transit,
        "previous_close": previous_close,
        "delta": _money(total - previous_close),
        "rows": rows,
        "next_settlement": next_settlement,
        "needs_opening": needs_opening,
    }


def _pending_payment_proposals(db: Session, organization_id: str) -> dict[str, Decimal]:
    """payable_id → monto propuesto, para las propuestas PAYABLE_PAYMENT que esperan."""
    proposals = (
        db.query(AgentProposal)
        .filter(
            AgentProposal.organization_id == organization_id,
            AgentProposal.kind == "PAYABLE_PAYMENT",
            AgentProposal.status == "PROPOSED",
        )
        .all()
    )
    pending: dict[str, Decimal] = {}
    for proposal in proposals:
        payload = proposal.payload or {}
        payable_id = payload.get("payable_id")
        if payable_id:
            pending[payable_id] = pending.get(payable_id, Decimal("0")) + Decimal(str(payload.get("amount") or 0))
    return pending


def week_panel(
    db: Session,
    organization: Organization,
    week_of: date,
    money_total: Decimal,
    business_unit_id: str | None,
    fiscal_entity_id: str | None,
) -> dict:
    start = week_of - timedelta(days=week_of.weekday())
    end = start + timedelta(days=6)
    query = (
        db.query(Payable, Vendor.name)
        .join(Vendor, Vendor.id == Payable.vendor_id)
        .filter(
            Payable.organization_id == organization.id,
            Payable.status.in_(("OPEN", "PARTIAL")),
            Payable.due_date <= end,
        )
    )
    if business_unit_id:
        query = query.filter(Payable.business_unit_id == business_unit_id)
    if fiscal_entity_id:
        query = query.filter(Payable.fiscal_entity_id == fiscal_entity_id)
    payables = query.order_by(Payable.due_date, Payable.created_at).all()
    pending = _pending_payment_proposals(db, organization.id)

    days = {start + timedelta(days=i): {"date": start + timedelta(days=i), "amount": Decimal("0"), "pending_approval_amount": Decimal("0")} for i in range(7)}
    items = []
    running = money_total
    for payable, vendor_name in payables:
        balance = _money(Decimal(payable.amount or 0) - Decimal(payable.amount_paid or 0))
        if balance <= 0:
            continue
        if payable.id in pending:
            approval = "PENDING"
        elif approvals.reaches_threshold(organization, balance):
            approval = "REQUIRED"
        else:
            approval = None
        overdue = payable.due_date < start
        running -= balance
        day = days[start if overdue else payable.due_date]
        day["amount"] += balance
        if approval == "PENDING":
            day["pending_approval_amount"] += balance
        items.append(
            {
                "payable_id": payable.id,
                "due_date": payable.due_date,
                "overdue": overdue,
                "vendor": vendor_name,
                "description": payable.description,
                "amount": balance,
                "running_balance": _money(running),
                "approval": approval,
            }
        )
    return {
        "start": start,
        "end": end,
        "days": [{**day, "amount": _money(day["amount"]), "pending_approval_amount": _money(day["pending_approval_amount"])} for day in days.values()],
        "items": items,
        "total": _money(sum((item["amount"] for item in items), Decimal("0"))),
    }


def approvals_panel(db: Session, organization_id: str, membership: OrganizationMember) -> dict:
    rows = (
        db.query(AgentProposal, User.name)
        .outerjoin(User, User.id == AgentProposal.requested_by)
        .filter(
            AgentProposal.organization_id == organization_id,
            AgentProposal.status == "PROPOSED",
            AgentProposal.origin.like(f"{approvals.ORIGIN_PREFIX}%"),
        )
        .order_by(AgentProposal.created_at)
        .all()
    )
    pending = []
    for proposal, name in rows:
        amount = (proposal.payload or {}).get("amount")
        pending.append(
            {
                "proposal_id": proposal.id,
                "summary": proposal.summary,
                "amount": _money(Decimal(str(amount))) if amount is not None else None,
                "requested_by_name": name,
            }
        )
    return {"pending": pending, "can_authorize": approvals.can_authorize(membership)}


def today(
    db: Session,
    organization_id: str,
    membership: OrganizationMember,
    week_of: date | None,
    business_unit_id: str | None,
    fiscal_entity_id: str | None,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    organization = db.get(Organization, organization_id)
    money = money_panel(db, organization, business_unit_id, today)
    week = week_panel(db, organization, week_of or today, money["total"], business_unit_id, fiscal_entity_id)
    return {
        "money": money,
        "week": week,
        "approvals": approvals_panel(db, organization_id, membership),
        "branches": branches_panel(db, organization, today, business_unit_id, fiscal_entity_id),
    }


# --- Sucursales ---------------------------------------------------------------


def _months_back(month: date, months: int) -> date:
    year, m = month.year, month.month - months
    while m <= 0:
        year, m = year - 1, m + 12
    return date(year, m, 1)


def _month_end(month: date) -> date:
    return month.replace(day=calendar.monthrange(month.year, month.month)[1])


def _pct(current: Decimal, base: Decimal) -> Decimal:
    return ((current - base) / base * 100).quantize(ZERO, rounding=ROUND_HALF_UP)


def _local_date(moment: datetime, tz: str) -> date:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    try:
        zone = ZoneInfo(tz or "America/Mexico_City")
    except Exception:  # zona rara en BD: UTC antes que romper Inicio
        zone = timezone.utc
    return moment.astimezone(zone).date()


def _cut_status(db: Session, organization: Organization, units: list[BusinessUnit], day: date) -> dict[str, str]:
    """Definición 5: estado del corte de `day` para la caja de cada unidad."""
    accounts = (
        db.query(FinancialAccount)
        .filter(
            FinancialAccount.organization_id == organization.id,
            FinancialAccount.type == "CASH",
            FinancialAccount.active.is_(True),
            FinancialAccount.deleted_at.is_(None),
            FinancialAccount.business_unit_id.isnot(None),
        )
        .order_by(FinancialAccount.name)
        .all()
    )
    cash_by_unit: dict[str, FinancialAccount] = {}
    for account in accounts:
        cash_by_unit.setdefault(account.business_unit_id, account)
    account_ids = [account.id for account in cash_by_unit.values()]
    if not account_ids:
        return {unit.id: "NA" for unit in units}
    cuts = {
        cut.financial_account_id: cut
        for cut in db.query(CashCut)
        .filter(
            CashCut.organization_id == organization.id,
            CashCut.financial_account_id.in_(account_ids),
            CashCut.date == day,
            CashCut.status != "CANCELLED",
        )
        .order_by(CashCut.created_at)
        .all()
    }
    moved = {
        account_id
        for (account_id,) in db.query(FinancialTransaction.financial_account_id)
        .filter(
            FinancialTransaction.organization_id == organization.id,
            FinancialTransaction.financial_account_id.in_(account_ids),
            FinancialTransaction.status == "ACTIVE",
            FinancialTransaction.date == day,
        )
        .distinct()
        .all()
    }
    status: dict[str, str] = {}
    for unit in units:
        account = cash_by_unit.get(unit.id)
        if account is None:
            status[unit.id] = "NA"
            continue
        cut = cuts.get(account.id)
        if cut is not None and cut.delivered_at is not None:
            status[unit.id] = "DELIVERED" if _local_date(cut.delivered_at, organization.timezone) <= day else "LATE"
        elif account.id in moved:
            status[unit.id] = "MISSING"
        else:
            status[unit.id] = "NA"
    return status


def branches_panel(
    db: Session,
    organization: Organization,
    today: date,
    business_unit_id: str | None,
    fiscal_entity_id: str | None,
) -> dict:
    query = db.query(BusinessUnit).filter(BusinessUnit.organization_id == organization.id, BusinessUnit.active.is_(True))
    if business_unit_id:
        query = query.filter(BusinessUnit.id == business_unit_id)
    units = query.order_by(BusinessUnit.sort_order, BusinessUnit.name).all()
    month = today.replace(day=1)
    opening = organization.opening_date
    if not units:
        return {"month": month, "origin": "live", "rows": []}

    start = _months_back(month, 13)
    daily = sales_by_unit_day(db, organization.id, opening, start, today, fiscal_entity_id)
    by_unit_month: dict[str, dict[date, dict[date, Decimal]]] = defaultdict(lambda: defaultdict(dict))
    for (unit_id, day), amount in daily.items():
        by_unit_month[unit_id][day.replace(day=1)][day] = amount

    def tramo(unit_id: str, which: date, last_day: int) -> Decimal | None:
        """Venta de la unidad en `which` del día 1 al `last_day`; None si no hay dato."""
        days = by_unit_month.get(unit_id, {}).get(which)
        if not days:
            return None
        return sum((v for d, v in days.items() if d.day <= last_day), Decimal("0"))

    # Mes en curso vivo; si ninguna unidad vendió desde el corte, el último mes con histórico.
    live_from = max(month, opening) if opening else month
    has_live = any(day >= live_from and amount > 0 for (_, day), amount in daily.items())
    if has_live or opening is None:
        origin, ref_month, last_day = "live", month, today.day
    else:
        past = sorted({day.replace(day=1) for (_, day) in daily if day < month}, reverse=True)
        if past:
            origin, ref_month, last_day = "historical", past[0], _month_end(past[0]).day
        else:
            origin, ref_month, last_day = "live", month, today.day

    rows = []
    for unit in units:
        sales = tramo(unit.id, ref_month, last_day) or Decimal("0")
        delta_pct = delta_basis = None
        previous_year = tramo(unit.id, ref_month.replace(year=ref_month.year - 1), last_day)
        if previous_year:
            delta_pct, delta_basis = _pct(sales, previous_year), "previous_year"
        else:
            bases = []
            for back in range(1, 13):
                value = tramo(unit.id, _months_back(ref_month, back), last_day)
                if value:
                    bases.append(value)
                if len(bases) == 3:
                    break
            if bases:
                average = sum(bases, Decimal("0")) / len(bases)
                delta_pct, delta_basis = _pct(sales, average), "avg_3m"
        rows.append({"unit": unit, "sales": _money(sales), "delta_pct": delta_pct, "delta_basis": delta_basis})

    rows.sort(key=lambda r: (-r["sales"], r["unit"].sort_order, r["unit"].name))
    top = rows[0]["sales"] if rows and rows[0]["sales"] > 0 else None

    yesterday = today - timedelta(days=1)
    window_start = yesterday - timedelta(days=29)
    cut_status = _cut_status(db, organization, units, yesterday)

    result = []
    for row in rows:
        unit = row["unit"]
        days_with_data = sorted(day for (unit_id, day) in daily if unit_id == unit.id and window_start <= day <= yesterday)
        sparkline = []
        if days_with_data:
            cursor = days_with_data[0]
            while cursor <= yesterday:
                sparkline.append({"date": cursor, "value": _money(daily.get((unit.id, cursor), Decimal("0")))})
                cursor += timedelta(days=1)
        result.append(
            {
                "business_unit_id": unit.id,
                "name": unit.name,
                "sales": row["sales"],
                "share": (row["sales"] / top).quantize(ZERO, rounding=ROUND_HALF_UP) if top else ZERO,
                "delta_pct": row["delta_pct"],
                "delta_basis": row["delta_basis"],
                "sparkline": sparkline,
                "cut": cut_status.get(unit.id, "NA"),
            }
        )
    return {"month": ref_month, "origin": origin, "rows": result}

