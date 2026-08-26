"""source_id a 64: las claves de idempotencia son compuestas

Revision ID: 20260826_03
Revises: 20260826_02
Create Date: 2026-08-26

La depreciación identifica su póliza con `{activo}:{AAAA-MM}`, que mide 44
caracteres. SQLite ignora el límite de VARCHAR y las pruebas pasaban; PostgreSQL
no, y en producción reventaba con StringDataRightTruncation. Se amplía la
columna en vez de acortar la clave: perder la legibilidad del identificador
sería pagar el precio equivocado.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260826_03"
down_revision = "20260826_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch_alter_table: SQLite no sabe ALTER COLUMN y Alembic lo emula
    # recreando la tabla. PostgreSQL hace el ALTER directo.
    for table in ("journal_entries", "financial_transactions"):
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "source_id",
                existing_type=sa.String(36),
                type_=sa.String(64),
                existing_nullable=True,
            )


def downgrade() -> None:
    # Sólo es seguro si nadie usó claves compuestas todavía.
    for table in ("journal_entries", "financial_transactions"):
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "source_id",
                existing_type=sa.String(64),
                type_=sa.String(36),
                existing_nullable=True,
            )
