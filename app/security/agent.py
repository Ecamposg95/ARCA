"""Autenticación de agentes: llave API fija a UNA organización.

El token completo (`ak_<40 hex>`) se muestra una sola vez; en BD vive solo
su sha256. La organización viene de la llave — no hay header de org y por
tanto no hay superficie cross-tenant para agentes.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.agent import AgentKey

_bearer = HTTPBearer(auto_error=False)

KEY_PREFIX = "ak_"


def generate_key() -> tuple[str, str, str]:
    """Devuelve (token completo, prefijo visible, sha256)."""
    token = KEY_PREFIX + secrets.token_hex(20)
    return token, token[:12], hashlib.sha256(token.encode()).hexdigest()


def hash_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class AgentContext:
    agent_key_id: str
    organization_id: str
    scopes: tuple[str, ...]
    name: str


def get_agent_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> AgentContext:
    if credentials is None or not credentials.credentials.startswith(KEY_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere una llave de agente (ak_...).",
        )
    key = (
        db.query(AgentKey)
        .filter(AgentKey.key_hash == hash_key(credentials.credentials))
        .first()
    )
    if key is None or not key.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Llave de agente inválida o revocada.")
    key.last_used_at = datetime.now(timezone.utc)
    return AgentContext(
        agent_key_id=key.id,
        organization_id=key.organization_id,
        scopes=tuple(scope.strip() for scope in key.scopes.split(",") if scope.strip()),
        name=key.name,
    )


def require_scope(scope: str):
    def _checker(context: AgentContext = Depends(get_agent_context)) -> AgentContext:
        if scope not in context.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Esta llave no tiene el permiso {scope}.",
            )
        return context

    return _checker
