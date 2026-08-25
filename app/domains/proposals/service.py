"""Aprobación de propuestas: el ÚNICO puente de lo agéntico a lo real.

Aprobar re-valida el payload contra el schema Create vigente y ejecuta el
service normal (con sus validaciones, movimientos y asientos). El humano
que aprueba queda como created_by de la operación resultante.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.events import event_bus
from app.domains.expenses.schemas import ExpenseCreate
from app.domains.expenses.service import create_expense
from app.domains.income.schemas import IncomeCreate
from app.domains.income.service import create_income
from app.domains.payables.schemas import PayableCreate
from app.domains.payables.service import create_payable
from app.domains.receivables.schemas import ReceivableCreate
from app.domains.receivables.service import create_receivable
from app.models.agent import AgentProposal
from pydantic import ValidationError

_EXECUTORS = {
    "INCOME": (IncomeCreate, create_income),
    "EXPENSE": (ExpenseCreate, create_expense),
    "RECEIVABLE": (ReceivableCreate, create_receivable),
    "PAYABLE": (PayableCreate, create_payable),
}


def approve_proposal(db: Session, org_id: str, proposal: AgentProposal, user_id: str) -> AgentProposal:
    if proposal.status != "PROPOSED":
        raise ValueError("Esta propuesta ya fue revisada.")
    executor = _EXECUTORS.get(proposal.kind)
    if executor is None:
        raise ValueError("Tipo de propuesta desconocido.")
    schema, create_fn = executor

    try:
        payload = schema.model_validate(proposal.payload)
    except ValidationError as exc:
        raise ValueError(
            "La propuesta ya no es válida: " + "; ".join(e["msg"] for e in exc.errors()[:3])
        )

    entity = create_fn(db, org_id, payload, user_id)

    proposal.status = "APPROVED"
    proposal.reviewed_by = user_id
    proposal.reviewed_at = datetime.now(timezone.utc)
    proposal.result_id = entity.id
    db.commit()
    db.refresh(proposal)
    event_bus.publish("proposal.approved", {"proposal_id": proposal.id, "organization_id": org_id})
    return proposal


def reject_proposal(
    db: Session, org_id: str, proposal: AgentProposal, user_id: str, reason: str | None
) -> AgentProposal:
    if proposal.status != "PROPOSED":
        raise ValueError("Esta propuesta ya fue revisada.")
    proposal.status = "REJECTED"
    proposal.reviewed_by = user_id
    proposal.reviewed_at = datetime.now(timezone.utc)
    proposal.rejection_reason = reason
    db.commit()
    db.refresh(proposal)
    event_bus.publish("proposal.rejected", {"proposal_id": proposal.id, "organization_id": org_id})
    return proposal
