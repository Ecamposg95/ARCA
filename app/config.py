"""Configuración de ONE Finance.

Patrón Atlas (dasic): dataclass congelada + lru_cache, fail-fast en producción.
Sin fallback de secreto en producción, nunca.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

_DEV_SECRET = "arca-dev-secret-key-not-for-production-use-0000"
_DEV_DATABASE_URL = "sqlite:///./arca_dev.db"


def _normalize_database_url(url: str) -> str:
    # Railway entrega postgres://; SQLAlchemy requiere postgresql://
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret_key: str
    env: str
    cors_origins: tuple[str, ...]
    access_token_expire_minutes: int
    refresh_token_expire_days: int
    docs_enabled: bool
    # Asistente sobre Claude (spec 2026-11-02). La llave NO vive aquí: se lee
    # en el momento de construir el cliente, para que aparezca sin reiniciar nada.
    ai_model: str
    ai_effort: str
    ai_max_tokens: int
    ai_budget_default_usd: Decimal

    @property
    def is_production(self) -> bool:
        return self.env == "production"


def _build_settings() -> Settings:
    env = os.getenv("ENV", "development")
    is_production = env == "production"

    database_url = os.getenv("DATABASE_URL", "")
    secret_key = os.getenv("SECRET_KEY", "")

    if is_production:
        if not database_url:
            raise RuntimeError("DATABASE_URL debe estar definida en producción.")
        if not secret_key:
            raise RuntimeError("SECRET_KEY debe estar definida en producción.")
        if len(secret_key) < 32:
            raise RuntimeError("SECRET_KEY debe tener al menos 32 caracteres.")
    else:
        database_url = database_url or _DEV_DATABASE_URL
        secret_key = secret_key or _DEV_SECRET

    cors_origins = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "").split(",")
        if origin.strip()
    )

    return Settings(
        database_url=_normalize_database_url(database_url),
        secret_key=secret_key,
        env=env,
        cors_origins=cors_origins,
        access_token_expire_minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "720")),
        refresh_token_expire_days=int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30")),
        docs_enabled=os.getenv("DOCS_ENABLED", "false" if is_production else "true").lower() == "true",
        ai_model=os.getenv("AI_MODEL", "claude-opus-5-5"),
        ai_effort=os.getenv("AI_EFFORT", "medium"),
        ai_max_tokens=int(os.getenv("AI_MAX_TOKENS", "16000")),
        ai_budget_default_usd=Decimal(os.getenv("AI_BUDGET_DEFAULT_USD", "20")),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return _build_settings()
