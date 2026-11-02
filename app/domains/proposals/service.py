"""Aprobación de propuestas: el ÚNICO puente de lo agéntico a lo real.

Aprobar re-valida el payload contra el schema Create vigente y ejecuta el
service normal (con sus validaciones, movimientos y asientos). El humano
que aprueba queda como created_by de la operación resultante, salvo en las
de autorización por monto: ahí el autor es quien capturó (`requested_by`) y
el autorizador queda como `reviewed_by`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.events import event_bus
from app.domains.expenses.schemas import ExpenseCreate
from app.domains.expenses.service import create_expense, pay_expense
from app.domains.income.schemas import IncomeCreate
from app.domains.income.service import create_income
from app.domains.payables.schemas import PayableCreate
from app.domains.payables.service import create_payable, pay_payable
from app.domains.proposals.schemas import ExpensePaymentPayload, PayablePaymentPayload
from app.domains.receivables.schemas import ReceivableCreate
from app.domains.receivables.service import create_receivable
from app.domains.transactions.schemas import TransferCreate
from app.domains.transactions.service import create_transfer
from app.models.agent import AgentProposal
from app.models.expense import Expense
from app.models.payable import Payable
from app.services import approvals

SOURCE_APPROVAL = "approval"
SOURCE_ASSISTANT = "assistant"
SOURCE_SYSTEM = "system"
SOURCE_AGENT = "agent"
SOURCES = (SOURCE_APPROVAL, SOURCE_AGENT, SOURCE_ASSISTANT, SOURCE_SYSTEM)


def source_of(proposal: AgentProposal) -> str | None:
    """De dónde salió: la bandeja lo enseña y filtra por esto."""
    origin = proposal.origin or ""
    if origin.startswith(approvals.ORIGIN_PREFIX):
        return SOURCE_APPROVAL
    if origin.startswith("assistant:"):
        return SOURCE_ASSISTANT
    if origin.startswith("recurring:"):
        return SOURCE_SYSTEM
    if proposal.agent_key_id is not None:
        return SOURCE_AGENT
    return None


def _pay_expense(db: Session, org_id: str, payload: ExpensePaymentPayload, user_id: str) -> Expense:
    expense = (
        db.query(Expense)
        .filter(Expense.id == payload.expense_id, Expense.organization_id == org_id)
        .first()
    )
    if expense is None:
        raise ValueError("El gasto que se iba a pagar ya no existe.")
    return pay_expense(db, org_id, expense, payload.financial_account_id, payload.date, user_id)


def _pay_payable(db: Session, org_id: str, payload: PayablePaymentPayload, user_id: str) -> Payable:
    payable = (
        db.query(Payable)
        .filter(Payable.id == payload.payable_id, Payable.organization_id == org_id)
        .first()
    )
    if payable is None:
        raise ValueError("La cuenta por pagar ya no existe.")
    return pay_payable(db, org_id, payable, payload.amount, payload.financial_account_id, payload.date, user_id)


def _transfer(db: Session, org_id: str, payload: TransferCreate, user_id: str):
    # El resultado es el movimiento de salida; la entrada comparte su grupo.
    return create_transfer(db, org_id, payload, user_id)[0]


_EXECUTORS = {
    "INCOME": (IncomeCreate, create_income),
    "EXPENSE": (ExpenseCreate, create_expense),
    "RECEIVABLE": (ReceivableCreate, create_receivable),
    "PAYABLE": (PayableCreate, create_payable),
    "EXPENSE_PAYMENT": (ExpensePaymentPayload, _pay_expense),
    "PAYABLE_PAYMENT": (PayablePaymentPayload, _pay_payable),
    "TRANSFER": (TransferCreate, _transfer),
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

    # Lo capturado por una persona se registra a su nombre; lo propuesto por
    # un agente, a nombre de quien lo aprueba.
    author = proposal.requested_by or user_id
    try:
        entity = create_fn(db, org_id, payload, author)
    except ValueError:
        # Cuenta inactiva, CxP ya pagada, mes cerrado...: la propuesta sigue
        # viva y nada a medias se queda en la sesión.
        db.rollback()
        raise

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
    if source_of(proposal) == SOURCE_APPROVAL and not (reason or "").strip():
        raise ValueError("Escribe el motivo del rechazo: quien capturó debe saber por qué.")
    proposal.status = "REJECTED"
    proposal.reviewed_by = user_id
    proposal.reviewed_at = datetime.now(timezone.utc)
    proposal.rejection_reason = reason
    db.commit()
    db.refresh(proposal)
    event_bus.publish("proposal.rejected", {"proposal_id": proposal.id, "organization_id": org_id})
    return proposal
