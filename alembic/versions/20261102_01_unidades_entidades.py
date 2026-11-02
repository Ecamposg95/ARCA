"""unidades de negocio y entidad fiscal: dos dimensiones opcionales del libro

Revision ID: 20261102_01
Revises: 20261102_02
Create Date: 2026-11-02

Va después de `20261102_02` (asistente) aunque el número diga lo contrario:
las dos se escribieron el mismo día en ramas distintas y el head es uno solo.

`business_units` y `fiscal_entities` nuevas; columnas nullable con índice en
cuentas de dinero, ingresos, gastos, CxC, CxP, movimientos y pólizas. Toda
empresa arranca sin unidades ni entidades: nada cambia para quien no las usa.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261102_01"
down_revision = "20261102_02"
branch_labels = None
depends_on = None

# (tabla, lleva entidad fiscal)
DIMENSIONED = (
    ("financial_accounts", False),
    ("incomes", True),
    ("expenses", True),
    ("receivables", True),
    ("payables", True),
    ("financial_transactions", False),
    ("journal_entries", True),
)


def upgrade() -> None:
    op.create_table(
        "business_units",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(12), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="OTRA"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("opened_on", sa.Date(), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "code", name="uq_business_unit_org_code"),
    )
    op.create_table(
        "fiscal_entities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("tax_id", sa.String(13), nullable=True),
        sa.Column("regime", sa.String(80), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    for table, with_entity in DIMENSIONED:
        op.add_column(
            table,
            sa.Column(
                "business_unit_id",
                sa.String(36),
                sa.ForeignKey("business_units.id", name=f"fk_{table}_business_unit"),
                nullable=True,
            ),
        )
        op.create_index(f"ix_{table}_business_unit_id", table, ["business_unit_id"])
        if with_entity:
            op.add_column(
                table,
                sa.Column(
                    "fiscal_entity_id",
                    sa.String(36),
                    sa.ForeignKey("fiscal_entities.id", name=f"fk_{table}_fiscal_entity"),
                    nullable=True,
                ),
            )
            op.create_index(f"ix_{table}_fiscal_entity_id", table, ["fiscal_entity_id"])


def downgrade() -> None:
    for table, with_entity in reversed(DIMENSIONED):
        if with_entity:
            op.drop_index(f"ix_{table}_fiscal_entity_id", table_name=table)
            op.drop_constraint(f"fk_{table}_fiscal_entity", table, type_="foreignkey")
            op.drop_column(table, "fiscal_entity_id")
        op.drop_index(f"ix_{table}_business_unit_id", table_name=table)
        op.drop_constraint(f"fk_{table}_business_unit", table, type_="foreignkey")
        op.drop_column(table, "business_unit_id")
    op.drop_table("fiscal_entities")
    op.drop_table("business_units")
