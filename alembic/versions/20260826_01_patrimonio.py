"""patrimonio: activos fijos con depreciación y préstamos con amortización

Revision ID: 20260826_01
Revises: 20260825_03
Create Date: 2026-08-26

Agrega las tablas de los dos módulos y siembra las cuentas contables que
necesitan (1400, 1490, 2300, 5800, 5900) en las organizaciones que ya existen.
Sin ese backfill, la primera compra de activo fijo de una empresa vieja
reventaría al no encontrar su cuenta.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260826_01"
down_revision = "20260825_03"
branch_labels = None
depends_on = None

# (code, name, type, parent_code)
NEW_ACCOUNTS = (
    ("1400", "Activo Fijo", "ASSET", "1000"),
    ("1490", "Depreciación Acumulada", "ASSET", "1000"),
    ("2300", "Préstamos por Pagar", "LIABILITY", "2000"),
    ("5800", "Depreciación", "EXPENSE", "5000"),
    ("5900", "Intereses", "EXPENSE", "5000"),
)


def upgrade() -> None:
    op.create_table(
        "fixed_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(30), nullable=False, server_default="OTRO"),
        sa.Column("acquisition_date", sa.Date(), nullable=False),
        sa.Column("cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("salvage_value", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("useful_life_months", sa.Integer(), nullable=False),
        sa.Column(
            "accumulated_depreciation", sa.Numeric(14, 2), nullable=False, server_default="0"
        ),
        sa.Column(
            "financial_account_id",
            sa.String(36),
            sa.ForeignKey("financial_accounts.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("vendor_id", sa.String(36), sa.ForeignKey("vendors.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("disposed_at", sa.Date(), nullable=True),
        sa.Column("disposal_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "loans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("lender", sa.String(200), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("principal", sa.Numeric(14, 2), nullable=False),
        sa.Column("outstanding", sa.Numeric(14, 2), nullable=False),
        sa.Column("annual_rate", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("term_months", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("payment_day", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "financial_account_id",
            sa.String(36),
            sa.ForeignKey("financial_accounts.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "loan_payments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("loan_id", sa.String(36), sa.ForeignKey("loans.id"), nullable=False, index=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("principal_part", sa.Numeric(14, 2), nullable=False),
        sa.Column("interest_part", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "financial_account_id",
            sa.String(36),
            sa.ForeignKey("financial_accounts.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- Backfill del catálogo contable en las empresas que ya existen ---
    connection = op.get_bind()
    organizations = [
        row[0] for row in connection.execute(sa.text("SELECT id FROM organizations")).fetchall()
    ]

    for organization_id in organizations:
        existing = {
            row[0]
            for row in connection.execute(
                sa.text("SELECT code FROM accounts WHERE organization_id = :org"),
                {"org": organization_id},
            ).fetchall()
        }
        for code, name, account_type, parent_code in NEW_ACCOUNTS:
            if code in existing:
                continue
            parent = connection.execute(
                sa.text(
                    "SELECT id FROM accounts WHERE organization_id = :org AND code = :code"
                ),
                {"org": organization_id, "code": parent_code},
            ).fetchone()
            connection.execute(
                sa.text(
                    """
                    INSERT INTO accounts
                        (id, organization_id, code, name, type, parent_id, active, system,
                         created_at, updated_at)
                    VALUES
                        (:id, :org, :code, :name, :type, :parent, :active, :system,
                         CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {
                    "id": f"{organization_id[:8]}-acct-{code}",
                    "org": organization_id,
                    "code": code,
                    "name": name,
                    "type": account_type,
                    "parent": parent[0] if parent else None,
                    "active": True,
                    "system": True,
                },
            )


def downgrade() -> None:
    op.drop_table("loan_payments")
    op.drop_table("loans")
    op.drop_table("fixed_assets")
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM accounts WHERE code IN ('1400','1490','2300','5800','5900')")
    )
