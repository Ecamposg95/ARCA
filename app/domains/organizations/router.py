from fastapi import APIRouter, Depends, HTTPException
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field
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


# --- Equipo: el backend ya distinguía cinco roles, pero no había forma de usarlos ---


class MemberInvite(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(default=ROLE_MEMBER)
    # Contraseña inicial: ARCA todavía no manda correos, así que se entrega a mano.
    password: str = Field(min_length=8, max_length=128)


class MemberRoleUpdate(BaseModel):
    role: str


class MemberRead(BaseModel):
    id: str
    user_id: str
    name: str
    email: str
    role: str
    is_you: bool


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
    items = [
        MemberRead(
            id=member.id,
            user_id=member.user_id,
            name=account.name,
            email=account.email,
            role=member.role,
            is_you=account.id == user.id,
        )
        for member, account in rows
    ]
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
    return MemberRead(
        id=member.id,
        user_id=account.id,
        name=account.name,
        email=account.email,
        role=member.role,
        is_you=False,
    )


@router.patch("/current/members/{member_id}", response_model=MemberRead)
def update_member_role(
    member_id: str,
    payload: MemberRoleUpdate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _role: None = Depends(require_role((ROLE_OWNER, ROLE_ADMIN))),
):
    if payload.role not in VALID_ROLES or payload.role == ROLE_OWNER:
        raise HTTPException(status_code=400, detail="Ese permiso no se puede asignar.")

    member = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.id == member_id, OrganizationMember.organization_id == org_id)
        .first()
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Esa persona no está en tu equipo.")
    if member.role == ROLE_OWNER:
        raise HTTPException(status_code=400, detail="No puedes cambiar el permiso del dueño.")

    member.role = payload.role
    db.commit()
    db.refresh(member)
    account = db.get(User, member.user_id)
    return MemberRead(
        id=member.id,
        user_id=account.id,
        name=account.name,
        email=account.email,
        role=member.role,
        is_you=account.id == user.id,
    )


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
