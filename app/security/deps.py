"""Dependencias de autenticación y contexto de organización.

Regla de oro Atlas: organization_id viene del contexto VALIDADO
(membresía verificada), nunca del payload del frontend.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.organization import OrganizationMember
from app.models.user import User
from app.security.tokens import TokenError, decode_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado.")
    try:
        user_id = decode_token(credentials.credentials, expected_type="access")
    except TokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida o expirada.")
    user = db.get(User, user_id)
    if user is None or user.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no disponible.")
    return user


def get_current_membership(
    x_organization_id: str | None = Header(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrganizationMember:
    """Resuelve y VALIDA la membresía del usuario en la organización activa."""
    query = db.query(OrganizationMember).filter(OrganizationMember.user_id == user.id)
    if x_organization_id:
        membership = query.filter(OrganizationMember.organization_id == x_organization_id).first()
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a esta organización.",
            )
        return membership
    memberships = query.limit(2).all()
    if not memberships:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No perteneces a ninguna organización.")
    if len(memberships) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Indica la organización activa (encabezado X-Organization-ID).",
        )
    return memberships[0]


def get_current_org_id(membership: OrganizationMember = Depends(get_current_membership)) -> str:
    return membership.organization_id


def require_role(roles: list[str] | tuple[str, ...]):
    """Factory de dependencia: exige que el rol del usuario en la org esté en `roles`."""

    def _checker(membership: OrganizationMember = Depends(get_current_membership)) -> OrganizationMember:
        if membership.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para esta acción.",
            )
        return membership

    return _checker
