from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, String

from app.database import Base
from app.models.dimensions import BusinessUnitDimension
from app.models.mixins import AuditMixin, SoftDeleteMixin, TenantMixin, UUIDPKMixin

FINANCIAL_ACCOUNT_TYPES = ("CASH", "BANK", "CREDIT_CARD", "PROCESSOR", "OTHER")

# La naturaleza decide TODO: cómo se mueve el saldo y en qué cuenta contable vive.
# Una tarjeta de crédito no guarda tu dinero: registra lo que debes.
ASSET_ACCOUNT_TYPES = ("CASH", "BANK", "PROCESSOR", "OTHER")
LIABILITY_ACCOUNT_TYPES = ("CREDIT_CARD",)

# Disponible es lo que puedes gastar hoy. Un procesador de pagos (NetPay,
# Mercado Pago) es activo tuyo, pero el dinero llega al banco días después y
# menos comisión: está en tránsito, y el tablero lo muestra aparte.
AVAILABLE_ACCOUNT_TYPES = ("CASH", "BANK", "OTHER")
IN_TRANSIT_ACCOUNT_TYPES = ("PROCESSOR",)


def is_liability(account_type: str) -> bool:
    return account_type in LIABILITY_ACCOUNT_TYPES


def is_available(account_type: str) -> bool:
    return account_type in AVAILABLE_ACCOUNT_TYPES


class FinancialAccount(Base, UUIDPKMixin, TenantMixin, AuditMixin, SoftDeleteMixin, BusinessUnitDimension):
    """Dónde existe el dinero (Caja, BBVA Operativa, AMEX, NetPay...).

    current_balance SOLO se modifica vía app/services/transactions.py
    (lock → refresh → re-check). Nunca asignarlo directamente.

    `business_unit_id`: la caja de Morelos pertenece a Morelos. Las operaciones
    pagadas desde esta cuenta heredan su unidad cuando no traen una propia.
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
    # Sólo para procesadores: la comisión pactada (0.0350 = 3.5 %), en cuántos
    # días deposita y a qué banco. La tasa se guarda para validar después
    # (HU-15); hoy no calcula nada.
    fee_rate = Column(Numeric(6, 4), nullable=True)
    settlement_days = Column(Integer, nullable=True)
    settlement_account_id = Column(String(36), ForeignKey("financial_accounts.id"), nullable=True)
    # Apertura ajustable: si el saldo inicial ya se confirmó con un documento
    # (PROVISIONAL / CONFIRMED, null = nunca revisado) y de dónde sale la cifra
    # ("Estado de cuenta oct-2026", "Pendiente"). `opening_balance` sólo cambia
    # junto con un movimiento de ajuste fechado en el corte (domains/opening).
    opening_status = Column(String(20), nullable=True)
    opening_note = Column(String(255), nullable=True)
