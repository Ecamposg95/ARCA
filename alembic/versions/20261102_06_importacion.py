"""importación: lotes y filas de Toronja y archivos de Excel/CSV, ajustes por empresa

Revision ID: 20261102_06
Revises: 20261102_05
Create Date: 2026-11-02

`import_batches` (un archivo subido, en PREVIEW hasta confirmarse) e
`import_rows` (una fila leída y clasificada; `external_id` es el folio de
Toronja o un hash, y un `external_id` ya CREATED en la empresa es duplicado).
`organizations.import_settings` guarda las cuentas destino de Toronja.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261102_06"
down_revision = "20261102_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("import_settings", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_table(
        "import_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PREVIEW"),
        sa.Column("mapping", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("options", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "import_rows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("import_batches.id"), nullable=False, index=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(120), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="OK"),
        sa.Column("message", sa.String(500), nullable=True),
        sa.Column("result_type", sa.String(30), nullable=True),
        sa.Column("result_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_import_rows_org_kind_external", "import_rows", ["organization_id", "kind", "external_id"]
    )
    op.create_index("ix_import_rows_batch_status", "import_rows", ["batch_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_import_rows_batch_status", table_name="import_rows")
    op.drop_index("ix_import_rows_org_kind_external", table_name="import_rows")
    op.drop_table("import_rows")
    op.drop_table("import_batches")
    op.drop_column("organizations", "import_settings")
