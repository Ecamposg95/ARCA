from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.recurring import service
from app.domains.recurring.schemas import (
    GenerateRequest,
    RecurringCreate,
    RecurringRead,
    RecurringUpdate,
)
from app.models.category import Category
from app.models.organization import WRITE_ROLES
from app.models.recurring import RecurringRule
from app.models.user import User
from app.security.deps import get_current_org_id, get_current_user, require_role

router = APIRouter(prefix="/recurring", tags=["recurring"])


def _get_rule(db: Session, org_id: str, rule_id: str) -> RecurringRule:
    rule = (
        db.query(RecurringRule)
        .filter(RecurringRule.id == rule_id, RecurringRule.organization_id == org_id)
        .first()
    )
    if rule is None:
        raise HTTPException(status_code=404, detail="La regla no existe.")
    return rule


@router.get("")
def list_rules(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    rows = (
        db.query(RecurringRule)
        .filter(RecurringRule.organization_id == org_id)
        .order_by(RecurringRule.day_of_month, RecurringRule.created_at)
        .all()
    )
    items = [RecurringRead.model_validate(row) for row in rows]
    return {"items": items, "total": len(items), "limit": len(items), "offset": 0}


@router.get("/pending")
def pending(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    return {"pending": service.pending_count(db, org_id, year, month)}


@router.post("", response_model=RecurringRead, status_code=201)
def create_rule(
    payload: RecurringCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _role: None = Depends(require_role(WRITE_ROLES)),
):
    category = (
        db.query(Category)
        .filter(Category.id == payload.category_id, Category.organization_id == org_id)
        .first()
    )
    if category is None:
        raise HTTPException(status_code=400, detail="Esa categoría no existe.")
    rule = RecurringRule(
        organization_id=org_id,
        created_by=user.id,
        **payload.model_dump(),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.post("/generate")
def generate(
    payload: GenerateRequest,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _user: User = Depends(get_current_user),
    _role: None = Depends(require_role(WRITE_ROLES)),
):
    try:
        return service.generate_drafts(db, org_id, payload.year, payload.month)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.patch("/{rule_id}", response_model=RecurringRead)
def update_rule(
    rule_id: str,
    payload: RecurringUpdate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _role: None = Depends(require_role(WRITE_ROLES)),
):
    rule = _get_rule(db, org_id, rule_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
def delete_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _role: None = Depends(require_role(WRITE_ROLES)),
):
    rule = _get_rule(db, org_id, rule_id)
    if service.has_generated(db, org_id, rule.id):
        raise HTTPException(
            status_code=400,
            detail="Esta regla ya generó borradores: mejor pausa la regla. "
            "La historia no se borra.",
        )
    db.delete(rule)
    db.commit()
