from fastapi import APIRouter, Depends
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
