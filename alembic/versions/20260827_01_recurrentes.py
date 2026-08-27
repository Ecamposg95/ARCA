"""recurrentes: reglas mensuales que proponen solas

Revision ID: 20260827_01
Revises: 20260826_04
Create Date: 2026-08-27

Crea `recurring_rules` y toca `agent_proposals` dos veces:

- `agent_key_id` pasa a nullable: los borradores recurrentes los propone ARCA
  mismo, no una llave de agente. Inventar una "llave de sistema" con hash
  falso habría sido más invasivo que admitir la verdad en el esquema.
- `origin` (nullable, indexada): la clave de idempotencia
  `recurring:{regla}:{AAAA-MM}` — el patrón de la depreciación, para que un
  mes no se proponga dos veces ni aunque el humano ya lo haya rechazado.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260827_01"
down_revision = "20260826_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recurring_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("category_id", sa.String(36), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("vendor_id", sa.String(36), sa.ForeignKey("vendors.id"), nullable=True),
        sa.Column(
            "financial_account_id",
            sa.String(36),
            sa.ForeignKey("financial_accounts.id"),
            nullable=True,
        ),
        sa.Column("day_of_month", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # batch: SQLite no sabe ALTER COLUMN; PostgreSQL hace el ALTER directo.
    with op.batch_alter_table("agent_proposals") as batch:
        batch.alter_column(
            "agent_key_id",
            existing_type=sa.String(36),
            nullable=True,
        )
        batch.add_column(sa.Column("origin", sa.String(64), nullable=True))
    op.create_index("ix_agent_proposals_origin", "agent_proposals", ["origin"])


def downgrade() -> None:
    op.drop_index("ix_agent_proposals_origin", table_name="agent_proposals")
    # Sólo es seguro si no existen propuestas sin llave (las recurrentes).
    with op.batch_alter_table("agent_proposals") as batch:
        batch.drop_column("origin")
        batch.alter_column(
            "agent_key_id",
            existing_type=sa.String(36),
            nullable=False,
        )
    op.drop_table("recurring_rules")
