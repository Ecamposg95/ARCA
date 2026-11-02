from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.fiscal_entities import service
from app.domains.fiscal_entities.schemas import FiscalEntityCreate, FiscalEntityRead, FiscalEntityUpdate
from app.models.fiscal_entity import FiscalEntity
from app.models.organization import ROLE_ADMIN, ROLE_OWNER
from app.schemas.common import paginate
from app.security.deps import get_current_org_id, require_role
from app.services.dimensions import get_fiscal_entity

router = APIRouter(prefix="/fiscal-entities", tags=["fiscal-entities"])

CATALOG_ROLES = (ROLE_OWNER, ROLE_ADMIN)


@router.get("")
def list_fiscal_entities(
    active: bool | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    query = db.query(FiscalEntity).filter(FiscalEntity.organization_id == org_id)
    if active is not None:
        query = query.filter(FiscalEntity.active.is_(active))
    query = query.order_by(FiscalEntity.sort_order, FiscalEntity.name)
    return paginate(query, limit, offset, FiscalEntityRead)


@router.post("", response_model=FiscalEntityRead, status_code=201)
def create_fiscal_entity(
    payload: FiscalEntityCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _membership=Depends(require_role(CATALOG_ROLES)),
):
    return FiscalEntityRead.model_validate(service.create_fiscal_entity(db, org_id, payload))


@router.patch("/{entity_id}", response_model=FiscalEntityRead)
def update_fiscal_entity(
    entity_id: str,
    payload: FiscalEntityUpdate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _membership=Depends(require_role(CATALOG_ROLES)),
):
    entity = get_fiscal_entity(db, org_id, entity_id)
    return FiscalEntityRead.model_validate(service.update_fiscal_entity(db, entity, payload))
