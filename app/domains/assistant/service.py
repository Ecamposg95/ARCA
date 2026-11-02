"""Conversaciones del asistente (spec 2026-11-02 §API).

Persiste turnos vía el runtime, toma el candado de la conversación
(`busy_since`) y resuelve acciones delegando en el service de propuestas:
aprobar desde el chat ES aprobar en la bandeja.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domains.proposals import service as proposals
from app.models.agent import AgentProposal
from app.models.assistant import AiUsage, AssistantAction, AssistantConversation, AssistantMessage
from app.models.organization import Organization, OrganizationMember
from app.models.user import User
from app.services.ai import budget as budget_service
from app.services.ai import runtime
from app.services.ai.client import api_key_present
from app.services.ai.prompt import model_display_name

# Un turno que lleve más de esto se considera muerto (proceso caído) y el candado se libera.
STALE_SECONDS = 180


class ConversationBusy(Exception):
    """Ya hay un turno en curso en esta conversación."""


class ActionAlreadyResolved(Exception):
    """La acción ya no está pendiente."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --- Estado --------------------------------------------------------------


def status(db: Session, organization: Organization) -> dict:
    settings = get_settings()
    budget = budget_service.budget_status(db, organization)
    if not api_key_present():
        available, reason = False, "sin_llave"
    elif not organization.ai_enabled:
        available, reason = False, "deshabilitado"
    elif budget.exhausted:
        available, reason = False, "sin_presupuesto"
    else:
        available, reason = True, None
    return {
        "available": available,
        "reason": reason,
        "model": settings.ai_model,
        "model_name": model_display_name(settings.ai_model),
        "budget_usd": budget.budget_usd,
        "spent_usd": budget.spent_usd,
        "remaining_usd": budget.remaining_usd,
    }


# --- Conversaciones ------------------------------------------------------


def create_conversation(db: Session, org_id: str, user_id: str) -> AssistantConversation:
    conv = AssistantConversation(organization_id=org_id, user_id=user_id)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def list_conversations(db: Session, org_id: str, user_id: str, limit: int, offset: int):
    query = db.query(AssistantConversation).filter_by(organization_id=org_id, user_id=user_id)
    total = query.count()
    rows = (
        query.order_by(AssistantConversation.updated_at.desc(), AssistantConversation.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return rows, total


def get_conversation(db: Session, org_id: str, user_id: str, conv_id: str) -> AssistantConversation | None:
    """Sólo el dueño de la conversación, dentro de la empresa activa."""
    return db.query(AssistantConversation).filter_by(id=conv_id, organization_id=org_id, user_id=user_id).first()


def is_busy(conv: AssistantConversation) -> bool:
    since = _aware(conv.busy_since)
    return since is not None and (_now() - since).total_seconds() < STALE_SECONDS


def delete_conversation(db: Session, conv: AssistantConversation) -> None:
    if is_busy(conv):
        raise ConversationBusy()
    db.delete(conv)
    db.commit()


def _take_turn(db: Session, conv: AssistantConversation) -> None:
    """Candado atómico (UPDATE condicional): dos envíos simultáneos no corren dos loops."""
    now = _now()
    limit = now - timedelta(seconds=STALE_SECONDS)
    updated = (
        db.query(AssistantConversation)
        .filter(
            AssistantConversation.id == conv.id,
            or_(AssistantConversation.busy_since.is_(None), AssistantConversation.busy_since < limit),
        )
        .update({"busy_since": now}, synchronize_session=False)
    )
    db.commit()
    if updated != 1:
        raise ConversationBusy()
    db.refresh(conv)


def _release_turn(db: Session, conv: AssistantConversation) -> None:
    db.rollback()
    conv.busy_since = None
    conv.updated_at = _now()
    db.commit()


def send_message(
    db: Session,
    *,
    user: User,
    membership: OrganizationMember,
    organization: Organization,
    conv: AssistantConversation,
    text: str,
    client,
) -> runtime.TurnResult:
    _take_turn(db, conv)
    try:
        # Sin presupuesto no se persiste nada: el router lo convierte en 402.
        budget_service.ensure_budget(db, organization)
        result = runtime.run_turn(
            db, user=user, membership=membership, organization=organization, conversation=conv,
            user_text=text, client=client,
        )
        db.commit()
        return result
    finally:
        _release_turn(db, conv)


# --- Acciones ------------------------------------------------------------


def get_action(db: Session, org_id: str, user_id: str, action_id: str) -> AssistantAction | None:
    return (
        db.query(AssistantAction)
        .join(AssistantConversation, AssistantConversation.id == AssistantAction.conversation_id)
        .filter(
            AssistantAction.id == action_id,
            AssistantAction.organization_id == org_id,
            AssistantConversation.user_id == user_id,
        )
        .first()
    )


def resolve_action(db: Session, org_id: str, action: AssistantAction, user_id: str, *, approve: bool) -> AssistantAction:
    if action.status != "PENDING":
        raise ActionAlreadyResolved()
    proposal = db.get(AgentProposal, action.proposal_id) if action.proposal_id else None
    if proposal is None or proposal.organization_id != org_id:
        raise ValueError("La propuesta de esta acción ya no existe.")
    if proposal.status == "PROPOSED":
        if approve:
            proposals.approve_proposal(db, org_id, proposal, user_id)
        else:
            proposals.reject_proposal(db, org_id, proposal, user_id, "Rechazada desde el asistente")
    # Si la bandeja ya la resolvió, la acción sólo se pone al día.
    action.status = "APPROVED" if proposal.status == "APPROVED" else "REJECTED"
    action.resolved_at = _now()
    db.commit()
    db.refresh(action)
    return action


def visible_messages(conv: AssistantConversation) -> list[AssistantMessage]:
    """Los renglones de tool_result son para el API, no para la persona."""
    return [m for m in conv.messages if not runtime.is_tool_result_row(m)]


# --- Uso -----------------------------------------------------------------


def usage(db: Session, organization: Organization, month: str | None) -> dict:
    """Total y desglose por usuario y por día del mes `AAAA-MM` (default: el actual)."""
    if month:
        try:
            year, mon = (int(part) for part in month.split("-"))
            anchor = datetime(year, mon, 15, tzinfo=budget_service.MEXICO)
        except (TypeError, ValueError):
            raise ValueError("El mes debe tener formato AAAA-MM.")
    else:
        anchor = datetime.now(budget_service.MEXICO)
    start, end = budget_service.month_bounds(anchor)
    base = db.query(AiUsage).filter(
        AiUsage.organization_id == organization.id, AiUsage.created_at >= start, AiUsage.created_at < end
    )
    rows = base.order_by(AiUsage.created_at).all()
    total = sum((Decimal(r.cost_usd) for r in rows), Decimal("0"))

    names = {
        u.id: u.name
        for u in db.query(User).filter(User.id.in_({r.user_id for r in rows if r.user_id} or {""})).all()
    }
    by_user: dict[str, dict] = {}
    by_day: dict[str, dict] = {}
    for r in rows:
        ukey = r.user_id or "sistema"
        by_user.setdefault(ukey, {"key": ukey, "label": names.get(r.user_id, "ONE Finance"), "calls": 0, "cost_usd": Decimal("0")})
        by_user[ukey]["calls"] += 1
        by_user[ukey]["cost_usd"] += Decimal(r.cost_usd)
        day = _aware(r.created_at).astimezone(budget_service.MEXICO).date().isoformat()
        by_day.setdefault(day, {"key": day, "label": day, "calls": 0, "cost_usd": Decimal("0")})
        by_day[day]["calls"] += 1
        by_day[day]["cost_usd"] += Decimal(r.cost_usd)

    return {
        "month": anchor.astimezone(budget_service.MEXICO).strftime("%Y-%m"),
        "budget_usd": budget_service.budget_for(organization),
        "total_usd": total,
        "calls": len(rows),
        "by_user": sorted(by_user.values(), key=lambda x: x["cost_usd"], reverse=True),
        "by_day": sorted(by_day.values(), key=lambda x: x["key"]),
    }


def pending_count(db: Session, org_id: str, user_id: str) -> int:
    return (
        db.query(func.count(AssistantAction.id))
        .join(AssistantConversation, AssistantConversation.id == AssistantAction.conversation_id)
        .filter(AssistantAction.organization_id == org_id, AssistantConversation.user_id == user_id,
                AssistantAction.status == "PENDING")
        .scalar()
        or 0
    )
