"""código agrupador del SAT por cuenta

Revision ID: 20261006_01
Revises: 20261005_01
Create Date: 2026-10-06

`accounts.sat_code`: el código agrupador del Anexo 24. Nullable; se rellena con
los defaults del catálogo de ARCA en las cuentas sembradas por el sistema que
aún no tengan uno. El diccionario va copiado: una migración no depende de
constantes vivas del código.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261006_01"
down_revision = "20261005_01"
branch_labels = None
depends_on = None

DEFAULTS = {
    "1000": "100", "1100": "102.01", "1190": "118.01", "1191": "119.01", "1200": "105.01",
    "1300": "121.01", "1400": "160.01", "1490": "171.08", "2000": "200", "2100": "201.01",
    "2190": "208.01", "2191": "209.01", "2200": "205.06", "2300": "202.01", "2400": "216.04",
    "2410": "216.10", "3000": "300", "3100": "301.01", "3200": "304.01", "4000": "400",
    "4100": "401.01", "4200": "401.01", "5000": "600", "5100": "601.84", "5200": "601.01",
    "5300": "601.46", "5400": "601.60", "5500": "601.61", "5600": "601.72", "5700": "601.84",
    "5800": "613.08", "5900": "701.04",
}  # fmt: skip


def upgrade() -> None:
    op.add_column("accounts", sa.Column("sat_code", sa.String(10), nullable=True))
    accounts = sa.table(
        "accounts",
        sa.column("code", sa.String),
        sa.column("system", sa.Boolean),
        sa.column("sat_code", sa.String),
    )
    for code, sat_code in DEFAULTS.items():
        op.execute(
            accounts.update()
            .where(accounts.c.code == code, accounts.c.system.is_(True), accounts.c.sat_code.is_(None))
            .values(sat_code=sat_code)
        )


def downgrade() -> None:
    op.drop_column("accounts", "sat_code")
