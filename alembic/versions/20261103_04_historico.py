"""histórico de análisis: cargas y puntos

Revision ID: 20261103_04
Revises: 20261103_03
Create Date: 2026-11-04

Dos tablas nuevas para la capa de análisis (datos de los Excel de la empresa
antes de su fecha de corte). No toca el libro: ni pólizas, ni movimientos, ni
saldos.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261103_04"
down_revision = "20261103_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "historical_loads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loaded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "historical_points",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("load_id", sa.String(36), sa.ForeignKey("historical_loads.id"), nullable=False, index=True),
        sa.Column("dataset", sa.String(30), nullable=False),
        sa.Column("metric", sa.String(60), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_grain", sa.String(10), nullable=False),
        sa.Column("business_unit_id", sa.String(36), sa.ForeignKey("business_units.id"), nullable=True, index=True),
        sa.Column("unit_label", sa.String(255), nullable=True),
        sa.Column("fiscal_entity_id", sa.String(36), sa.ForeignKey("fiscal_entities.id"), nullable=True, index=True),
        sa.Column("payment_method", sa.String(30), nullable=True),
        sa.Column("account_code", sa.String(30), nullable=True),
        sa.Column("account_label", sa.String(255), nullable=True),
        sa.Column("value", sa.Numeric(16, 2), nullable=False),
        sa.Column("source", sa.String(255), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_historical_points_series",
        "historical_points",
        ["organization_id", "dataset", "metric", "period_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_historical_points_series", table_name="historical_points")
    op.drop_table("historical_points")
    op.drop_table("historical_loads")
