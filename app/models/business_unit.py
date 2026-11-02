from sqlalchemy import JSON, Boolean, Column, Date, Integer, String, UniqueConstraint

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin

BUSINESS_UNIT_KINDS = ("MATRIZ", "TOMA_MUESTRA", "UNIDAD_MOVIL", "CANAL", "OTRA")


class BusinessUnit(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Sucursal, toma de muestra, unidad móvil o canal: una dimensión del libro.

    Es una etiqueta, no una cuenta contable: marcar una operación con una unidad
    nunca cambia a qué cuentas va. Sirve para ver cajas, ingresos, gastos y
    reportes por unidad sin partir el negocio en varias empresas.
    """

    __tablename__ = "business_units"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_business_unit_org_code"),)

    name = Column(String(255), nullable=False)
    # Mayúsculas, sin espacios; se deriva del nombre si no viene.
    code = Column(String(12), nullable=False)
    kind = Column(String(20), nullable=False, default="OTRA")  # BUSINESS_UNIT_KINDS
    active = Column(Boolean, nullable=False, default=True)
    opened_on = Column(Date, nullable=True)
    # Nombres con los que el punto de venta (Toronja) llama a esta unidad. Se
    # guardan como vienen; la comparación normaliza (sin acentos ni mayúsculas).
    aliases = Column(JSON, nullable=False, default=list)
    sort_order = Column(Integer, nullable=False, default=0)
