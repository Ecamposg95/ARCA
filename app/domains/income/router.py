from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.income import service
from app.domains.income.schemas import IncomeCancel, IncomeCreate, IncomePay, IncomeRead
from app.models.income import Income
from app.models.organization import WRITE_ROLES
from app.models.user import User
from app.schemas.common import paginate
from app.security.deps import get_current_org_id, get_current_user, require_role

router = APIRouter(prefix="/income", tags=["income"])


def _get_income(db: Session, org_id: str, income_id: str) -> Income:
    income = (
        db.query(Income)
        .filter(Income.id == income_id, Income.organization_id == org_id)
        .first()
    )
    if income is None:
        raise HTTPException(status_code=404, detail="El ingreso no existe.")
    return income


@router.get("")
def list_income(
    status: str | None = Query(default=None, pattern="^(PENDING|PAID|CANCELLED)$"),
    start: date_type | None = None,
    end: date_type | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    query = db.query(Income).filter(Income.organization_id == org_id)
    if status:
        query = query.filter(Income.status == status)
    if start:
        query = query.filter(Income.date >= start)
    if end:
        query = query.filter(Income.date <= end)
    query = query.order_by(Income.date.desc(), Income.created_at.desc())
    return paginate(query, limit, offset, IncomeRead, sum_column=Income.amount)


@router.post("", response_model=IncomeRead, status_code=201)
def create_income(
    payload: IncomeCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    income = service.create_income(db, org_id, payload, created_by=user.id)
    return IncomeRead.model_validate(income)


@router.get("/{income_id}", response_model=IncomeRead)
def get_income(
    income_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    return IncomeRead.model_validate(_get_income(db, org_id, income_id))


@router.post("/{income_id}/pay", response_model=IncomeRead)
def pay_income(
    income_id: str,
    payload: IncomePay,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    income = _get_income(db, org_id, income_id)
    income = service.pay_income(db, org_id, income, payload.financial_account_id, payload.date, user.id)
    return IncomeRead.model_validate(income)


@router.post("/{income_id}/cancel", response_model=IncomeRead)
def cancel_income(
    income_id: str,
    payload: IncomeCancel,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    income = _get_income(db, org_id, income_id)
    income = service.cancel_income(db, income, user.id, payload.reason)
    return IncomeRead.model_validate(income)
