"""Asistente ONE Finance sobre Claude (spec 2026-11-02).

`blocks` guarda el contenido crudo del API (texto, thinking con firma,
tool_use, tool_result) para reenviar el historial íntegro; `text` es lo que
pinta la interfaz. Las acciones son las propuestas que el modelo hizo en el
chat y que un humano aprueba o rechaza desde la misma tarjeta. `ai_usage`
lleva una fila por llamada al API: de ahí sale el consumo del mes.
"""

from __future__ import annotations

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin, _utcnow

MESSAGE_ROLES = ("user", "assistant")
ACTION_STATUSES = ("PENDING", "APPROVED", "REJECTED")
FEATURE_ASSISTANT = "assistant"


class AssistantConversation(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    __tablename__ = "assistant_conversations"

    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(120), nullable=True)
    # Un turno en curso bloquea otro en la misma conversación.
    busy_since = Column(DateTime(timezone=True), nullable=True)

    messages = relationship(
        "AssistantMessage",
        cascade="all, delete-orphan",
        order_by="AssistantMessage.created_at, AssistantMessage.seq",
        passive_deletes=True,
    )


class AssistantMessage(Base, UUIDPKMixin, TenantMixin):
    __tablename__ = "assistant_messages"

    conversation_id = Column(
        String(36), ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Orden estable dentro de la conversación (los timestamps pueden empatar).
    seq = Column(Integer, nullable=False, default=0)
    role = Column(String(16), nullable=False)  # MESSAGE_ROLES
    blocks = Column(JSON, nullable=False)
    text = Column(Text, nullable=True)
    steps = Column(JSON, nullable=True)  # [{name, ok, summary}]
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cache_read_tokens = Column(Integer, nullable=False, default=0)
    cache_write_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Numeric(10, 6), nullable=False, default=0)
    stop_reason = Column(String(30), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    actions = relationship(
        "AssistantAction", cascade="all, delete-orphan", order_by="AssistantAction.created_at", passive_deletes=True
    )


class AssistantAction(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    __tablename__ = "assistant_actions"

    message_id = Column(String(36), ForeignKey("assistant_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(
        String(36), ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_use_id = Column(String(64), nullable=False)
    tool_name = Column(String(100), nullable=False)
    args = Column(JSON, nullable=False)
    summary = Column(String(300), nullable=False)
    proposal_id = Column(String(36), ForeignKey("agent_proposals.id"), nullable=True, index=True)
    status = Column(String(16), nullable=False, default="PENDING")  # ACTION_STATUSES
    resolved_at = Column(DateTime(timezone=True), nullable=True)


class AiUsage(Base, UUIDPKMixin, TenantMixin):
    """Una fila por llamada al API (no por turno)."""

    __tablename__ = "ai_usage"
    __table_args__ = (Index("ix_ai_usage_org_created", "organization_id", "created_at"),)

    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    feature = Column(String(30), nullable=False, default=FEATURE_ASSISTANT)
    model = Column(String(60), nullable=False)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cache_read_tokens = Column(Integer, nullable=False, default=0)
    cache_write_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Numeric(10, 6), nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
