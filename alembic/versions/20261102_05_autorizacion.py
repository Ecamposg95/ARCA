"""autorización por monto: umbral y límite del auxiliar por empresa, facultad por miembro

Revision ID: 20261102_05
Revises: 20261102_03
Create Date: 2026-11-02

Spec `docs/superpowers/specs/2026-11-02-autorizacion-por-monto-design.md`.
Todo nullable o con default: ninguna empresa cambia de comportamiento hasta
que fija su umbral. `agent_proposals.requested_by` distingue a quien capturó
una operación que espera autorización del agente o asistente que propone.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261102_05"
down_revision = "20261102_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.add_column(sa.Column("approval_threshold", sa.Numeric(14, 2), nullable=True))
        batch.add_column(sa.Column("member_capture_limit", sa.Numeric(14, 2), nullable=True))
    with op.batch_alter_table("organization_members") as batch:
        batch.add_column(
            sa.Column("can_authorize", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    with op.batch_alter_table("agent_proposals") as batch:
        batch.add_column(sa.Column("requested_by", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_agent_proposals_requested_by", "users", ["requested_by"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_proposals") as batch:
        batch.drop_constraint("fk_agent_proposals_requested_by", type_="foreignkey")
        batch.drop_column("requested_by")
    with op.batch_alter_table("organization_members") as batch:
        batch.drop_column("can_authorize")
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("member_capture_limit")
        batch.drop_column("approval_threshold")
