"""asistente ONE Finance sobre Claude

Revision ID: 20261102_02
Revises: 20261012_01
Create Date: 2026-11-02

Conversaciones, mensajes (bloques crudos del API), acciones propuestas desde el
chat, uso del API por llamada y presupuesto por empresa. `agent_action_logs`
acepta auditoría sin llave: el asistente corre como el usuario logueado.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261102_02"
down_revision = "20261012_01"
branch_labels = None
depends_on = None


def _tenant_columns():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False, index=True),
    ]


def upgrade() -> None:
    op.add_column("organizations", sa.Column("ai_budget_usd", sa.Numeric(10, 2), nullable=True))
    op.add_column(
        "organizations",
        sa.Column("ai_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    with op.batch_alter_table("agent_action_logs") as batch:
        batch.alter_column("agent_key_id", existing_type=sa.String(36), nullable=True)
        batch.add_column(sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True))

    op.create_table(
        "assistant_conversations",
        *_tenant_columns(),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("title", sa.String(120), nullable=True),
        sa.Column("busy_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "assistant_messages",
        *_tenant_columns(),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("blocks", sa.JSON(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("steps", sa.JSON(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("stop_reason", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "assistant_actions",
        *_tenant_columns(),
        sa.Column(
            "message_id",
            sa.String(36),
            sa.ForeignKey("assistant_messages.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("tool_use_id", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("args", sa.JSON(), nullable=False),
        sa.Column("summary", sa.String(300), nullable=False),
        sa.Column("proposal_id", sa.String(36), sa.ForeignKey("agent_proposals.id"), nullable=True, index=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "ai_usage",
        *_tenant_columns(),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("feature", sa.String(30), nullable=False, server_default="assistant"),
        sa.Column("model", sa.String(60), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_usage_org_created", "ai_usage", ["organization_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_org_created", table_name="ai_usage")
    op.drop_table("ai_usage")
    op.drop_table("assistant_actions")
    op.drop_table("assistant_messages")
    op.drop_table("assistant_conversations")
    with op.batch_alter_table("agent_action_logs") as batch:
        batch.drop_column("user_id")
        batch.alter_column("agent_key_id", existing_type=sa.String(36), nullable=False)
    op.drop_column("organizations", "ai_enabled")
    op.drop_column("organizations", "ai_budget_usd")
