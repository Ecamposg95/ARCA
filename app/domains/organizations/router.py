from fastapi import APIRouter, Depends, HTTPException
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.schemas import OrganizationRead
from app.models.organization import (
    Organization,
    OrganizationMember,
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_OWNER,
    VALID_ROLES,
)
from app.models.user import User
from app.security.passwords import hash_password
from app.security.deps import get_current_org_id, get_current_user, require_role
from app.services import approvals
from app.services.onboarding import provision_organization

router = APIRouter(prefix="/organizations", tags=["organizations"])


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    tax_id: str | None = Field(default=None, max_length=20)
    business_type: str | None = Field(default=None, max_length=50)
    default_tax_rate: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    # Asistente sobre Claude: sólo el dueño mueve el tope o el apagador.
    ai_budget_usd: Decimal | None = Field(default=None, ge=0, le=100000, allow_inf_nan=False)
    ai_enabled: bool | None = None


AI_FIELDS = ("ai_budget_usd", "ai_enabled")


class OrganizationCreate(BaseModel):
    business_name: str = Field(min_length=1, max_length=255)
    business_type: str | None = Field(default=None, max_length=50)
    tax_id: str | None = Field(default=None, max_length=20)
    initial_cash: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)

    @field_validator("business_name")
    @classmethod
    def _name_is_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Escribe el nombre de la empresa.")
        return value


@router.post("", response_model=OrganizationRead, status_code=201)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Otra empresa para quien ya tiene sesión: el contador da de alta a un cliente.

    Mismo arranque que el registro (catálogo, categorías, "Caja"); quien la crea
    queda como dueño.
    """
    organization = provision_organization(
        db,
        user,
        business_name=payload.business_name,
        business_type=payload.business_type,
        initial_cash=payload.initial_cash,
    )
    organization.tax_id = (payload.tax_id or "").strip().upper() or None
    db.commit()
    db.refresh(organization)
    return OrganizationRead.model_validate(organization)


@router.get("/current", response_model=OrganizationRead)
def get_current_organization(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    organization = db.get(Organization, org_id)
    return _organization_read(db, organization)


def _organization_read(db: Session, organization: Organization) -> OrganizationRead:
    from app.models.business_unit import BusinessUnit
    from app.models.fiscal_entity import FiscalEntity

    item = OrganizationRead.model_validate(organization)
    item.has_business_units = (
        db.query(BusinessUnit.id).filter(BusinessUnit.organization_id == organization.id).first() is not None
    )
    item.has_fiscal_entities = (
        db.query(FiscalEntity.id).filter(FiscalEntity.organization_id == organization.id).first() is not None
    )
    return item


@router.patch("/current", response_model=OrganizationRead)
def update_current_organization(
    payload: OrganizationUpdate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    membership=Depends(require_role((ROLE_OWNER, ROLE_ADMIN))),
):
    organization = db.get(Organization, org_id)
    changes = payload.model_dump(exclude_unset=True)
    if any(field in changes for field in AI_FIELDS) and membership.role != ROLE_OWNER:
        raise HTTPException(status_code=403, detail="Sólo el dueño puede cambiar el presupuesto del asistente.")
    for field, value in changes.items():
        setattr(organization, field, value)
    db.commit()
    db.refresh(organization)
    return OrganizationRead.model_validate(organization)


# --- Autorización por monto (spec 2026-11-02) ---------------------------------


class ApprovalSettings(BaseModel):
    """Vacío = sin autorización / sin límite. Se guarda tal cual, inclusive el null."""

    approval_threshold: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    member_capture_limit: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)


@router.get("/current/approvals", response_model=ApprovalSettings)
def get_approval_settings(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _role: None = Depends(require_role((ROLE_OWNER, ROLE_ADMIN))),
):
    return ApprovalSettings.model_validate(db.get(Organization, org_id), from_attributes=True)


@router.patch("/current/approvals", response_model=ApprovalSettings)
def update_approval_settings(
    payload: ApprovalSettings,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _role: None = Depends(require_role((ROLE_OWNER, ROLE_ADMIN))),
):
    organization = db.get(Organization, org_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(organization, field, value)
    db.commit()
    db.refresh(organization)
    return ApprovalSettings.model_validate(organization, from_attributes=True)


# --- Equipo: el backend ya distinguía cinco roles, pero no había forma de usarlos ---


class MemberInvite(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(default=ROLE_MEMBER)
    # Contraseña inicial: ONE Finance todavía no manda correos, así que se entrega a mano.
    password: str = Field(min_length=8, max_length=128)


class MemberRoleUpdate(BaseModel):
    role: str | None = None
    # Facultad de autorizar lo que alcanza el umbral. El dueño la tiene fija.
    can_authorize: bool | None = None


class MemberRead(BaseModel):
    id: str
    user_id: str
    name: str
    email: str
    role: str
    is_you: bool
    can_authorize: bool = False


def _member_read(member: OrganizationMember, account: User, viewer_id: str) -> MemberRead:
    return MemberRead(
        id=member.id,
        user_id=account.id,
        name=account.name,
        email=account.email,
        role=member.role,
        is_you=account.id == viewer_id,
        can_authorize=approvals.can_authorize(member),
    )


@router.get("/current/members")
def list_members(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
):
    rows = (
        db.query(OrganizationMember, User)
        .join(User, User.id == OrganizationMember.user_id)
        .filter(OrganizationMember.organization_id == org_id)
        .order_by(OrganizationMember.created_at)
        .all()
    )
    items = [_member_read(member, account, user.id) for member, account in rows]
    return {"items": items, "total": len(items), "limit": len(items), "offset": 0}


@router.post("/current/members", response_model=MemberRead, status_code=201)
def invite_member(
    payload: MemberInvite,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _role: None = Depends(require_role((ROLE_OWNER, ROLE_ADMIN))),
):
    if payload.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Ese permiso no existe.")
    if payload.role == ROLE_OWNER:
        raise HTTPException(
            status_code=400, detail="Sólo puede haber un dueño. Elige otro permiso."
        )

    email = payload.email.strip().lower()
    account = db.query(User).filter(User.email == email).first()
    if account is None:
        account = User(email=email, name=payload.name, password_hash=hash_password(payload.password))
        db.add(account)
        db.flush()

    existing = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == account.id,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=400, detail="Esa persona ya está en tu equipo.")

    member = OrganizationMember(organization_id=org_id, user_id=account.id, role=payload.role)
    db.add(member)
    db.commit()
    db.refresh(member)
    return _member_read(member, account, viewer_id="")


@router.patch("/current/members/{member_id}", response_model=MemberRead)
def update_member_role(
    member_id: str,
    payload: MemberRoleUpdate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _role: None = Depends(require_role((ROLE_OWNER, ROLE_ADMIN))),
):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No hay nada que cambiar.")
    if "role" in changes and (payload.role not in VALID_ROLES or payload.role == ROLE_OWNER):
        raise HTTPException(status_code=400, detail="Ese permiso no se puede asignar.")

    member = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.id == member_id, OrganizationMember.organization_id == org_id)
        .first()
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Esa persona no está en tu equipo.")
    if member.role == ROLE_OWNER:
        detail = "El dueño siempre autoriza." if "can_authorize" in changes else "No puedes cambiar el permiso del dueño."
        raise HTTPException(status_code=400, detail=detail)

    if "role" in changes:
        member.role = payload.role
    if "can_authorize" in changes:
        member.can_authorize = bool(payload.can_authorize)
    db.commit()
    db.refresh(member)
    account = db.get(User, member.user_id)
    return _member_read(member, account, user.id)


@router.delete("/current/members/{member_id}", status_code=204)
def remove_member(
    member_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _role: None = Depends(require_role((ROLE_OWNER, ROLE_ADMIN))),
):
    member = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.id == member_id, OrganizationMember.organization_id == org_id)
        .first()
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Esa persona no está en tu equipo.")
    if member.role == ROLE_OWNER:
        raise HTTPException(status_code=400, detail="No puedes sacar al dueño de su empresa.")
    db.delete(member)
    db.commit()
