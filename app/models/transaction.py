from sqlalchemy import Column, Date, ForeignKey, Numeric, String

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin

TRANSACTION_TYPES = (
    "INCOME",
    "EXPENSE",
    "TRANSFER_IN",
    "TRANSFER_OUT",
    "RECEIVABLE_COLLECTION",
    "PAYABLE_PAYMENT",
    "ADJUSTMENT",
)

# Tipos que aumentan el saldo de la cuenta financiera
INFLOW_TYPES = ("INCOME", "TRANSFER_IN", "RECEIVABLE_COLLECTION")

# Cómo se movió el dinero. Normalizado (no texto libre) para poder responder
# "¿con qué gasto?" y para detectar pagos en efectivo no deducibles.
PAYMENT_METHODS = (
    "EFECTIVO",
    "TRANSFERENCIA",
    "TARJETA_DEBITO",
    "TARJETA_CREDITO",
    "DOMICILIACION",
    "CHEQUE",
    "PASARELA",
    "OTRO",
)


class FinancialTransaction(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Movimiento de dinero sobre una cuenta financiera.

    No es un asiento contable: la póliza correspondiente vive en el ledger
    (journal_entries) y referencia a la operación de negocio por source_type/source_id.
    """

    __tablename__ = "financial_transactions"

    financial_account_id = Column(String(36), ForeignKey("financial_accounts.id"), nullable=False, index=True)
    transaction_type = Column(String(30), nullable=False)  # TRANSACTION_TYPES
    amount = Column(Numeric(14, 2), nullable=False)  # siempre positivo; el signo lo da el tipo
    currency = Column(String(3), nullable=False, default="MXN")
    date = Column(Date, nullable=False, index=True)
    description = Column(String(500), nullable=False)
    reference = Column(String(100), nullable=True)
    payment_method = Column(String(20), nullable=True)  # PAYMENT_METHODS
    status = Column(String(20), nullable=False, default="ACTIVE")  # ACTIVE | CANCELLED
    source_type = Column(String(50), nullable=True, index=True)
    # 64, no 36: las claves de idempotencia de procesos periódicos son
    # compuestas (`{entidad}:{AAAA-MM}`) y no caben en un UUID pelón.
    source_id = Column(String(64), nullable=True, index=True)
    transfer_group_id = Column(String(36), nullable=True, index=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
