"""JWT HS256 (python-jose). Access de corta vida + refresh de larga vida.

El claim `type` distingue access/refresh: un refresh token nunca autentica
requests y un access token nunca renueva sesión.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import get_settings

ALGORITHM = "HS256"


class TokenError(Exception):
    pass


def _create_token(user_id: str, token_type: str, expires_delta: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    return _create_token(user_id, "access", timedelta(minutes=settings.access_token_expire_minutes))


def create_refresh_token(user_id: str) -> str:
    settings = get_settings()
    return _create_token(user_id, "refresh", timedelta(days=settings.refresh_token_expire_days))


def decode_token(token: str, expected_type: str) -> str:
    """Devuelve el user_id del token o lanza TokenError."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        raise TokenError("Token inválido o expirado.")
    if payload.get("type") != expected_type:
        raise TokenError("Tipo de token incorrecto.")
    user_id = payload.get("sub")
    if not user_id:
        raise TokenError("Token sin sujeto.")
    return user_id
