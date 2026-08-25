from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.financial_accounts.schemas import (
    FinancialAccountCreate,
    FinancialAccountRead,
    FinancialAccountUpdate,
)
from app.domains.financial_accounts.service import create_financial_account
from app.models.financial_account import FinancialAccount
from app.models.organization import WRITE_ROLES
from app.models.user import User
from app.security.deps import get_current_org_id, get_current_user, require_role

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _get_account(db: Session, org_id: str, account_id: str) -> FinancialAccount:
    account = (
        db.query(FinancialAccount)
        .filter(
            FinancialAccount.id == account_id,
            FinancialAccount.organization_id == org_id,
            FinancialAccount.deleted_at.is_(None),
        )
        .first()
    )
    if account is None:
        raise HTTPException(status_code=404, detail="La cuenta de dinero no existe.")
    return account


@router.get("", response_model=list[FinancialAccountRead])
def list_accounts(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    accounts = (
        db.query(FinancialAccount)
        .filter(
            FinancialAccount.organization_id == org_id,
            FinancialAccount.deleted_at.is_(None),
        )
        .order_by(FinancialAccount.created_at)
        .all()
    )
    return [FinancialAccountRead.model_validate(account) for account in accounts]


@router.post("", response_model=FinancialAccountRead, status_code=201)
def create_account(
    payload: FinancialAccountCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    account = create_financial_account(
        db,
        organization_id=org_id,
        name=payload.name,
        account_type=payload.type,
        opening_balance=payload.opening_balance,
        institution=payload.institution,
        last_four=payload.last_four,
        credit_limit=payload.credit_limit,
        created_by=user.id,
    )
    db.commit()
    db.refresh(account)
    return FinancialAccountRead.model_validate(account)


@router.get("/{account_id}", response_model=FinancialAccountRead)
def get_account(
    account_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    return FinancialAccountRead.model_validate(_get_account(db, org_id, account_id))


@router.patch("/{account_id}", response_model=FinancialAccountRead)
def update_account(
    account_id: str,
    payload: FinancialAccountUpdate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    account = _get_account(db, org_id, account_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    db.commit()
    db.refresh(account)
    return FinancialAccountRead.model_validate(account)
