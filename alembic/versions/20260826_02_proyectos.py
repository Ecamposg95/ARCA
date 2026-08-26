"""proyectos: dimensión analítica en operaciones

Revision ID: 20260826_02
Revises: 20260826_01
Create Date: 2026-08-26

Un proyecto es una etiqueta de negocio, no una cuenta: por eso `project_id` es
nullable en las cuatro operaciones y no hay backfill que inventar. Lo existente
queda "sin asignar", que es la verdad.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260826_02"
down_revision = "20260826_01"
branch_labels = None
depends_on = None

TABLES = ("incomes", "expenses", "receivables", "payables")


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("code", sa.String(30), nullable=True),
        sa.Column(
            "customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=True, index=True
        ),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("budget", sa.Numeric(14, 2), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    for table in TABLES:
        op.add_column(table, sa.Column("project_id", sa.String(36), nullable=True))
        op.create_index(f"ix_{table}_project_id", table, ["project_id"])


def downgrade() -> None:
    for table in TABLES:
        op.drop_index(f"ix_{table}_project_id", table_name=table)
        op.drop_column(table, "project_id")
    op.drop_table("projects")
