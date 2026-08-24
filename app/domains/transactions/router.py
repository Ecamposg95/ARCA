from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.organization import WRITE_ROLES
from app.models.transaction import FinancialTransaction
from app.models.user import User
from app.schemas.common import paginate
from app.security.deps import get_current_org_id, get_current_user, require_role
from app.services.accounting.rules import transfer_entry
from app.services.transactions import get_locked_account, record_transaction

router = APIRouter(prefix="/transactions", tags=["transactions"])


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    financial_account_id: str
    transaction_type: str
    amount: Decimal
    currency: str
    date: date_type
    description: str
    reference: str | None
    status: str
    source_type: str | None
    source_id: str | None
    created_at: datetime


class TransferCreate(BaseModel):
    from_account_id: str
    to_account_id: str
    amount: Decimal = Field(gt=0, allow_inf_nan=False)
    date: date_type
    description: str | None = Field(default=None, max_length=500)


@router.get("")
def list_transactions(
    account_id: str | None = None,
    transaction_type: str | None = None,
    start: date_type | None = None,
    end: date_type | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    query = db.query(FinancialTransaction).filter(FinancialTransaction.organization_id == org_id)
    if account_id:
        query = query.filter(FinancialTransaction.financial_account_id == account_id)
    if transaction_type:
        query = query.filter(FinancialTransaction.transaction_type == transaction_type)
    if start:
        query = query.filter(FinancialTransaction.date >= start)
    if end:
        query = query.filter(FinancialTransaction.date <= end)
    query = query.order_by(FinancialTransaction.date.desc(), FinancialTransaction.created_at.desc())
    return paginate(query, limit, offset, TransactionRead)


@router.post("/transfer", response_model=list[TransactionRead], status_code=201)
def create_transfer(
    payload: TransferCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    if payload.from_account_id == payload.to_account_id:
        raise ValueError("Elige dos cuentas distintas para el traspaso.")

    origin = get_locked_account(db, org_id, payload.from_account_id)
    destination = get_locked_account(db, org_id, payload.to_account_id)
    description = payload.description or f"Traspaso de {origin.name} a {destination.name}"
    group_id = str(uuid4())

    outgoing = record_transaction(
        db,
        organization_id=org_id,
        financial_account_id=origin.id,
        transaction_type="TRANSFER_OUT",
        amount=payload.amount,
        date=payload.date,
        description=description,
        source_type="transfer",
        transfer_group_id=group_id,
        created_by=user.id,
    )
    incoming = record_transaction(
        db,
        organization_id=org_id,
        financial_account_id=destination.id,
        transaction_type="TRANSFER_IN",
        amount=payload.amount,
        date=payload.date,
        description=description,
        source_type="transfer",
        transfer_group_id=group_id,
        created_by=user.id,
    )
    transfer_entry(
        db,
        org_id,
        description=description,
        amount=payload.amount,
        date=payload.date,
        from_account_name=origin.name,
        to_account_name=destination.name,
        source_id=group_id,
        created_by=user.id,
    )
    db.commit()
    db.refresh(outgoing)
    db.refresh(incoming)
    return [TransactionRead.model_validate(outgoing), TransactionRead.model_validate(incoming)]
