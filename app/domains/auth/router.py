from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.schemas import (
    AuthResponse,
    LoginRequest,
    MeResponse,
    MembershipRead,
    OrganizationRead,
    RefreshRequest,
    RegisterRequest,
    UserRead,
)
from app.domains.auth.service import authenticate_user, register_user
from app.models.organization import Organization, OrganizationMember
from app.models.user import User
from app.security.deps import get_current_user
from app.security.tokens import TokenError, create_access_token, create_refresh_token, decode_token

router = APIRouter(tags=["auth"])


def _auth_response(user: User, organization: Organization | None) -> AuthResponse:
    return AuthResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=UserRead.model_validate(user),
        organization=OrganizationRead.model_validate(organization) if organization else None,
    )


@router.post("/auth/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    user, organization = register_user(
        db,
        email=payload.email,
        password=payload.password,
        name=payload.name,
        business_name=payload.business_name,
        business_type=payload.business_type,
        initial_cash=payload.initial_cash,
    )
    return _auth_response(user, organization)


@router.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")
    membership = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.user_id == user.id)
        .order_by(OrganizationMember.created_at)
        .first()
    )
    organization = db.get(Organization, membership.organization_id) if membership else None
    return _auth_response(user, organization)


@router.post("/auth/refresh", response_model=AuthResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    try:
        user_id = decode_token(payload.refresh_token, expected_type="refresh")
    except TokenError:
        raise HTTPException(status_code=401, detail="Sesión expirada, inicia sesión de nuevo.")
    user = db.get(User, user_id)
    if user is None or user.status != "ACTIVE":
        raise HTTPException(status_code=401, detail="Usuario no disponible.")
    membership = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.user_id == user.id)
        .order_by(OrganizationMember.created_at)
        .first()
    )
    organization = db.get(Organization, membership.organization_id) if membership else None
    return _auth_response(user, organization)


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    memberships = db.query(OrganizationMember).filter(OrganizationMember.user_id == user.id).all()
    org_ids = [m.organization_id for m in memberships]
    organizations = (
        db.query(Organization).filter(Organization.id.in_(org_ids)).all() if org_ids else []
    )
    return MeResponse(
        user=UserRead.model_validate(user),
        memberships=[MembershipRead.model_validate(m) for m in memberships],
        organizations=[OrganizationRead.model_validate(o) for o in organizations],
    )
