from sqlalchemy import Column, Date, DateTime, ForeignKey, Numeric, String

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin

# Estados persistidos. OVERDUE se CALCULA (due_date < hoy con saldo pendiente),
# nunca se almacena — evita jobs de actualización de estado.
RECEIVABLE_STATUSES = ("OPEN", "PARTIAL", "PAID", "CANCELLED")


class Receivable(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Cuenta por cobrar. Se contabiliza al emitirse (devengo §18):
    Cargo 1200 / Abono ingreso. Los cobros solo mueven 1100 ↔ 1200."""

    __tablename__ = "receivables"

    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    description = Column(String(500), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    amount_paid = Column(Numeric(14, 2), nullable=False, default=0)
    date = Column(Date, nullable=False)  # fecha de emisión
    due_date = Column(Date, nullable=False, index=True)
    category_id = Column(String(36), ForeignKey("categories.id"), nullable=False)
    status = Column(String(20), nullable=False, default="OPEN")  # RECEIVABLE_STATUSES
    notes = Column(String(1000), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    cancellation_reason = Column(String(500), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
