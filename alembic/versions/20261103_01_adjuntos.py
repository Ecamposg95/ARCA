"""adjuntos: foto del ticket y PDF/XML de la factura en cada gasto

Revision ID: 20261103_01
Revises: 20261102_04
Create Date: 2026-11-03

`attachments` guarda los metadatos (genérico por `owner_type`/`owner_id`; hoy
sólo "expense") con baja lógica (`deleted_at`/`deleted_by`). Los bytes viven
aparte en `attachment_blobs` para que listar o contar adjuntos nunca los lea.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261103_01"
down_revision = "20261102_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("owner_type", sa.String(30), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("uploaded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_attachments_owner", "attachments", ["organization_id", "owner_type", "owner_id"])
    op.create_table(
        "attachment_blobs",
        sa.Column("attachment_id", sa.String(36), sa.ForeignKey("attachments.id"), primary_key=True),
        sa.Column("data", sa.LargeBinary(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("attachment_blobs")
    op.drop_index("ix_attachments_owner", table_name="attachments")
    op.drop_table("attachments")
