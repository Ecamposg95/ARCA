from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin

LOAN_STATUSES = ("ACTIVE", "PAID", "CANCELLED")


class Loan(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Un crédito con su tabla de amortización.

    La razón de existir: el pago de un préstamo NO es todo gasto. La mayor parte
    reduce la deuda (2300) y sólo los intereses son gasto (5900). Sin separarlos,
    un crédito distorsiona el resultado del mes y el patrimonio nunca cuadra.
    """

    __tablename__ = "loans"

    lender = Column(String(200), nullable=False)
    description = Column(String(500), nullable=False)
    principal = Column(Numeric(14, 2), nullable=False)  # monto original
    outstanding = Column(Numeric(14, 2), nullable=False)  # capital que aún debes
    # Tasa ANUAL en decimal: 0.2400 = 24%. La mensual se deriva al calcular.
    annual_rate = Column(Numeric(6, 4), nullable=False, default=0)
    term_months = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False)
    payment_day = Column(Integer, nullable=False, default=1)
    # Dónde entró el dinero prestado.
    financial_account_id = Column(
        String(36), ForeignKey("financial_accounts.id"), nullable=True, index=True
    )
    status = Column(String(20), nullable=False, default="ACTIVE")
    notes = Column(String(1000), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)


class LoanPayment(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Un pago del crédito, ya partido en capital e intereses."""

    __tablename__ = "loan_payments"

    loan_id = Column(String(36), ForeignKey("loans.id"), nullable=False, index=True)
    date = Column(Date, nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)  # lo que sale del banco
    principal_part = Column(Numeric(14, 2), nullable=False)
    interest_part = Column(Numeric(14, 2), nullable=False)
    financial_account_id = Column(
        String(36), ForeignKey("financial_accounts.id"), nullable=False, index=True
    )
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
