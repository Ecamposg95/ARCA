from sqlalchemy import Column, ForeignKey, Integer, Numeric, String

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin

RECURRING_KINDS = ("INCOME", "EXPENSE")
RECURRING_STATUSES = ("ACTIVE", "PAUSED")


class RecurringRule(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Lo que se repite igual cada mes: renta, nómina, igualas, suscripciones.

    La regla NO registra nada. Cada mes genera un borrador en la bandeja de
    Propuestas —el mismo camino que usan los agentes— y la aprobación humana
    sigue siendo la única puerta a la contabilidad. La generación es
    idempotente por (regla, mes): el patrón de la depreciación.
    """

    __tablename__ = "recurring_rules"

    kind = Column(String(20), nullable=False)  # RECURRING_KINDS
    description = Column(String(500), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)  # TOTAL con impuesto
    tax_rate = Column(Numeric(5, 4), nullable=False, default=0)
    category_id = Column(String(36), ForeignKey("categories.id"), nullable=False)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True)
    vendor_id = Column(String(36), ForeignKey("vendors.id"), nullable=True)
    # Con cuenta, el borrador se propone ya pagado desde ella; sin cuenta,
    # queda PENDING y el pago se registra cuando ocurra.
    financial_account_id = Column(
        String(36), ForeignKey("financial_accounts.id"), nullable=True
    )
    # 1–28: la regla de la casa para no pelear con febrero.
    day_of_month = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default="ACTIVE")  # RECURRING_STATUSES
    notes = Column(String(1000), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
