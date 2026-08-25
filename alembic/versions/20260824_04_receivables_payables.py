"""cuentas por cobrar y por pagar

Revision ID: 20260824_04
Revises: 20260824_03
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa

revision = "20260824_04"
down_revision = "20260824_03"
branch_labels = None
depends_on = None


def _debt_columns(contact_table: str, contact_column: str):
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column(contact_column, sa.String(36), sa.ForeignKey(f"{contact_table}.id"), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("amount_paid", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("category_id", sa.String(36), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("cancellation_reason", sa.String(500), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table("receivables", *_debt_columns("customers", "customer_id"))
    op.create_index("ix_receivables_organization_id", "receivables", ["organization_id"])
    op.create_index("ix_receivables_customer_id", "receivables", ["customer_id"])
    op.create_index("ix_receivables_due_date", "receivables", ["due_date"])

    op.create_table("payables", *_debt_columns("vendors", "vendor_id"))
    op.create_index("ix_payables_organization_id", "payables", ["organization_id"])
    op.create_index("ix_payables_vendor_id", "payables", ["vendor_id"])
    op.create_index("ix_payables_due_date", "payables", ["due_date"])


def downgrade() -> None:
    op.drop_table("payables")
    op.drop_table("receivables")
