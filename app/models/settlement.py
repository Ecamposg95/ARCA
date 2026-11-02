from sqlalchemy import Column, Date, DateTime, ForeignKey, Numeric, String

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin

SETTLEMENT_STATUSES = ("ACTIVE", "CANCELLED")


class ProcessorSettlement(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Liquidación de un procesador de pagos (NetPay deposita al banco).

    No mueve dinero por sí misma: es la cabecera de dos operaciones ya
    existentes, un traspaso procesador → banco por el neto y un gasto de
    comisión pagado desde el procesador. Cancelar la revierte con el
    mecanismo de reverso; la fila queda como CANCELLED (nunca se borra).
    """

    __tablename__ = "processor_settlements"

    processor_account_id = Column(String(36), ForeignKey("financial_accounts.id"), nullable=False, index=True)
    bank_account_id = Column(String(36), ForeignKey("financial_accounts.id"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    gross_amount = Column(Numeric(14, 2), nullable=False)  # lo que cobró el procesador
    fee_amount = Column(Numeric(14, 2), nullable=False, default=0)  # su comisión
    net_amount = Column(Numeric(14, 2), nullable=False)  # lo que llegó al banco
    # Folio del depósito. Única por empresa y procesador entre liquidaciones
    # vigentes (se valida en el service: una cancelada no estorba).
    reference = Column(String(100), nullable=True, index=True)
    notes = Column(String(1000), nullable=True)
    status = Column(String(20), nullable=False, default="ACTIVE")  # SETTLEMENT_STATUSES
    transfer_group_id = Column(String(36), nullable=False, index=True)
    expense_id = Column(String(36), ForeignKey("expenses.id"), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(String(36), ForeignKey("users.id"), nullable=True)
