from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.category import Category
from app.security.deps import get_current_org_id

router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    kind: str
    account_code: str
    active: bool
    created_at: datetime


@router.get("", response_model=list[CategoryRead])
def list_categories(
    kind: str | None = Query(default=None, pattern="^(INCOME|EXPENSE)$"),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    query = db.query(Category).filter(
        Category.organization_id == org_id,
        Category.active.is_(True),
    )
    if kind:
        query = query.filter(Category.kind == kind)
    categories = query.order_by(Category.kind, Category.name).all()
    return [CategoryRead.model_validate(category) for category in categories]
