"""dinero: categorías, cuentas financieras, movimientos, contactos, ingresos y gastos

Revision ID: 20260824_03
Revises: 20260824_02
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa

revision = "20260824_03"
down_revision = "20260824_02"
branch_labels = None
depends_on = None


def _tenant_audit_columns():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _contact_columns():
    return [
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("legal_name", sa.String(255), nullable=True),
        sa.Column("tax_id", sa.String(20), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "categories",
        *_tenant_audit_columns(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("account_code", sa.String(10), nullable=False),
        sa.Column("system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("organization_id", "kind", "name", name="uq_category_org_kind_name"),
    )
    op.create_index("ix_categories_organization_id", "categories", ["organization_id"])

    op.create_table(
        "financial_accounts",
        *_tenant_audit_columns(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="MXN"),
        sa.Column("opening_balance", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("current_balance", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("institution", sa.String(100), nullable=True),
        sa.Column("last_four", sa.String(4), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_financial_accounts_organization_id", "financial_accounts", ["organization_id"])

    op.create_table("customers", *_tenant_audit_columns(), *_contact_columns())
    op.create_index("ix_customers_organization_id", "customers", ["organization_id"])

    op.create_table("vendors", *_tenant_audit_columns(), *_contact_columns())
    op.create_index("ix_vendors_organization_id", "vendors", ["organization_id"])

    op.create_table(
        "financial_transactions",
        *_tenant_audit_columns(),
        sa.Column("financial_account_id", sa.String(36), sa.ForeignKey("financial_accounts.id"), nullable=False),
        sa.Column("transaction_type", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="MXN"),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("source_type", sa.String(50), nullable=True),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("transfer_group_id", sa.String(36), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    )
    for column in ("organization_id", "financial_account_id", "date", "source_type", "source_id", "transfer_group_id"):
        op.create_index(f"ix_financial_transactions_{column}", "financial_transactions", [column])

    def _operation_columns(contact_table: str, contact_column: str):
        return [
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column(contact_column, sa.String(36), sa.ForeignKey(f"{contact_table}.id"), nullable=True),
            sa.Column("description", sa.String(500), nullable=False),
            sa.Column("amount", sa.Numeric(14, 2), nullable=False),
            sa.Column("category_id", sa.String(36), sa.ForeignKey("categories.id"), nullable=False),
            sa.Column("financial_account_id", sa.String(36), sa.ForeignKey("financial_accounts.id"), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
            sa.Column("notes", sa.String(1000), nullable=True),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("cancellation_reason", sa.String(500), nullable=True),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        ]

    op.create_table("incomes", *_tenant_audit_columns(), *_operation_columns("customers", "customer_id"))
    op.create_index("ix_incomes_organization_id", "incomes", ["organization_id"])
    op.create_index("ix_incomes_date", "incomes", ["date"])

    op.create_table(
        "expenses",
        *_tenant_audit_columns(),
        *_operation_columns("vendors", "vendor_id"),
        sa.Column("payment_method", sa.String(30), nullable=True),
        sa.Column("reference", sa.String(100), nullable=True),
    )
    op.create_index("ix_expenses_organization_id", "expenses", ["organization_id"])
    op.create_index("ix_expenses_date", "expenses", ["date"])


def downgrade() -> None:
    op.drop_table("expenses")
    op.drop_table("incomes")
    op.drop_table("financial_transactions")
    op.drop_table("vendors")
    op.drop_table("customers")
    op.drop_table("financial_accounts")
    op.drop_table("categories")
