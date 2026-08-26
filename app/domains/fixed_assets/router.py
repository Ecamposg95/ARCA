from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.fixed_assets import service
from app.domains.fixed_assets.schemas import (
    DepreciationRun,
    FixedAssetCreate,
    FixedAssetDispose,
    FixedAssetRead,
)
from app.models.fixed_asset import FixedAsset
from app.models.organization import WRITE_ROLES
from app.models.user import User
from app.security.deps import get_current_org_id, get_current_user, require_role

router = APIRouter(prefix="/fixed-assets", tags=["fixed-assets"])


def _read(asset: FixedAsset) -> dict:
    monthly = service.monthly_depreciation(asset)
    pending = service.remaining_to_depreciate(asset)
    months_remaining = int(pending / monthly) if monthly > 0 else 0
    return {
        **{c.name: getattr(asset, c.name) for c in asset.__table__.columns},
        "book_value": service.book_value(asset),
        "monthly_depreciation": monthly,
        "months_remaining": months_remaining,
    }


def _get_asset(db: Session, org_id: str, asset_id: str) -> FixedAsset:
    asset = (
        db.query(FixedAsset)
        .filter(FixedAsset.id == asset_id, FixedAsset.organization_id == org_id)
        .first()
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="El activo no existe.")
    return asset


@router.get("")
def list_assets(
    status: str | None = Query(default=None, pattern="^(ACTIVE|DISPOSED)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    query = db.query(FixedAsset).filter(FixedAsset.organization_id == org_id)
    if status:
        query = query.filter(FixedAsset.status == status)
    total = query.count()
    rows = query.order_by(FixedAsset.acquisition_date.desc()).limit(limit).offset(offset).all()
    return {
        "items": [_read(asset) for asset in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/summary")
def summary(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    return service.summary(db, org_id)


@router.post("", response_model=FixedAssetRead, status_code=201)
def create_asset(
    payload: FixedAssetCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _role: None = Depends(require_role(WRITE_ROLES)),
):
    try:
        asset = service.create_asset(
            db,
            org_id,
            name=payload.name,
            category=payload.category,
            acquisition_date=payload.acquisition_date,
            cost=payload.cost,
            useful_life_months=payload.useful_life_months,
            salvage_value=payload.salvage_value,
            tax_amount=payload.tax_amount,
            financial_account_id=payload.financial_account_id,
            vendor_id=payload.vendor_id,
            notes=payload.notes,
            user_id=user.id,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _read(asset)


@router.post("/depreciate")
def run_depreciation(
    payload: DepreciationRun,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _role: None = Depends(require_role(WRITE_ROLES)),
):
    try:
        return service.run_depreciation(db, org_id, payload.year, payload.month, user_id=user.id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/{asset_id}/dispose", response_model=FixedAssetRead)
def dispose(
    asset_id: str,
    payload: FixedAssetDispose,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _role: None = Depends(require_role(WRITE_ROLES)),
):
    asset = _get_asset(db, org_id, asset_id)
    if asset.status == "DISPOSED":
        raise HTTPException(status_code=400, detail="Este activo ya está dado de baja.")
    asset = service.dispose_asset(
        db, org_id, asset, payload.disposed_at or date.today(), user_id=user.id
    )
    return _read(asset)
