"""dinero en tránsito y corte de caja

Revision ID: 20261102_04
Revises: 20261102_03
Create Date: 2026-11-02

Tipo PROCESSOR en cuentas de dinero (tasa, días y banco donde liquida), la
cuenta de mayor 1110 "Cobros en tránsito" sembrada en las empresas que ya
existen, `processor_settlements` y `cash_cuts`. Una empresa sin procesadores
ni cortes no cambia en nada.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261102_04"
down_revision = "20261102_03"
branch_labels = None
depends_on = None

IN_TRANSIT = ("1110", "Cobros en tránsito", "ASSET", "1000", "107.05")


def upgrade() -> None:
    # Batch: en PostgreSQL son ALTER normales; en SQLite (pruebas locales) copia y mueve.
    with op.batch_alter_table("financial_accounts") as batch:
        batch.add_column(sa.Column("fee_rate", sa.Numeric(6, 4), nullable=True))
        batch.add_column(sa.Column("settlement_days", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("settlement_account_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_financial_accounts_settlement_account",
            "financial_accounts",
            ["settlement_account_id"],
            ["id"],
        )

    op.create_table(
        "processor_settlements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column(
            "processor_account_id",
            sa.String(36),
            sa.ForeignKey("financial_accounts.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("bank_account_id", sa.String(36), sa.ForeignKey("financial_accounts.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False, index=True),
        sa.Column("gross_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("fee_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("reference", sa.String(100), nullable=True, index=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("transfer_group_id", sa.String(36), nullable=False, index=True),
        sa.Column("expense_id", sa.String(36), sa.ForeignKey("expenses.id"), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "cash_cuts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column(
            "financial_account_id",
            sa.String(36),
            sa.ForeignKey("financial_accounts.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("business_unit_id", sa.String(36), sa.ForeignKey("business_units.id"), nullable=True, index=True),
        sa.Column("date", sa.Date(), nullable=False, index=True),
        sa.Column("opening_balance", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("inflows", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("outflows", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("expected_closing", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("counted_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("difference", sa.Numeric(14, 2), nullable=True),
        sa.Column("explanation", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("delivered_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("delivered_to_account_id", sa.String(36), sa.ForeignKey("financial_accounts.id"), nullable=True),
        sa.Column("delivered_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transfer_group_id", sa.String(36), nullable=True, index=True),
        sa.Column(
            "adjustment_transaction_id",
            sa.String(36),
            sa.ForeignKey("financial_transactions.id"),
            nullable=True,
        ),
        sa.Column("closed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- Backfill de 1110 en las empresas que ya existen (como hizo patrimonio) ---
    connection = op.get_bind()
    code, name, account_type, parent_code, sat_code = IN_TRANSIT
    organizations = [row[0] for row in connection.execute(sa.text("SELECT id FROM organizations")).fetchall()]
    for organization_id in organizations:
        exists = connection.execute(
            sa.text("SELECT id FROM accounts WHERE organization_id = :org AND code = :code"),
            {"org": organization_id, "code": code},
        ).fetchone()
        if exists:
            continue
        parent = connection.execute(
            sa.text("SELECT id FROM accounts WHERE organization_id = :org AND code = :code"),
            {"org": organization_id, "code": parent_code},
        ).fetchone()
        connection.execute(
            sa.text(
                """
                INSERT INTO accounts
                    (id, organization_id, code, name, type, parent_id, active, system, sat_code,
                     created_at, updated_at)
                VALUES
                    (:id, :org, :code, :name, :type, :parent, :active, :system, :sat_code,
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
                "sat_code": sat_code,
            },
        )


def downgrade() -> None:
    op.drop_table("cash_cuts")
    op.drop_table("processor_settlements")
    with op.batch_alter_table("financial_accounts") as batch:
        batch.drop_constraint("fk_financial_accounts_settlement_account", type_="foreignkey")
        batch.drop_column("settlement_account_id")
        batch.drop_column("settlement_days")
        batch.drop_column("fee_rate")
    connection = op.get_bind()
    connection.execute(sa.text("DELETE FROM accounts WHERE code = '1110' AND system = :system"), {"system": True})
