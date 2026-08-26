from sqlalchemy import Column, Date, DateTime, ForeignKey, Numeric, String

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin

INCOME_STATUSES = ("PENDING", "PAID", "CANCELLED")


class Income(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Operación de negocio "vendí / me pagaron". Al pagarse genera
    FinancialTransaction + póliza contable (nunca directamente aquí)."""

    __tablename__ = "incomes"

    date = Column(Date, nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True)
    description = Column(String(500), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)  # TOTAL: lo que se mueve en efectivo
    subtotal = Column(Numeric(14, 2), nullable=False, default=0)  # base gravable
    tax_rate = Column(Numeric(5, 4), nullable=False, default=0)  # 0.1600 = 16%
    tax_amount = Column(Numeric(14, 2), nullable=False, default=0)
    category_id = Column(String(36), ForeignKey("categories.id"), nullable=False)
    # Dimensión analítica opcional: no toca el ledger.
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    financial_account_id = Column(String(36), ForeignKey("financial_accounts.id"), nullable=True)
    status = Column(String(20), nullable=False, default="PENDING")  # INCOME_STATUSES
    notes = Column(String(1000), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    cancellation_reason = Column(String(500), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
