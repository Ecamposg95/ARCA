from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.dashboard import service, today
from app.domains.dashboard.schemas import DashboardToday
from app.models.organization import OrganizationMember
from app.security.deps import get_current_membership, get_current_org_id

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary(
    business_unit_id: str | None = Query(default=None),
    fiscal_entity_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    return service.summary(db, org_id, business_unit_id=business_unit_id, fiscal_entity_id=fiscal_entity_id)


@router.get("/cash-flow")
def dashboard_cash_flow(
    granularity: str = Query(default="month", pattern="^(month|week)$"),
    business_unit_id: str | None = Query(default=None),
    fiscal_entity_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    return service.cash_flow_series(
        db, org_id, granularity, business_unit_id=business_unit_id, fiscal_entity_id=fiscal_entity_id
    )


@router.get("/today", response_model=DashboardToday)
def dashboard_today(
    week_of: date | None = Query(default=None),
    business_unit_id: str | None = Query(default=None),
    fiscal_entity_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    membership: OrganizationMember = Depends(get_current_membership),  # todos los roles
):
    return today.today(
        db,
        org_id,
        membership,
        week_of=week_of,
        business_unit_id=business_unit_id or None,
        fiscal_entity_id=fiscal_entity_id or None,
    )
