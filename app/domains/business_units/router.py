from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.business_units import service
from app.domains.business_units.schemas import BusinessUnitCreate, BusinessUnitRead, BusinessUnitUpdate
from app.models.business_unit import BusinessUnit
from app.models.organization import ROLE_ADMIN, ROLE_OWNER
from app.security.deps import get_current_org_id, require_role
from app.services.dimensions import get_business_unit

router = APIRouter(prefix="/business-units", tags=["business-units"])

# Dar de alta sucursales es decisión del dueño, no del capturista.
CATALOG_ROLES = (ROLE_OWNER, ROLE_ADMIN)


def _read(unit: BusinessUnit, counts: dict[str, int]) -> BusinessUnitRead:
    item = BusinessUnitRead.model_validate(unit)
    item.accounts_count = counts.get(unit.id, 0)
    return item


@router.get("")
def list_business_units(
    active: bool | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    query = db.query(BusinessUnit).filter(BusinessUnit.organization_id == org_id)
    if active is not None:
        query = query.filter(BusinessUnit.active.is_(active))
    query = query.order_by(BusinessUnit.sort_order, BusinessUnit.name)
    total = query.count()
    units = query.limit(limit).offset(offset).all()
    counts = service.accounts_count_by_unit(db, org_id)
    return {"items": [_read(unit, counts) for unit in units], "total": total, "limit": limit, "offset": offset}


@router.post("", response_model=BusinessUnitRead, status_code=201)
def create_business_unit(
    payload: BusinessUnitCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _membership=Depends(require_role(CATALOG_ROLES)),
):
    unit = service.create_business_unit(db, org_id, payload)
    return _read(unit, {})


@router.patch("/{unit_id}", response_model=BusinessUnitRead)
def update_business_unit(
    unit_id: str,
    payload: BusinessUnitUpdate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _membership=Depends(require_role(CATALOG_ROLES)),
):
    unit = get_business_unit(db, org_id, unit_id)
    unit = service.update_business_unit(db, unit, payload)
    return _read(unit, service.accounts_count_by_unit(db, org_id))
