"""API del asistente ONE Finance sobre Claude (spec 2026-11-02 §API).

El cliente de Anthropic entra por una dependencia (`get_ai_client`) para que
las pruebas lo sustituyan por uno falso; sin llave la dependencia devuelve
None y los envíos responden 503 sin tocar la BD.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.assistant import service
from app.domains.assistant.schemas import (
    ActionRead,
    AssistantStatus,
    ConversationLite,
    ConversationRead,
    MessageRead,
    MessageSend,
    StepRead,
    UsageRead,
)
from app.models.agent import AgentProposal
from app.models.assistant import AssistantAction, AssistantConversation, AssistantMessage
from app.models.organization import ROLE_ADMIN, ROLE_OWNER, WRITE_ROLES, Organization, OrganizationMember
from app.models.user import User
from app.security.deps import get_current_membership, get_current_org_id, get_current_user, require_role
from app.services.ai import budget as budget_service
from app.services.ai.client import build_client

router = APIRouter(prefix="/assistant", tags=["assistant"])

SIN_LLAVE = "El asistente se activa cuando se conecte la llave de Claude."


def get_ai_client():
    """None sin llave. Las pruebas la sobreescriben con un cliente falso."""
    return build_client()


def _organization(db: Session, org_id: str) -> Organization:
    return db.get(Organization, org_id)


def _conversation(db: Session, org_id: str, user: User, conv_id: str) -> AssistantConversation:
    conv = service.get_conversation(db, org_id, user.id, conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="La conversación no existe.")
    return conv


def _action_out(db: Session, action: AssistantAction) -> ActionRead:
    out = ActionRead.model_validate(action)
    if action.proposal_id:
        proposal = db.get(AgentProposal, action.proposal_id)
        out.proposal_kind = proposal.kind if proposal else None
    return out


def _message_out(db: Session, m: AssistantMessage) -> MessageRead:
    return MessageRead(
        id=m.id,
        role=m.role,
        text=m.text,
        steps=[StepRead(**s) for s in (m.steps or [])],
        actions=[_action_out(db, a) for a in m.actions],
        stop_reason=m.stop_reason,
        input_tokens=m.input_tokens,
        output_tokens=m.output_tokens,
        cost_usd=m.cost_usd or 0,
        created_at=m.created_at,
    )


def _conversation_out(db: Session, conv: AssistantConversation) -> ConversationRead:
    return ConversationRead(
        id=conv.id,
        title=conv.title,
        busy=service.is_busy(conv),
        messages=[_message_out(db, m) for m in service.visible_messages(conv)],
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.get("/status", response_model=AssistantStatus)
def assistant_status(db: Session = Depends(get_db), org_id: str = Depends(get_current_org_id)):
    return AssistantStatus(**service.status(db, _organization(db, org_id)))


@router.get("/conversations")
def list_conversations(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
):
    rows, total = service.list_conversations(db, org_id, user.id, limit, offset)
    return {
        "items": [ConversationLite.model_validate(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/conversations", response_model=ConversationLite, status_code=status.HTTP_201_CREATED)
def create_conversation(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
):
    return ConversationLite.model_validate(service.create_conversation(db, org_id, user.id))


@router.get("/conversations/{conv_id}", response_model=ConversationRead)
def read_conversation(
    conv_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
):
    return _conversation_out(db, _conversation(db, org_id, user, conv_id))


@router.delete("/conversations/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conv_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
):
    conv = _conversation(db, org_id, user, conv_id)
    try:
        service.delete_conversation(db, conv)
    except service.ConversationBusy:
        raise HTTPException(status_code=409, detail="El asistente sigue trabajando en esta conversación.")


@router.post("/conversations/{conv_id}/messages", response_model=MessageRead)
def send_message(
    conv_id: str,
    payload: MessageSend,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    membership: OrganizationMember = Depends(get_current_membership),
    client=Depends(get_ai_client),
):
    conv = _conversation(db, org_id, user, conv_id)
    organization = _organization(db, org_id)
    if client is None:
        raise HTTPException(status_code=503, detail=SIN_LLAVE)
    if not organization.ai_enabled:
        raise HTTPException(status_code=503, detail="El asistente está desactivado en esta empresa.")
    try:
        result = service.send_message(
            db, user=user, membership=membership, organization=organization, conv=conv, text=payload.text,
            client=client,
        )
    except service.ConversationBusy:
        raise HTTPException(status_code=409, detail="El asistente sigue trabajando en esta conversación; espera a que termine.")
    except budget_service.BudgetExhausted as exc:
        raise HTTPException(status_code=402, detail=str(exc))
    return _message_out(db, result.final)


def _action(db: Session, org_id: str, user: User, action_id: str) -> AssistantAction:
    action = service.get_action(db, org_id, user.id, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="La acción no existe.")
    return action


def _resolve(db, org_id, user, action_id, approve: bool) -> ActionRead:
    action = _action(db, org_id, user, action_id)
    try:
        action = service.resolve_action(db, org_id, action, user.id, approve=approve)
    except service.ActionAlreadyResolved:
        raise HTTPException(status_code=409, detail="Esta propuesta ya fue resuelta.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _action_out(db, action)


@router.post("/actions/{action_id}/approve", response_model=ActionRead)
def approve_action(
    action_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    return _resolve(db, org_id, user, action_id, approve=True)


@router.post("/actions/{action_id}/reject", response_model=ActionRead)
def reject_action(
    action_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    return _resolve(db, org_id, user, action_id, approve=False)


@router.get("/usage", response_model=UsageRead)
def usage(
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _membership=Depends(require_role((ROLE_OWNER, ROLE_ADMIN))),
):
    try:
        return UsageRead(**service.usage(db, _organization(db, org_id), month))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
