from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.periods import service
from app.models.organization import ACCOUNTING_ROLES
from app.models.user import User
from app.security.deps import get_current_org_id, get_current_user, require_role

router = APIRouter(prefix="/periods", tags=["periods"])


class PeriodAction(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    notes: str | None = Field(default=None, max_length=1000)


class PeriodReopen(PeriodAction):
    # Reabrir un mes declarado exige explicar por qué: el motivo queda guardado.
    reason: str = Field(min_length=3, max_length=500)


@router.get("")
def list_periods(
    months: int = Query(default=12, ge=1, le=36),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    items = service.list_periods(db, org_id, months)
    return {"items": items, "total": len(items), "limit": len(items), "offset": 0}


@router.post("/close")
def close_period(
    payload: PeriodAction,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _role: None = Depends(require_role(ACCOUNTING_ROLES)),
):
    try:
        lock = service.close_period(
            db, org_id, payload.year, payload.month, user_id=user.id, notes=payload.notes
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"year": lock.year, "month": lock.month, "closed": True}


@router.post("/reopen")
def reopen_period(
    payload: PeriodReopen,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _role: None = Depends(require_role(ACCOUNTING_ROLES)),
):
    try:
        lock = service.reopen_period(
            db, org_id, payload.year, payload.month, payload.reason, user_id=user.id
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"year": lock.year, "month": lock.month, "closed": False}
