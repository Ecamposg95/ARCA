"""Histórico de análisis: datos del pasado (Excel de la empresa) que alimentan
gráficas y comparaciones SIN tocar la contabilidad.

No crea pólizas, movimientos ni saldos. Es una capa reemplazable: recargar
una fuente borra y vuelve a insertar los puntos de su familia en el rango que
trae el archivo (el invariante "nada se borra" aplica al libro, no a esto).
"""

from __future__ import annotations

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin, _utcnow

DATASETS = (
    "sales_daily",
    "sales_monthly",
    "sales_target",
    "pnl_monthly",
    "expense_monthly",
    "balance_monthly",
    "cash_daily",
    "snapshot",
)
GRAINS = ("day", "month", "snapshot")
SOURCE_FAMILIES = ("toronja", "control_general", "reconstruccion", "efectivo")


class HistoricalLoad(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Una carga de archivo: qué fuente, qué rango, cuántas filas y quién."""

    __tablename__ = "historical_loads"

    source = Column(String(255), nullable=False)  # "familia:archivo#hoja"
    period_from = Column(Date, nullable=False)
    period_to = Column(Date, nullable=False)
    rows = Column(Integer, nullable=False, default=0)
    loaded_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    loaded_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    notes = Column(String(500), nullable=True)


class HistoricalPoint(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Un valor agregado: dataset × métrica × periodo × dimensiones opcionales.

    Nunca lleva datos de pacientes ni estudios: los cargadores agregan antes.
    """

    __tablename__ = "historical_points"
    __table_args__ = (
        Index("ix_historical_points_series", "organization_id", "dataset", "metric", "period_start"),
    )

    load_id = Column(String(36), ForeignKey("historical_loads.id"), nullable=False, index=True)
    dataset = Column(String(30), nullable=False)  # DATASETS
    metric = Column(String(60), nullable=False)
    period_start = Column(Date, nullable=False)
    period_grain = Column(String(10), nullable=False)  # GRAINS
    business_unit_id = Column(String(36), ForeignKey("business_units.id"), nullable=True, index=True)
    unit_label = Column(String(255), nullable=True)  # etiqueta del Excel cuando no resuelve a una unidad
    fiscal_entity_id = Column(String(36), ForeignKey("fiscal_entities.id"), nullable=True, index=True)
    payment_method = Column(String(30), nullable=True)
    account_code = Column(String(30), nullable=True)
    account_label = Column(String(255), nullable=True)
    value = Column(Numeric(16, 2), nullable=False)
    source = Column(String(255), nullable=False, index=True)  # "familia:archivo#hoja"
