"""cuenta equivalente en CONTPAQi

Revision ID: 20261005_01
Revises: 20260827_01
Create Date: 2026-10-05

`accounts.contpaqi_code`: el número de la misma cuenta en el CONTPAQi del
contador. Nullable: una cuenta sin equivalente se exporta con su código de ARCA.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261005_01"
down_revision = "20260827_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("contpaqi_code", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("accounts", "contpaqi_code")
