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
    amount = Column(Numeric(14, 2), nullable=False)
    category_id = Column(String(36), ForeignKey("categories.id"), nullable=False)
    financial_account_id = Column(String(36), ForeignKey("financial_accounts.id"), nullable=True)
    status = Column(String(20), nullable=False, default="PENDING")  # INCOME_STATUSES
    notes = Column(String(1000), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    cancellation_reason = Column(String(500), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
