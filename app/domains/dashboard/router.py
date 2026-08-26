from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.dashboard import service
from app.security.deps import get_current_org_id

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    return service.summary(db, org_id)


@router.get("/cash-flow")
def dashboard_cash_flow(
    granularity: str = Query(default="month", pattern="^(month|week)$"),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    return service.cash_flow_series(db, org_id, granularity)
