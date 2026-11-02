from sqlalchemy import Column, Date, DateTime, ForeignKey, Numeric, String

from app.database import Base
from app.models.dimensions import BusinessUnitDimension
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin

# OPEN → COUNTED → DELIVERED. CANCELLED en cualquier punto: la fila queda
# (invariante 8) y el ajuste y la entrega se revierten con pólizas espejo.
CASH_CUT_STATUSES = ("OPEN", "COUNTED", "DELIVERED", "CANCELLED")


class CashCut(Base, UUIDPKMixin, TenantMixin, AuditMixin, BusinessUnitDimension):
    """Corte de caja de un día: lo que debía haber, lo que se contó y a quién
    se entregó.

    Tampoco mueve dinero por sí mismo: la diferencia es un ingreso o gasto
    "Diferencias de caja" y la entrega es un traspaso caja → destino. Uno por
    caja y día entre cortes vigentes (se valida en el service).
    """

    __tablename__ = "cash_cuts"

    financial_account_id = Column(String(36), ForeignKey("financial_accounts.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    # Saldo antes del primer movimiento del día, y los movimientos del día.
    opening_balance = Column(Numeric(14, 2), nullable=False, default=0)
    inflows = Column(Numeric(14, 2), nullable=False, default=0)
    outflows = Column(Numeric(14, 2), nullable=False, default=0)
    expected_closing = Column(Numeric(14, 2), nullable=False, default=0)
    counted_amount = Column(Numeric(14, 2), nullable=True)
    difference = Column(Numeric(14, 2), nullable=True)  # contado − esperado
    explanation = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, default="OPEN")  # CASH_CUT_STATUSES
    delivered_amount = Column(Numeric(14, 2), nullable=True)
    delivered_to_account_id = Column(String(36), ForeignKey("financial_accounts.id"), nullable=True)
    delivered_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    received_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=True)
    transfer_group_id = Column(String(36), nullable=True, index=True)
    # El movimiento de ajuste vigente en la caja; su operación (ingreso o
    # gasto) se encuentra por source_type/source_id del movimiento.
    adjustment_transaction_id = Column(String(36), ForeignKey("financial_transactions.id"), nullable=True)
    closed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(String(36), ForeignKey("users.id"), nullable=True)
