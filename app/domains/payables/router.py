from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.payables import service
from app.domains.payables.schemas import DebtCancel, PayableCreate, PayableRead, PaymentCreate
from app.models.contact import Vendor
from app.models.organization import WRITE_ROLES
from app.models.payable import Payable
from app.models.user import User
from app.schemas.common import apply_sort, paginate
from app.security.deps import get_current_org_id, get_current_user, require_role
from app.services import approvals

router = APIRouter(prefix="/payables", tags=["payables"])


def _get_payable(db: Session, org_id: str, payable_id: str) -> Payable:
    payable = (
        db.query(Payable)
        .filter(Payable.id == payable_id, Payable.organization_id == org_id)
        .first()
    )
    if payable is None:
        raise HTTPException(status_code=404, detail="La cuenta por pagar no existe.")
    return payable


@router.get("")
def list_payables(
    status: str | None = Query(default=None, pattern="^(OPEN|PARTIAL|PAID|CANCELLED|OVERDUE)$"),
    q: str | None = Query(default=None, max_length=200),
    business_unit_id: str | None = None,
    fiscal_entity_id: str | None = None,
    sort: str | None = Query(default=None, max_length=30),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    query = db.query(Payable).filter(Payable.organization_id == org_id)
    if business_unit_id:
        query = query.filter(Payable.business_unit_id == business_unit_id)
    if fiscal_entity_id:
        query = query.filter(Payable.fiscal_entity_id == fiscal_entity_id)
    if status == "OVERDUE":
        query = query.filter(
            Payable.status.in_(("OPEN", "PARTIAL")),
            Payable.due_date < date.today(),
        )
    elif status:
        query = query.filter(Payable.status == status)
    if q:
        query = query.filter(Payable.description.ilike(f"%{q}%"))
    query = apply_sort(
        query,
        sort,
        {"due_date": Payable.due_date, "date": Payable.date, "amount": Payable.amount},
        (Payable.due_date.asc(), Payable.created_at.desc()),
    )
    return paginate(query, limit, offset, PayableRead)


@router.post("", response_model=PayableRead, status_code=201)
def create_payable(
    payload: PayableCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    payable = service.create_payable(db, org_id, payload, created_by=user.id)
    return PayableRead.model_validate(payable)


@router.get("/{payable_id}", response_model=PayableRead)
def get_payable(
    payable_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    return PayableRead.model_validate(_get_payable(db, org_id, payable_id))


@router.post("/{payable_id}/pay", response_model=PayableRead)
def pay_payable(
    payable_id: str,
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    membership=Depends(require_role(WRITE_ROLES)),
):
    payable = _get_payable(db, org_id, payable_id)
    waiting = approvals.gate(
        db,
        membership=membership,
        user=user,
        amount=payload.amount,
        kind="PAYABLE_PAYMENT",
        payload={"payable_id": payable.id, **payload.model_dump(mode="json")},
        summary=_payment_summary(db, org_id, payable, payload.amount),
    )
    if waiting is not None:
        return JSONResponse(status_code=202, content=approvals.pending_body(db, waiting))
    payable = service.pay_payable(
        db, org_id, payable, payload.amount, payload.financial_account_id, payload.date, user.id
    )
    return PayableRead.model_validate(payable)


def _payment_summary(db: Session, org_id: str, payable: Payable, amount) -> str:
    row = (
        db.query(Vendor.name)
        .filter(Vendor.id == payable.vendor_id, Vendor.organization_id == org_id)
        .first()
    )
    recipient = f" a {row[0]}" if row else ""
    return f"Pago de {approvals.money(amount)}{recipient} · {payable.description}"


@router.post("/{payable_id}/cancel", response_model=PayableRead)
def cancel_payable(
    payable_id: str,
    payload: DebtCancel,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    payable = _get_payable(db, org_id, payable_id)
    payable = service.cancel_payable(db, org_id, payable, user.id, payload.reason)
    return PayableRead.model_validate(payable)
