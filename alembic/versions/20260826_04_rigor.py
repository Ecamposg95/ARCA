"""rigor contable: cierre de periodo y retenciones

Revision ID: 20260826_04
Revises: 20260826_03
Create Date: 2026-08-26

Cierre de periodo: candado por mes que valida el motor de pólizas.
Retenciones: columnas en gastos y cuentas por pagar, más las dos cuentas de
pasivo donde vive lo retenido mientras no se entera al SAT.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260826_04"
down_revision = "20260826_03"
branch_labels = None
depends_on = None

NEW_ACCOUNTS = (
    ("2400", "ISR Retenido por Enterar", "LIABILITY", "2000"),
    ("2410", "IVA Retenido por Enterar", "LIABILITY", "2000"),
)


def upgrade() -> None:
    op.create_table(
        "period_locks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("closed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopened_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reopen_reason", sa.String(500), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "year", "month", name="uq_period_lock"),
    )

    for table in ("expenses", "payables"):
        op.add_column(
            table,
            sa.Column("retention_isr", sa.Numeric(14, 2), nullable=False, server_default="0"),
        )
        op.add_column(
            table,
            sa.Column("retention_iva", sa.Numeric(14, 2), nullable=False, server_default="0"),
        )

    # Las empresas que ya existen necesitan las cuentas nuevas o la primera
    # retención reventaría al no encontrar dónde asentarla.
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
                sa.text("SELECT id FROM accounts WHERE organization_id = :org AND code = :code"),
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
    for table in ("expenses", "payables"):
        op.drop_column(table, "retention_iva")
        op.drop_column(table, "retention_isr")
    op.drop_table("period_locks")
    connection = op.get_bind()
    connection.execute(sa.text("DELETE FROM accounts WHERE code IN ('2400','2410')"))
