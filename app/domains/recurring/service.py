"""Recurrentes: ARCA propone lo que se repite; el humano sigue aprobando.

La generación es idempotente por (regla, AAAA-MM) vía `AgentProposal.origin`,
sin importar qué pasó con el borrador: si el humano lo rechazó, regenerar no
deshace esa decisión — el patrón de la depreciación.
"""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.events import event_bus
from app.models.agent import AgentProposal
from app.models.recurring import RecurringRule

# Nombre visible en la bandeja cuando propone el sistema, no una llave.
RECURRING_AUTHOR = "ARCA · Recurrentes"


def origin_key(rule_id: str, year: int, month: int) -> str:
    return f"recurring:{rule_id}:{year:04d}-{month:02d}"


def _draft_payload(rule: RecurringRule, year: int, month: int) -> dict:
    # El borrador se fecha el día de la regla, pero nunca en el futuro: una
    # póliza con fecha adelantada queda invisible hasta que llegue el día
    # (la lección de la depreciación).
    today = date_type.today()
    when = min(date_type(year, month, rule.day_of_month), today)

    payload: dict = {
        "date": when.isoformat(),
        "description": rule.description,
        "amount": str(Decimal(rule.amount)),
        "tax_rate": str(Decimal(rule.tax_rate)),
        "category_id": rule.category_id,
        # Con cuenta, se propone ya pagado desde ella; sin cuenta, por pagar.
        "status": "PAID" if rule.financial_account_id else "PENDING",
    }
    if rule.project_id:
        payload["project_id"] = rule.project_id
    if rule.financial_account_id:
        payload["financial_account_id"] = rule.financial_account_id
    if rule.kind == "INCOME" and rule.customer_id:
        payload["customer_id"] = rule.customer_id
    if rule.kind == "EXPENSE" and rule.vendor_id:
        payload["vendor_id"] = rule.vendor_id
    return payload


def generate_drafts(db: Session, organization_id: str, year: int, month: int) -> dict:
    """Un borrador por regla activa que aún no tenga el suyo este mes."""
    today = date_type.today()
    if (year, month) > (today.year, today.month):
        raise ValueError(
            f"{month:02d}/{year} todavía no llega. Los borradores se generan "
            "cuando el mes ya corre."
        )

    rules = (
        db.query(RecurringRule)
        .filter(
            RecurringRule.organization_id == organization_id,
            RecurringRule.status == "ACTIVE",
        )
        .order_by(RecurringRule.day_of_month, RecurringRule.created_at)
        .all()
    )
    existing = {
        origin
        for (origin,) in db.query(AgentProposal.origin).filter(
            AgentProposal.organization_id == organization_id,
            AgentProposal.origin.in_([origin_key(rule.id, year, month) for rule in rules]),
        )
        if origin
    }

    generated: list[dict] = []
    for rule in rules:
        key = origin_key(rule.id, year, month)
        if key in existing:
            continue
        proposal = AgentProposal(
            organization_id=organization_id,
            agent_key_id=None,  # propone el sistema, no una llave
            kind=rule.kind,
            payload=_draft_payload(rule, year, month),
            summary=f"{rule.description} · {month:02d}/{year}",
            evidence=f"Regla recurrente: se repite el día {rule.day_of_month} de cada mes.",
            origin=key,
        )
        db.add(proposal)
        db.flush()
        generated.append({"proposal_id": proposal.id, "rule_id": rule.id})
        event_bus.publish(
            "proposal.created",
            {"proposal_id": proposal.id, "organization_id": organization_id},
        )

    db.commit()
    return {
        "period": f"{year:04d}-{month:02d}",
        "generated": len(generated),
        "drafts": generated,
    }


def pending_count(db: Session, organization_id: str, year: int, month: int) -> int:
    """Reglas activas que aún no tienen borrador este mes: el aviso de la UI."""
    rules = (
        db.query(RecurringRule.id)
        .filter(
            RecurringRule.organization_id == organization_id,
            RecurringRule.status == "ACTIVE",
        )
        .all()
    )
    if not rules:
        return 0
    keys = [origin_key(rule_id, year, month) for (rule_id,) in rules]
    existing = (
        db.query(AgentProposal.origin)
        .filter(
            AgentProposal.organization_id == organization_id,
            AgentProposal.origin.in_(keys),
        )
        .count()
    )
    return len(keys) - existing


def has_generated(db: Session, organization_id: str, rule_id: str) -> bool:
    return (
        db.query(AgentProposal.id)
        .filter(
            AgentProposal.organization_id == organization_id,
            AgentProposal.origin.like(f"recurring:{rule_id}:%"),
        )
        .first()
        is not None
    )
