"""folios de póliza: contador por organización/tipo/mes y respaldo de asientos existentes

Revision ID: 20260825_01
Revises: 20260824_05
Create Date: 2026-08-25
"""

from alembic import op
import sqlalchemy as sa

revision = "20260825_01"
down_revision = "20260824_05"
branch_labels = None
depends_on = None

PREFIXES = {"INGRESO": "Ig", "EGRESO": "Eg", "DIARIO": "Dr"}


def upgrade() -> None:
    op.create_table(
        "folio_counters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "kind", "period", name="uq_folio_counter_scope"),
    )
    op.create_index("ix_folio_counters_organization_id", "folio_counters", ["organization_id"])

    op.add_column("journal_entries", sa.Column("folio", sa.String(20), nullable=True))
    op.add_column("journal_entries", sa.Column("kind", sa.String(10), nullable=True))

    _backfill()

    with op.batch_alter_table("journal_entries") as batch:
        batch.alter_column("folio", existing_type=sa.String(20), nullable=False)
        batch.alter_column("kind", existing_type=sa.String(10), nullable=False)
        batch.create_unique_constraint("uq_journal_entry_org_folio", ["organization_id", "folio"])


def _backfill() -> None:
    """Asigna folio a las pólizas existentes en orden cronológico.

    La naturaleza se deduce del movimiento de Caja y Bancos (1100): cargo =
    ingreso, abono = egreso; los saldos iniciales y los traspasos (que tocan
    1100 en ambos lados) quedan como póliza de diario.
    """
    from datetime import datetime, timezone
    from uuid import uuid4

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT e.id, e.organization_id, e.date, e.source_type,
                   COALESCE(SUM(CASE WHEN a.code = '1100' THEN l.debit ELSE 0 END), 0) AS cash_debit,
                   COALESCE(SUM(CASE WHEN a.code = '1100' THEN l.credit ELSE 0 END), 0) AS cash_credit
            FROM journal_entries e
            LEFT JOIN journal_entry_lines l ON l.journal_entry_id = e.id
            LEFT JOIN accounts a ON a.id = l.account_id
            GROUP BY e.id, e.organization_id, e.date, e.source_type
            ORDER BY e.date, e.created_at
            """
        )
    ).fetchall()

    counters: dict[tuple[str, str, str], int] = {}
    now = datetime.now(timezone.utc)

    for row in rows:
        entry_date = row.date if hasattr(row.date, "year") else datetime.fromisoformat(str(row.date)).date()
        cash_debit = float(row.cash_debit or 0)
        cash_credit = float(row.cash_credit or 0)

        if row.source_type == "financial_account" or (cash_debit > 0 and cash_credit > 0):
            kind = "DIARIO"
        elif cash_debit > 0:
            kind = "INGRESO"
        elif cash_credit > 0:
            kind = "EGRESO"
        else:
            kind = "DIARIO"

        period = f"{entry_date.year:04d}-{entry_date.month:02d}"
        key = (row.organization_id, kind, period)
        number = counters.get(key, 0) + 1
        counters[key] = number

        connection.execute(
            sa.text("UPDATE journal_entries SET folio = :folio, kind = :kind WHERE id = :id"),
            {"folio": f"{PREFIXES[kind]}-{period}-{number:04d}", "kind": kind, "id": row.id},
        )

    for (organization_id, kind, period), used in counters.items():
        connection.execute(
            sa.text(
                """
                INSERT INTO folio_counters
                    (id, organization_id, kind, period, next_number, created_at, updated_at)
                VALUES (:id, :org, :kind, :period, :next_number, :now, :now)
                """
            ),
            {
                "id": str(uuid4()),
                "org": organization_id,
                "kind": kind,
                "period": period,
                "next_number": used + 1,
                "now": now,
            },
        )


def downgrade() -> None:
    with op.batch_alter_table("journal_entries") as batch:
        batch.drop_constraint("uq_journal_entry_org_folio", type_="unique")
        batch.drop_column("kind")
        batch.drop_column("folio")
    op.drop_table("folio_counters")
