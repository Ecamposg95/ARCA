"""marca por empresa

Revision ID: 20261112_01
Revises: 20261103_04
Create Date: 2026-11-12

La empresa puede llevar la identidad de su negocio (acento y logotipo) sobre
ONE Finance. Sólo se guarda la clave de la marca; null = ONE Finance.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261112_01"
down_revision = "20261103_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("brand", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "brand")
