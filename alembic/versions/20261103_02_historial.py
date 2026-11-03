"""bitácora de cambios con valores anteriores (HU-09)

Revision ID: 20261103_02
Revises: 20261102_04
Create Date: 2026-11-03

Tabla append-only `change_log`: quién cambió qué registro, cuándo, desde dónde
y con qué valores antes y después. Sólo agrega una tabla; nada existente cambia.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261103_02"
down_revision = "20261102_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "change_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="web"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_change_log_organization_id", "change_log", ["organization_id"])
    op.create_index("ix_change_log_user_id", "change_log", ["user_id"])
    op.create_index(
        "ix_change_log_entity", "change_log", ["organization_id", "entity_type", "entity_id", "created_at"]
    )
    op.create_index("ix_change_log_org_created", "change_log", ["organization_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_change_log_org_created", table_name="change_log")
    op.drop_index("ix_change_log_entity", table_name="change_log")
    op.drop_index("ix_change_log_user_id", table_name="change_log")
    op.drop_index("ix_change_log_organization_id", table_name="change_log")
    op.drop_table("change_log")
