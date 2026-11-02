from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.proposals import service
from app.models.agent import AgentKey, AgentProposal
from app.models.organization import WRITE_ROLES
from app.models.user import User
from app.security.deps import get_current_org_id, get_current_user, require_role
from app.services import approvals

router = APIRouter(prefix="/proposals", tags=["proposals"])


class ProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    payload: dict[str, Any]
    summary: str
    evidence: str | None
    status: str
    rejection_reason: str | None
    result_id: str | None
    created_at: datetime
    agent_name: str | None = None
    # approval | agent | assistant | system: de dónde salió (ver service.source_of).
    source: str | None = None
    # Quién capturó la operación que espera autorización.
    requested_by_name: str | None = None


class ProposalReject(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


def _source_filter(source: str):
    """Mismo criterio que `service.source_of`, expresado como filtro SQL."""
    if source == service.SOURCE_APPROVAL:
        return AgentProposal.origin.like(f"{approvals.ORIGIN_PREFIX}%")
    if source == service.SOURCE_ASSISTANT:
        return AgentProposal.origin.like("assistant:%")
    if source == service.SOURCE_SYSTEM:
        return AgentProposal.origin.like("recurring:%")
    return AgentProposal.agent_key_id.isnot(None)


def _get_proposal(db: Session, org_id: str, proposal_id: str) -> AgentProposal:
    proposal = (
        db.query(AgentProposal)
        .filter(AgentProposal.id == proposal_id, AgentProposal.organization_id == org_id)
        .first()
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="La propuesta no existe.")
    return proposal


@router.get("")
def list_proposals(
    status: str | None = Query(default=None, pattern="^(PROPOSED|APPROVED|REJECTED)$"),
    source: str | None = Query(default=None, pattern="^(approval|agent|assistant|system)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    query = db.query(AgentProposal).filter(AgentProposal.organization_id == org_id)
    if status:
        query = query.filter(AgentProposal.status == status)
    if source:
        query = query.filter(_source_filter(source))
    query = query.order_by(
        case((AgentProposal.status == "PROPOSED", 0), else_=1),
        AgentProposal.created_at.desc(),
    )
    total = query.count()
    rows = query.limit(limit).offset(offset).all()
    key_names = {
        key.id: key.name
        for key in db.query(AgentKey).filter(AgentKey.organization_id == org_id).all()
    }
    requester_ids = {row.requested_by for row in rows if row.requested_by}
    requester_names = (
        {uid: name for uid, name in db.query(User.id, User.name).filter(User.id.in_(requester_ids)).all()}
        if requester_ids
        else {}
    )
    items = []
    for row in rows:
        item = ProposalRead.model_validate(row)
        item.source = service.source_of(row)
        item.requested_by_name = requester_names.get(row.requested_by)
        # Sin llave y con origen recurrente, propuso el sistema: la bandeja
        # debe decir quién, igual que con cualquier agente.
        if row.agent_key_id is None and (row.origin or "").startswith("recurring:"):
            item.agent_name = "ONE Finance · Recurrentes"
        else:
            item.agent_name = key_names.get(row.agent_key_id)
        items.append(item)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/pending-count")
def pending_count(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    pending = db.query(AgentProposal).filter(
        AgentProposal.organization_id == org_id, AgentProposal.status == "PROPOSED"
    )
    # El badge cuenta todo; `approval` deja a Gastos y Por pagar avisar
    # "N operaciones esperan autorización".
    return {
        "count": pending.count(),
        "approval": pending.filter(_source_filter(service.SOURCE_APPROVAL)).count(),
    }


@router.post("/{proposal_id}/approve", response_model=ProposalRead)
def approve(
    proposal_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    membership=Depends(require_role(WRITE_ROLES)),
):
    proposal = _get_proposal(db, org_id, proposal_id)
    approvals.ensure_can_review(db, membership, proposal)
    proposal = service.approve_proposal(db, org_id, proposal, user.id)
    return ProposalRead.model_validate(proposal)


@router.post("/{proposal_id}/reject", response_model=ProposalRead)
def reject(
    proposal_id: str,
    payload: ProposalReject,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    membership=Depends(require_role(WRITE_ROLES)),
):
    proposal = _get_proposal(db, org_id, proposal_id)
    approvals.ensure_can_review(db, membership, proposal)
    proposal = service.reject_proposal(db, org_id, proposal, user.id, payload.reason)
    return ProposalRead.model_validate(proposal)
