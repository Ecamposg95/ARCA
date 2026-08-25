from fastapi import APIRouter, Depends
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.schemas import OrganizationRead
from app.models.organization import Organization, ROLE_ADMIN, ROLE_OWNER
from app.security.deps import get_current_org_id, require_role

router = APIRouter(prefix="/organizations", tags=["organizations"])


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    tax_id: str | None = Field(default=None, max_length=20)
    business_type: str | None = Field(default=None, max_length=50)
    default_tax_rate: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


@router.get("/current", response_model=OrganizationRead)
def get_current_organization(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    organization = db.get(Organization, org_id)
    return OrganizationRead.model_validate(organization)


@router.patch("/current", response_model=OrganizationRead)
def update_current_organization(
    payload: OrganizationUpdate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _membership=Depends(require_role((ROLE_OWNER, ROLE_ADMIN))),
):
    organization = db.get(Organization, org_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(organization, field, value)
    db.commit()
    db.refresh(organization)
    return OrganizationRead.model_validate(organization)
