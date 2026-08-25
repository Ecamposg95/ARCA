"""instrumentos: tarjetas como pasivo, límite de crédito y método de pago

Revision ID: 20260825_03
Revises: 20260825_02
Create Date: 2026-08-25
"""

from alembic import op
import sqlalchemy as sa

revision = "20260825_03"
down_revision = "20260825_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("financial_accounts", sa.Column("credit_limit", sa.Numeric(14, 2), nullable=True))
    op.add_column("financial_transactions", sa.Column("payment_method", sa.String(20), nullable=True))

    connection = op.get_bind()

    # El método se deduce del instrumento con el que ya se movió el dinero.
    connection.execute(
        sa.text(
            """
            UPDATE financial_transactions
            SET payment_method = (
                SELECT CASE a.type
                    WHEN 'CASH' THEN 'EFECTIVO'
                    WHEN 'BANK' THEN 'TRANSFERENCIA'
                    WHEN 'CREDIT_CARD' THEN 'TARJETA_CREDITO'
                    ELSE 'OTRO'
                END
                FROM financial_accounts a
                WHERE a.id = financial_transactions.financial_account_id
            )
            WHERE payment_method IS NULL
            """
        )
    )

    _seed_credit_card_account(connection)
    _warn_about_existing_cards(connection)


def _seed_credit_card_account(connection) -> None:
    """Agrega 2200 Tarjetas de crédito al catálogo de cada organización."""
    from datetime import datetime, timezone
    from uuid import uuid4

    now = datetime.now(timezone.utc)
    for org in connection.execute(sa.text("SELECT id FROM organizations")).fetchall():
        exists = connection.execute(
            sa.text("SELECT 1 FROM accounts WHERE organization_id = :org AND code = '2200'"),
            {"org": org.id},
        ).first()
        if exists:
            continue
        parent = connection.execute(
            sa.text("SELECT id FROM accounts WHERE organization_id = :org AND code = '2000'"),
            {"org": org.id},
        ).scalar()
        connection.execute(
            sa.text(
                """
                INSERT INTO accounts
                    (id, organization_id, code, name, type, parent_id, active, system, created_at, updated_at)
                VALUES (:id, :org, '2200', 'Tarjetas de crédito', 'LIABILITY', :parent, :t, :t2, :now, :now)
                """
            ),
            {"id": str(uuid4()), "org": org.id, "parent": parent, "t": True, "t2": True, "now": now},
        )


def _warn_about_existing_cards(connection) -> None:
    """Las tarjetas creadas antes de esta migración quedaron contabilizadas como
    efectivo (todo iba a 1100). La corrección aplica hacia adelante; si existen
    tarjetas con movimientos, se deja constancia en el log del arranque para
    poder reclasificarlas con una póliza manual.
    """
    import logging

    cards = connection.execute(
        sa.text(
            """
            SELECT a.id, a.name, COUNT(t.id) AS movimientos
            FROM financial_accounts a
            LEFT JOIN financial_transactions t ON t.financial_account_id = a.id
            WHERE a.type = 'CREDIT_CARD'
            GROUP BY a.id, a.name
            HAVING COUNT(t.id) > 0
            """
        )
    ).fetchall()
    if cards:
        logging.getLogger("alembic").warning(
            "Tarjetas con movimientos previos a la corrección (requieren póliza de "
            "reclasificación de 1100 a 2200): %s",
            ", ".join(f"{c.name} ({c.movimientos} movimientos)" for c in cards),
        )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM accounts WHERE code = '2200'"))
    with op.batch_alter_table("financial_transactions") as batch:
        batch.drop_column("payment_method")
    with op.batch_alter_table("financial_accounts") as batch:
        batch.drop_column("credit_limit")
