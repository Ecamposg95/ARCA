from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.cash_cuts import service
from app.domains.cash_cuts.schemas import (
    CashCutCount,
    CashCutCreate,
    CashCutDeliver,
    CashCutRead,
    TodayCashRow,
)
from app.models.cash_cut import CashCut
from app.models.financial_account import FinancialAccount
from app.models.organization import ROLE_ADMIN, ROLE_OWNER, WRITE_ROLES, OrganizationMember
from app.models.user import User
from app.security.deps import get_current_org_id, get_current_user, require_role

router = APIRouter(prefix="/cash-cuts", tags=["cash-cuts"])

# Cancelar un corte revierte entrega y ajuste: lo hace quien administra.
CANCEL_ROLES = (ROLE_OWNER, ROLE_ADMIN)


def _reads(db: Session, org_id: str, cuts: list[CashCut]) -> list[CashCutRead]:
    """Serializa con nombres de caja, destino y personas en dos consultas, no una por fila."""
    if not cuts:
        return []
    account_ids = {cut.financial_account_id for cut in cuts} | {
        cut.delivered_to_account_id for cut in cuts if cut.delivered_to_account_id
    }
    user_ids = {cut.delivered_by for cut in cuts if cut.delivered_by} | {
        cut.received_by for cut in cuts if cut.received_by
    }
    accounts = dict(
        db.query(FinancialAccount.id, FinancialAccount.name)
        .filter(FinancialAccount.organization_id == org_id, FinancialAccount.id.in_(account_ids))
        .all()
    )
    users = dict(db.query(User.id, User.name).filter(User.id.in_(user_ids or [""])).all())
    items = []
    for cut in cuts:
        item = CashCutRead.model_validate(cut)
        item.account_name = accounts.get(cut.financial_account_id)
        item.delivered_to_account_name = accounts.get(cut.delivered_to_account_id)
        item.delivered_by_name = users.get(cut.delivered_by)
        item.received_by_name = users.get(cut.received_by)
        items.append(item)
    return items


def _read(db: Session, org_id: str, cut: CashCut) -> CashCutRead:
    return _reads(db, org_id, [cut])[0]


def _cut_or_404(db: Session, org_id: str, cut_id: str) -> CashCut:
    try:
        return service.get_cut(db, org_id, cut_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/today", response_model=list[TodayCashRow])
def today(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    rows = service.today_overview(db, org_id)
    return [
        TodayCashRow(**{**row, "cut": _read(db, org_id, row["cut"]) if row["cut"] is not None else None})
        for row in rows
    ]


@router.get("")
def list_cuts(
    account_id: str | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
    status: str | None = Query(default=None, max_length=20),
    business_unit_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    query = service.cuts_query(
        db,
        org_id,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        status=status,
        business_unit_id=business_unit_id,
    )
    # Sobre {items,total,limit,offset} a mano: los nombres de caja y personas
    # se completan en bloque sobre las filas de la página.
    total = query.count()
    rows = query.limit(limit).offset(offset).all()
    return {"items": _reads(db, org_id, rows), "total": total, "limit": limit, "offset": offset}


@router.get("/{cut_id}", response_model=CashCutRead)
def get_cut(
    cut_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    return _read(db, org_id, _cut_or_404(db, org_id, cut_id))


@router.post("", response_model=CashCutRead, status_code=201)
def create_cut(
    payload: CashCutCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    try:
        cut = service.create_cut(db, org_id, payload.financial_account_id, payload.date, user.id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except service.CashCutConflictError as error:
        raise HTTPException(status_code=409, detail=str(error))
    db.commit()
    db.refresh(cut)
    return _read(db, org_id, cut)


@router.post("/{cut_id}/count", response_model=CashCutRead)
def count_cut(
    cut_id: str,
    payload: CashCutCount,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    cut = _cut_or_404(db, org_id, cut_id)
    cut = service.count_cut(db, org_id, cut, payload.counted_amount, payload.explanation, user.id)
    db.commit()
    db.refresh(cut)
    return _read(db, org_id, cut)


@router.post("/{cut_id}/deliver", response_model=CashCutRead)
def deliver_cut(
    cut_id: str,
    payload: CashCutDeliver,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    cut = _cut_or_404(db, org_id, cut_id)
    cut = service.deliver_cut(db, org_id, cut, payload.delivered_amount, payload.delivered_to_account_id, user.id)
    db.commit()
    db.refresh(cut)
    return _read(db, org_id, cut)


@router.post("/{cut_id}/confirm-receipt", response_model=CashCutRead)
def confirm_receipt(
    cut_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    membership: OrganizationMember = Depends(require_role(WRITE_ROLES)),
):
    cut = _cut_or_404(db, org_id, cut_id)
    try:
        cut = service.confirm_receipt(db, org_id, cut, user.id, membership.role)
    except service.CashCutForbiddenError as error:
        raise HTTPException(status_code=403, detail=str(error))
    db.commit()
    db.refresh(cut)
    return _read(db, org_id, cut)


@router.delete("/{cut_id}", response_model=CashCutRead)
def cancel_cut(
    cut_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(CANCEL_ROLES)),
):
    cut = _cut_or_404(db, org_id, cut_id)
    cut = service.cancel_cut(db, org_id, cut, user.id)
    db.commit()
    db.refresh(cut)
    return _read(db, org_id, cut)
