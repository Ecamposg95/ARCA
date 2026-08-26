from sqlalchemy import Column, Date, DateTime, ForeignKey, Numeric, String

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin

PROJECT_STATUSES = ("ACTIVE", "CLOSED", "CANCELLED")


class Project(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Una dimensión analítica, no una cuenta contable.

    Marcar ingresos y gastos con un proyecto permite saber cuál deja dinero y
    cuál se lo come. Deliberadamente NO toca el ledger: la contabilidad no
    cambia porque un trabajo se llame de una forma u otra.
    """

    __tablename__ = "projects"

    name = Column(String(200), nullable=False)
    code = Column(String(30), nullable=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True, index=True)
    description = Column(String(1000), nullable=True)
    # Lo que se acordó cobrar. Sirve para comparar contra lo realmente facturado.
    budget = Column(Numeric(14, 2), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="ACTIVE")
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
