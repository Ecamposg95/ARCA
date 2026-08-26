from sqlalchemy import Column, Date, DateTime, ForeignKey, Numeric, String

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin

PAYABLE_STATUSES = ("OPEN", "PARTIAL", "PAID", "CANCELLED")


class Payable(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Cuenta por pagar. Se contabiliza al registrarse (devengo §18):
    Cargo gasto / Abono 2100. Los pagos solo mueven 2100 ↔ 1100."""

    __tablename__ = "payables"

    vendor_id = Column(String(36), ForeignKey("vendors.id"), nullable=False, index=True)
    description = Column(String(500), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)  # TOTAL: lo que se mueve en efectivo
    subtotal = Column(Numeric(14, 2), nullable=False, default=0)  # base gravable
    tax_rate = Column(Numeric(5, 4), nullable=False, default=0)  # 0.1600 = 16%
    tax_amount = Column(Numeric(14, 2), nullable=False, default=0)
    amount_paid = Column(Numeric(14, 2), nullable=False, default=0)
    # IVA que ya pasó de 'pendiente de pago' a acreditable.
    tax_paid = Column(Numeric(14, 2), nullable=False, default=0)
    date = Column(Date, nullable=False)  # fecha de registro del compromiso
    due_date = Column(Date, nullable=False, index=True)
    category_id = Column(String(36), ForeignKey("categories.id"), nullable=False)
    # Dimensión analítica opcional: no toca el ledger.
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="OPEN")  # PAYABLE_STATUSES
    notes = Column(String(1000), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    cancellation_reason = Column(String(500), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
