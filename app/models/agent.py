"""Capa agéntica (spec 2026-08-24): llaves, propuestas y auditoría.

Los agentes leen vía herramientas y PROPONEN operaciones; solo un humano
aprueba, y la aprobación ejecuta los services reales. Nunca escritura directa.
"""

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin

AGENT_SCOPES = ("READ", "PROPOSE")
PROPOSAL_KINDS = ("INCOME", "EXPENSE", "RECEIVABLE", "PAYABLE")
PROPOSAL_STATUSES = ("PROPOSED", "APPROVED", "REJECTED")


class AgentKey(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Llave API de agente, fija a UNA organización. En BD solo hash + prefijo."""

    __tablename__ = "agent_keys"

    name = Column(String(100), nullable=False)
    key_prefix = Column(String(12), nullable=False)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    scopes = Column(String(50), nullable=False, default="READ")  # "READ" | "READ,PROPOSE"
    active = Column(Boolean, nullable=False, default=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)


class AgentProposal(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    __tablename__ = "agent_proposals"

    # Nullable: los borradores recurrentes los propone ARCA mismo, sin llave.
    agent_key_id = Column(String(36), ForeignKey("agent_keys.id"), nullable=True, index=True)
    kind = Column(String(20), nullable=False)  # PROPOSAL_KINDS
    payload = Column(JSON, nullable=False)
    summary = Column(String(300), nullable=False)
    evidence = Column(String(2000), nullable=True)
    status = Column(String(20), nullable=False, default="PROPOSED")  # PROPOSAL_STATUSES
    reviewed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(String(500), nullable=True)
    result_id = Column(String(36), nullable=True)
    # Clave de idempotencia para propuestas generadas por el sistema:
    # `recurring:{regla}:{AAAA-MM}`. Un mes no se propone dos veces.
    origin = Column(String(64), nullable=True, index=True)


class AgentActionLog(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Toda invocación de herramienta queda registrada, exitosa o no."""

    __tablename__ = "agent_action_logs"

    agent_key_id = Column(String(36), ForeignKey("agent_keys.id"), nullable=False, index=True)
    tool = Column(String(100), nullable=False)
    arguments = Column(JSON, nullable=True)
    success = Column(Boolean, nullable=False, default=True)
    error = Column(String(500), nullable=True)
    duration_ms = Column(Integer, nullable=True)
