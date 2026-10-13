from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin


class FiscalYearLock(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Un ejercicio cerrado: su resultado ya pasó a Resultados Acumulados.

    Es el candado anual. Como el de mes, no impide corregir: obliga a reabrir
    el año a propósito, con motivo, y la reapertura revierte la póliza de
    cierre para que el libro vuelva a mostrar ingresos y gastos vivos.
    """

    __tablename__ = "fiscal_year_locks"
    __table_args__ = (UniqueConstraint("organization_id", "year", name="uq_fiscal_year_lock"),)

    year = Column(Integer, nullable=False)
    closed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    # None cuando el año no tuvo ingresos ni gastos: se cierra sin póliza.
    closing_entry_id = Column(String(36), ForeignKey("journal_entries.id"), nullable=True)
    reopened_at = Column(DateTime(timezone=True), nullable=True)
    reopened_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    reopen_reason = Column(String(500), nullable=True)
    notes = Column(String(1000), nullable=True)
