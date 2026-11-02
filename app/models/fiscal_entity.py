from sqlalchemy import Boolean, Column, Integer, String

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin


class FiscalEntity(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Contribuyente bajo el que se declara una operación (Liza, Ale...).

    Un negocio puede operar con una sola caja y dos RFC: en vez de dos empresas,
    cada movimiento y su póliza llevan la entidad y los reportes se filtran por
    ella. Si no viene, queda "por asignar": nada se infiere.
    """

    __tablename__ = "fiscal_entities"

    name = Column(String(255), nullable=False)
    tax_id = Column(String(13), nullable=True)  # RFC, mayúsculas
    # Texto libre: "Persona física con actividad empresarial", "RESICO"...
    regime = Column(String(80), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
