"""Mixins base de ARCA (convención Atlas, con las deudas conocidas corregidas):

- PK UUID string en todas las tablas.
- organization_id NOT NULL en tablas de negocio (nunca nullable).
- Timestamps tz-aware.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import declarative_mixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


@declarative_mixin
class UUIDPKMixin:
    id = Column(String(36), primary_key=True, default=new_uuid)


@declarative_mixin
class AuditMixin:
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


@declarative_mixin
class SoftDeleteMixin:
    deleted_at = Column(DateTime(timezone=True), nullable=True)


@declarative_mixin
class TenantMixin:
    """Toda entidad de negocio pertenece a una organización. Sin excepciones."""

    organization_id = Column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
