"""Adjuntos: la evidencia (foto del ticket, PDF o XML de la factura) vive junto
a la operación que respalda.

Los metadatos y los bytes van en tablas separadas a propósito: listar adjuntos
(o contarlos en la lista de gastos) jamás carga los archivos. Leer y escribir
bytes sólo pasa por `app/services/attachments.py`, para que mudarlos a un bucket
toque un solo módulo.
"""

from sqlalchemy import Column, ForeignKey, Index, Integer, LargeBinary, String
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.mixins import AuditMixin, SoftDeleteMixin, TenantMixin, UUIDPKMixin

# Genérico a propósito: hoy sólo gastos; mañana cuentas por pagar, ingresos...
ATTACHMENT_OWNER_TYPES = ("expense",)


class Attachment(Base, UUIDPKMixin, TenantMixin, AuditMixin, SoftDeleteMixin):
    __tablename__ = "attachments"
    __table_args__ = (Index("ix_attachments_owner", "organization_id", "owner_type", "owner_id"),)

    owner_type = Column(String(30), nullable=False)  # ATTACHMENT_OWNER_TYPES
    owner_id = Column(String(36), nullable=False)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    uploaded_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    # Nada se borra físicamente: quitar un adjunto lo oculta y deja constancia.
    deleted_by = Column(String(36), ForeignKey("users.id"), nullable=True)

    uploader = relationship("User", foreign_keys=[uploaded_by], lazy="joined", viewonly=True)

    @property
    def uploaded_by_name(self) -> str | None:
        return self.uploader.name if self.uploader is not None else None


class AttachmentBlob(Base):
    """Los bytes del archivo. Sólo se leen al descargar."""

    __tablename__ = "attachment_blobs"

    attachment_id = Column(String(36), ForeignKey("attachments.id"), primary_key=True)
    data = Column(LargeBinary, nullable=False)
