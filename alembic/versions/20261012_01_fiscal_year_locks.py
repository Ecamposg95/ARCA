"""candado de ejercicio: cierre anual

Revision ID: 20261012_01
Revises: 20261006_01
Create Date: 2026-10-12

`fiscal_year_locks`: un renglón por empresa y año cerrado, con la póliza de
cierre que traspasó el resultado a Resultados Acumulados. Misma forma que
`period_locks`, más `closing_entry_id`.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261012_01"
down_revision = "20261006_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fiscal_year_locks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("closed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("closing_entry_id", sa.String(36), sa.ForeignKey("journal_entries.id"), nullable=True),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopened_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reopen_reason", sa.String(500), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "year", name="uq_fiscal_year_lock"),
    )


def downgrade() -> None:
    op.drop_table("fiscal_year_locks")
