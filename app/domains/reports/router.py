from datetime import date as date_type
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.reports import service
from app.security.deps import get_current_org_id

router = APIRouter(prefix="/reports", tags=["reports"])


def _default_month_range() -> tuple[date_type, date_type]:
    today = date.today()
    return today.replace(day=1), today


@router.get("/profit-loss")
def profit_loss(
    start: date_type | None = Query(default=None),
    end: date_type | None = Query(default=None),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    default_start, default_end = _default_month_range()
    return service.profit_loss(db, org_id, start or default_start, end or default_end)


@router.get("/balance-sheet")
def balance_sheet(
    as_of: date_type | None = Query(default=None),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    return service.balance_sheet(db, org_id, as_of or date.today())


@router.get("/cash-flow")
def cash_flow(
    start: date_type | None = Query(default=None),
    end: date_type | None = Query(default=None),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    default_start, default_end = _default_month_range()
    return service.cash_flow(db, org_id, start or default_start, end or default_end)


@router.get("/iva")
def vat(
    start: date_type | None = Query(default=None),
    end: date_type | None = Query(default=None),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    default_start, default_end = _default_month_range()
    return service.vat_report(db, org_id, start or default_start, end or default_end)
