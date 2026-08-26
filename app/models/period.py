from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin


class PeriodLock(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Un mes cerrado: ya se declaró y nadie debe moverlo.

    Sin esto, corregir un gasto de marzo en agosto cambia una declaración ya
    presentada y nadie se entera. El candado no borra la posibilidad de
    corregir: obliga a reabrir el mes a propósito, dejando rastro de quién y
    cuándo.
    """

    __tablename__ = "period_locks"
    __table_args__ = (
        UniqueConstraint("organization_id", "year", "month", name="uq_period_lock"),
    )

    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    closed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    reopened_at = Column(DateTime(timezone=True), nullable=True)
    reopened_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    reopen_reason = Column(String(500), nullable=True)
    notes = Column(String(1000), nullable=True)
