"""apertura provisional y ajustable a la fecha de corte

Revision ID: 20261103_03
Revises: 20261103_02
Create Date: 2026-11-03

La fecha de corte y el estado de la apertura en `organizations`, el estado y
la fuente del saldo inicial en `financial_accounts`, y la cuenta puente 3901
"Saldos de apertura por identificar" sembrada en las empresas que ya existen
(como 1110 en 20261102_04). Columnas nullables: nada existente cambia.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261103_03"
down_revision = "20261103_02"
branch_labels = None
depends_on = None

BRIDGE = ("3901", "Saldos de apertura por identificar", "EQUITY", "3000", "306.01")


def upgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.add_column(sa.Column("opening_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("opening_status", sa.String(20), nullable=True))
    with op.batch_alter_table("financial_accounts") as batch:
        batch.add_column(sa.Column("opening_status", sa.String(20), nullable=True))
        batch.add_column(sa.Column("opening_note", sa.String(255), nullable=True))

    # --- Backfill de 3901 en las empresas que ya existen ---
    connection = op.get_bind()
    code, name, account_type, parent_code, sat_code = BRIDGE
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
    connection = op.get_bind()
    # Sólo se quita la puente que nadie usó: una 3901 con pólizas es historia contable.
    connection.execute(
        sa.text(
            "DELETE FROM accounts WHERE code = '3901' AND system = :system "
            "AND id NOT IN (SELECT account_id FROM journal_entry_lines)"
        ),
        {"system": True},
    )
    with op.batch_alter_table("financial_accounts") as batch:
        batch.drop_column("opening_note")
        batch.drop_column("opening_status")
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("opening_status")
        batch.drop_column("opening_date")
