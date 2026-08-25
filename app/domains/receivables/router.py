from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.receivables import service
from app.domains.receivables.schemas import (
    CollectionCreate,
    DebtCancel,
    ReceivableCreate,
    ReceivableRead,
)
from app.models.organization import WRITE_ROLES
from app.models.receivable import Receivable
from app.models.user import User
from app.schemas.common import paginate
from app.security.deps import get_current_org_id, get_current_user, require_role

router = APIRouter(prefix="/receivables", tags=["receivables"])


def _get_receivable(db: Session, org_id: str, receivable_id: str) -> Receivable:
    receivable = (
        db.query(Receivable)
        .filter(Receivable.id == receivable_id, Receivable.organization_id == org_id)
        .first()
    )
    if receivable is None:
        raise HTTPException(status_code=404, detail="La cuenta por cobrar no existe.")
    return receivable


@router.get("")
def list_receivables(
    status: str | None = Query(default=None, pattern="^(OPEN|PARTIAL|PAID|CANCELLED|OVERDUE)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    query = db.query(Receivable).filter(Receivable.organization_id == org_id)
    if status == "OVERDUE":
        query = query.filter(
            Receivable.status.in_(("OPEN", "PARTIAL")),
            Receivable.due_date < date.today(),
        )
    elif status in ("OPEN", "PARTIAL"):
        query = query.filter(Receivable.status == status)
    elif status:
        query = query.filter(Receivable.status == status)
    query = query.order_by(Receivable.due_date.asc(), Receivable.created_at.desc())
    return paginate(query, limit, offset, ReceivableRead)


@router.post("", response_model=ReceivableRead, status_code=201)
def create_receivable(
    payload: ReceivableCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    receivable = service.create_receivable(db, org_id, payload, created_by=user.id)
    return ReceivableRead.model_validate(receivable)


@router.get("/{receivable_id}", response_model=ReceivableRead)
def get_receivable(
    receivable_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    return ReceivableRead.model_validate(_get_receivable(db, org_id, receivable_id))


@router.post("/{receivable_id}/collect", response_model=ReceivableRead)
def collect_receivable(
    receivable_id: str,
    payload: CollectionCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    receivable = _get_receivable(db, org_id, receivable_id)
    receivable = service.collect_receivable(
        db, org_id, receivable, payload.amount, payload.financial_account_id, payload.date, user.id
    )
    return ReceivableRead.model_validate(receivable)


@router.post("/{receivable_id}/cancel", response_model=ReceivableRead)
def cancel_receivable(
    receivable_id: str,
    payload: DebtCancel,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    receivable = _get_receivable(db, org_id, receivable_id)
    receivable = service.cancel_receivable(db, org_id, receivable, user.id, payload.reason)
    return ReceivableRead.model_validate(receivable)
