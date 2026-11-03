from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.financial_accounts import settlements
from app.domains.financial_accounts.schemas import (
    FinancialAccountCreate,
    FinancialAccountRead,
    FinancialAccountUpdate,
    SettlementCreate,
    SettlementRead,
)
from app.domains.financial_accounts.service import create_financial_account, validate_settlement_account
from app.domains.opening import service as opening_service
from app.domains.opening.schemas import AccountOpeningAdjustment
from app.models.financial_account import FinancialAccount
from app.models.organization import ACCOUNTING_ROLES, ROLE_ADMIN, ROLE_OWNER, WRITE_ROLES
from app.models.user import User
from app.schemas.common import paginate
from app.security.deps import get_current_org_id, get_current_user, require_role
from app.services.change_log import record_change, snapshot
from app.services.dimensions import validate_dimensions

router = APIRouter(prefix="/accounts", tags=["accounts"])

# Liquidar y cancelar liquidaciones mueve dinero entre instrumentos y toca
# resultados: lo hacen quienes administran la empresa.
SETTLEMENT_ROLES = (ROLE_OWNER, ROLE_ADMIN)


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
        business_unit_id=payload.business_unit_id,
        fee_rate=payload.fee_rate,
        settlement_days=payload.settlement_days,
        settlement_account_id=payload.settlement_account_id,
    )
    record_change(db, org_id, account, "CREATE", user.id)
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
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    account = _get_account(db, org_id, account_id)
    before = snapshot(account)
    changes = payload.model_dump(exclude_unset=True)
    validate_dimensions(db, org_id, changes.get("business_unit_id"), None)
    if changes.get("settlement_account_id"):
        validate_settlement_account(db, org_id, changes["settlement_account_id"])
    if account.type != "PROCESSOR":
        # Tasa, días y banco destino sólo tienen sentido en un procesador.
        for field in ("fee_rate", "settlement_days", "settlement_account_id"):
            changes.pop(field, None)
    for field, value in changes.items():
        setattr(account, field, value)
    record_change(db, org_id, account, "UPDATE", user.id, before=before, after=snapshot(account))
    db.commit()
    db.refresh(account)
    return FinancialAccountRead.model_validate(account)


@router.post("/{account_id}/opening-adjustment", response_model=FinancialAccountRead)
def adjust_opening(
    account_id: str,
    payload: AccountOpeningAdjustment,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(ACCOUNTING_ROLES)),
):
    """Corrige el saldo de apertura al corte: movimiento de ajuste + póliza contra 3901."""
    account = _get_account(db, org_id, account_id)
    try:
        opening_service.adjust_account_opening(
            db,
            org_id,
            account.id,
            target=payload.target_opening_balance,
            reason=payload.reason,
            status=payload.status,
            note=payload.note,
            user_id=user.id,
        )
    except ValueError:
        db.rollback()
        raise
    db.commit()
    db.refresh(account)
    return FinancialAccountRead.model_validate(account)


# --- Liquidaciones de procesadores (NetPay → banco) ---


def _processor_or_404(db: Session, org_id: str, account_id: str) -> FinancialAccount:
    try:
        return settlements.get_processor(db, org_id, account_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/{account_id}/settlements")
def list_settlements(
    account_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    processor = _processor_or_404(db, org_id, account_id)
    return paginate(settlements.settlements_query(db, org_id, processor.id), limit, offset, SettlementRead)


@router.post("/{account_id}/settlements", response_model=SettlementRead, status_code=201)
def create_settlement(
    account_id: str,
    payload: SettlementCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(SETTLEMENT_ROLES)),
):
    processor = _processor_or_404(db, org_id, account_id)
    try:
        settlement = settlements.create_settlement(
            db,
            org_id,
            processor,
            date=payload.date,
            gross_amount=payload.gross_amount,
            fee_amount=payload.fee_amount,
            bank_account_id=payload.bank_account_id,
            reference=payload.reference,
            notes=payload.notes,
            user_id=user.id,
        )
    except settlements.SettlementConflictError as error:
        raise HTTPException(status_code=409, detail=str(error))
    db.commit()
    db.refresh(settlement)
    return SettlementRead.model_validate(settlement)


@router.delete("/{account_id}/settlements/{settlement_id}", response_model=SettlementRead)
def cancel_settlement(
    account_id: str,
    settlement_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(SETTLEMENT_ROLES)),
):
    processor = _processor_or_404(db, org_id, account_id)
    try:
        settlement = settlements.get_settlement(db, org_id, processor.id, settlement_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))
    settlement = settlements.cancel_settlement(db, org_id, settlement, user.id)
    db.commit()
    db.refresh(settlement)
    return SettlementRead.model_validate(settlement)
