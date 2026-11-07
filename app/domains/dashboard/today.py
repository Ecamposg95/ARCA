"""Inicio «Tablero del día»: cuánto dinero hay, qué hay que pagar esta semana,
qué espera autorización y cómo van las sucursales (Task 9).

Sólo lee. Las reglas vienen de la spec 2026-11-03 (Definiciones 3, 4 y 5).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.agent import AgentProposal
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
    "branches": "Cajas de sucursal",
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
        "branches": {"month": None, "origin": "live", "rows": []},
    }

