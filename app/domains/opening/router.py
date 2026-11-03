"""Apertura: fecha de corte, estado y resumen de los saldos iniciales.

El ajuste de cada cuenta de dinero vive en `/accounts/{id}/opening-adjustment`
y el de las cuentas sin módulo en `PUT /accounting/opening-balance`; aquí sólo
se configura el corte y se lee el panorama.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.opening import service
from app.domains.opening.schemas import OpeningSettingsUpdate, OpeningSummary
from app.models.organization import ACCOUNTING_ROLES, ROLE_ADMIN, ROLE_OWNER
from app.models.user import User
from app.security.deps import get_current_org_id, get_current_user, require_role

router = APIRouter(prefix="/opening", tags=["opening"])

# La fecha de corte decide la fecha de toda la apertura: la fija quien administra.
SETTINGS_ROLES = (ROLE_OWNER, ROLE_ADMIN)


def _summary(db: Session, org_id: str) -> OpeningSummary:
    return OpeningSummary(organization_id=org_id, **service.summary(db, org_id))


@router.get("", response_model=OpeningSummary)
def get_opening(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _membership=Depends(require_role(ACCOUNTING_ROLES)),
):
    return _summary(db, org_id)


@router.patch("", response_model=OpeningSummary)
def update_opening(
    payload: OpeningSettingsUpdate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(SETTINGS_ROLES)),
):
    try:
        service.update_settings(db, org_id, changes=payload.model_dump(exclude_unset=True), user_id=user.id)
    except ValueError:
        db.rollback()
        raise
    db.commit()
    return _summary(db, org_id)
