"""capa agéntica: llaves, propuestas y auditoría

Revision ID: 20260824_05
Revises: 20260824_04
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa

revision = "20260824_05"
down_revision = "20260824_04"
branch_labels = None
depends_on = None


def _base_columns():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "agent_keys",
        *_base_columns(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_prefix", sa.String(12), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("scopes", sa.String(50), nullable=False, server_default="READ"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_agent_keys_organization_id", "agent_keys", ["organization_id"])
    op.create_index("ix_agent_keys_key_hash", "agent_keys", ["key_hash"], unique=True)

    op.create_table(
        "agent_proposals",
        *_base_columns(),
        sa.Column("agent_key_id", sa.String(36), sa.ForeignKey("agent_keys.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("summary", sa.String(300), nullable=False),
        sa.Column("evidence", sa.String(2000), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PROPOSED"),
        sa.Column("reviewed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.String(500), nullable=True),
        sa.Column("result_id", sa.String(36), nullable=True),
    )
    op.create_index("ix_agent_proposals_organization_id", "agent_proposals", ["organization_id"])
    op.create_index("ix_agent_proposals_agent_key_id", "agent_proposals", ["agent_key_id"])

    op.create_table(
        "agent_action_logs",
        *_base_columns(),
        sa.Column("agent_key_id", sa.String(36), sa.ForeignKey("agent_keys.id"), nullable=False),
        sa.Column("tool", sa.String(100), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
    )
    op.create_index("ix_agent_action_logs_organization_id", "agent_action_logs", ["organization_id"])
    op.create_index("ix_agent_action_logs_agent_key_id", "agent_action_logs", ["agent_key_id"])


def downgrade() -> None:
    op.drop_table("agent_action_logs")
    op.drop_table("agent_proposals")
    op.drop_table("agent_keys")
