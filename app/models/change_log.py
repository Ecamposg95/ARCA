"""Bitácora de cambios (HU-09): quién cambió qué y cuáles eran los valores anteriores.

Distinta de `AgentActionLog` (que audita invocaciones de herramientas de
agentes): ésta registra el efecto sobre los registros del negocio, venga de
donde venga (web, asistente, agente, importación o autorización).

Append-only: no existe endpoint para editarla ni borrarla.
"""

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, String

from app.database import Base
from app.models.mixins import TenantMixin, UUIDPKMixin, _utcnow

CHANGE_ACTIONS = ("CREATE", "UPDATE", "CANCEL", "PAY", "APPROVE", "REJECT", "DELETE")
CHANGE_SOURCES = ("web", "assistant", "agent", "import", "approval", "system")


class ChangeLog(Base, UUIDPKMixin, TenantMixin):
    __tablename__ = "change_log"

    entity_type = Column(String(40), nullable=False)
    entity_id = Column(String(36), nullable=False)
    action = Column(String(20), nullable=False)  # CHANGE_ACTIONS
    # {campo: {"old": x, "new": y}} con valores ya serializados (Decimal → str, fechas ISO).
    changes = Column(JSON, nullable=False, default=dict)
    reason = Column(String(500), nullable=True)
    # Nullable: lo que hace el sistema o un agente sin humano detrás.
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    source = Column(String(20), nullable=False, default="web")  # CHANGE_SOURCES
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_change_log_entity", "organization_id", "entity_type", "entity_id", "created_at"),
        Index("ix_change_log_org_created", "organization_id", "created_at"),
    )
