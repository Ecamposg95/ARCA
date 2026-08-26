from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin

FIXED_ASSET_STATUSES = ("ACTIVE", "DISPOSED")

# Vidas útiles sugeridas en meses. Son un punto de partida razonable, no una
# regla fiscal: el usuario puede cambiarlas al dar de alta el activo.
SUGGESTED_LIFE_MONTHS = {
    "EQUIPO_COMPUTO": 36,
    "MOBILIARIO": 120,
    "VEHICULOS": 48,
    "MAQUINARIA": 120,
    "EDIFICIOS": 240,
    "OTRO": 60,
}


class FixedAsset(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Algo que se compra para usar durante años, no para consumirlo este mes.

    Sin este modelo, una laptop de $40,000 se registra como gasto de agosto y
    desaparece del patrimonio: el resultado del mes queda mal y el balance
    también. Aquí el costo vive en 1400 y se lleva a gasto poco a poco (5800)
    contra la depreciación acumulada (1490).
    """

    __tablename__ = "fixed_assets"

    name = Column(String(200), nullable=False)
    category = Column(String(30), nullable=False, default="OTRO")
    acquisition_date = Column(Date, nullable=False)
    # Costo SIN IVA: el IVA es acreditable, no forma parte del activo.
    cost = Column(Numeric(14, 2), nullable=False)
    tax_amount = Column(Numeric(14, 2), nullable=False, default=0)
    # Lo que se espera recuperar al final de la vida útil; no se deprecia.
    salvage_value = Column(Numeric(14, 2), nullable=False, default=0)
    useful_life_months = Column(Integer, nullable=False)
    accumulated_depreciation = Column(Numeric(14, 2), nullable=False, default=0)
    # Con qué se pagó. Nulo significa que se registró sin salida de dinero.
    financial_account_id = Column(
        String(36), ForeignKey("financial_accounts.id"), nullable=True, index=True
    )
    vendor_id = Column(String(36), ForeignKey("vendors.id"), nullable=True)
    status = Column(String(20), nullable=False, default="ACTIVE")
    disposed_at = Column(Date, nullable=True)
    disposal_amount = Column(Numeric(14, 2), nullable=True)
    notes = Column(String(1000), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
