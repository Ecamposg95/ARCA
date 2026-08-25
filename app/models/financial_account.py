from sqlalchemy import Boolean, Column, Numeric, String

from app.database import Base
from app.models.mixins import AuditMixin, SoftDeleteMixin, TenantMixin, UUIDPKMixin

FINANCIAL_ACCOUNT_TYPES = ("CASH", "BANK", "CREDIT_CARD", "OTHER")

# La naturaleza decide TODO: cómo se mueve el saldo y en qué cuenta contable vive.
# Una tarjeta de crédito no guarda tu dinero: registra lo que debes.
ASSET_ACCOUNT_TYPES = ("CASH", "BANK", "OTHER")
LIABILITY_ACCOUNT_TYPES = ("CREDIT_CARD",)


def is_liability(account_type: str) -> bool:
    return account_type in LIABILITY_ACCOUNT_TYPES


class FinancialAccount(Base, UUIDPKMixin, TenantMixin, AuditMixin, SoftDeleteMixin):
    """Dónde existe el dinero (Caja, BBVA Operativa, AMEX...).

    current_balance SOLO se modifica vía app/services/transactions.py
    (lock → refresh → re-check). Nunca asignarlo directamente.
    """

    __tablename__ = "financial_accounts"

    name = Column(String(255), nullable=False)
    type = Column(String(20), nullable=False)  # FINANCIAL_ACCOUNT_TYPES
    currency = Column(String(3), nullable=False, default="MXN")
    opening_balance = Column(Numeric(14, 2), nullable=False, default=0)
    current_balance = Column(Numeric(14, 2), nullable=False, default=0)
    institution = Column(String(100), nullable=True)
    last_four = Column(String(4), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    # Sólo para tarjetas: el límite permite calcular el crédito disponible.
    credit_limit = Column(Numeric(14, 2), nullable=True)
