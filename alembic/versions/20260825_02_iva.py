"""IVA: desglose en operaciones, tasa por organización y cuentas de impuesto

Revision ID: 20260825_02
Revises: 20260825_01
Create Date: 2026-08-25
"""

from alembic import op
import sqlalchemy as sa

revision = "20260825_02"
down_revision = "20260825_01"
branch_labels = None
depends_on = None

OPERATION_TABLES = ("incomes", "expenses", "receivables", "payables")

# (código, nombre, tipo, código del padre)
VAT_ACCOUNTS = (
    ("1190", "IVA acreditable pagado", "ASSET", "1000"),
    ("1191", "IVA acreditable pendiente de pago", "ASSET", "1000"),
    ("2190", "IVA trasladado cobrado", "LIABILITY", "2000"),
    ("2191", "IVA trasladado pendiente de cobro", "LIABILITY", "2000"),
)


def upgrade() -> None:
    for table in OPERATION_TABLES:
        op.add_column(table, sa.Column("subtotal", sa.Numeric(14, 2), nullable=True))
        op.add_column(table, sa.Column("tax_rate", sa.Numeric(5, 4), nullable=True))
        op.add_column(table, sa.Column("tax_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("receivables", sa.Column("tax_collected", sa.Numeric(14, 2), nullable=True))
    op.add_column("payables", sa.Column("tax_paid", sa.Numeric(14, 2), nullable=True))
    op.add_column("organizations", sa.Column("default_tax_rate", sa.Numeric(5, 4), nullable=True))

    connection = op.get_bind()

    # Decisión de producto: lo registrado antes del módulo de IVA se asume SIN IVA.
    for table in OPERATION_TABLES:
        connection.execute(
            sa.text(f"UPDATE {table} SET subtotal = amount, tax_rate = 0, tax_amount = 0")
        )
    connection.execute(sa.text("UPDATE receivables SET tax_collected = 0"))
    connection.execute(sa.text("UPDATE payables SET tax_paid = 0"))
    # Las empresas que ya existen arrancan con la tasa general.
    connection.execute(sa.text("UPDATE organizations SET default_tax_rate = 0.16"))

    _seed_vat_accounts(connection)

    for table in OPERATION_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.alter_column("subtotal", existing_type=sa.Numeric(14, 2), nullable=False)
            batch.alter_column("tax_rate", existing_type=sa.Numeric(5, 4), nullable=False)
            batch.alter_column("tax_amount", existing_type=sa.Numeric(14, 2), nullable=False)
    with op.batch_alter_table("receivables") as batch:
        batch.alter_column("tax_collected", existing_type=sa.Numeric(14, 2), nullable=False)
    with op.batch_alter_table("payables") as batch:
        batch.alter_column("tax_paid", existing_type=sa.Numeric(14, 2), nullable=False)
    with op.batch_alter_table("organizations") as batch:
        batch.alter_column("default_tax_rate", existing_type=sa.Numeric(5, 4), nullable=False)


def _seed_vat_accounts(connection) -> None:
    """Agrega las cuentas de IVA al catálogo de cada organización existente."""
    from datetime import datetime, timezone
    from uuid import uuid4

    now = datetime.now(timezone.utc)
    organizations = connection.execute(sa.text("SELECT id FROM organizations")).fetchall()

    for org in organizations:
        existing = {
            row.code
            for row in connection.execute(
                sa.text("SELECT code FROM accounts WHERE organization_id = :org"), {"org": org.id}
            ).fetchall()
        }
        parents = {
            row.code: row.id
            for row in connection.execute(
                sa.text("SELECT id, code FROM accounts WHERE organization_id = :org AND code IN ('1000', '2000')"),
                {"org": org.id},
            ).fetchall()
        }
        for code, name, account_type, parent_code in VAT_ACCOUNTS:
            if code in existing:
                continue
            connection.execute(
                sa.text(
                    """
                    INSERT INTO accounts
                        (id, organization_id, code, name, type, parent_id, active, system, created_at, updated_at)
                    VALUES (:id, :org, :code, :name, :type, :parent, :active, :system, :now, :now)
                    """
                ),
                {
                    "id": str(uuid4()),
                    "org": org.id,
                    "code": code,
                    "name": name,
                    "type": account_type,
                    "parent": parents.get(parent_code),
                    "active": True,
                    "system": True,
                    "now": now,
                },
            )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM accounts WHERE code IN ('1190', '1191', '2190', '2191')")
    )
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("default_tax_rate")
    with op.batch_alter_table("payables") as batch:
        batch.drop_column("tax_paid")
    with op.batch_alter_table("receivables") as batch:
        batch.drop_column("tax_collected")
    for table in OPERATION_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_column("tax_amount")
            batch.drop_column("tax_rate")
            batch.drop_column("subtotal")
