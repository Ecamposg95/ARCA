from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.user import User
from app.security.passwords import hash_password, verify_password
from app.services.onboarding import provision_organization

logger = logging.getLogger("arca.auth")


def register_user(
    db: Session,
    email: str,
    password: str,
    name: str,
    business_name: str,
    business_type: str | None = None,
    initial_cash=None,
) -> tuple[User, Organization]:
    """Cadena completa de onboarding (task pack §29). Hace commit."""
    normalized_email = email.strip().lower()
    existing = db.query(User).filter(User.email == normalized_email).first()
    if existing is not None:
        raise ValueError("Ya existe una cuenta con este correo.")

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        name=name.strip(),
    )
    db.add(user)
    db.flush()

    organization = provision_organization(
        db,
        user,
        business_name=business_name,
        business_type=business_type,
        initial_cash=initial_cash,
    )
    db.commit()
    db.refresh(user)
    db.refresh(organization)
    logger.info("registro: usuario=%s organización=%s", user.id, organization.id)
    return user, organization


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if user is None:
        logger.warning("login fallido: correo desconocido")
        return None
    if not verify_password(password, user.password_hash):
        logger.warning("login fallido: contraseña incorrecta usuario=%s", user.id)
        return None
    if user.status != "ACTIVE":
        logger.warning("login fallido: usuario inactivo usuario=%s", user.id)
        return None
    return user
