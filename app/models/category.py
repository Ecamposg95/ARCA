from sqlalchemy import Boolean, Column, String, UniqueConstraint

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin

CATEGORY_KINDS = ("INCOME", "EXPENSE")


class Category(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Categoría amigable para el empresario; mapea a una cuenta contable por código."""

    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("organization_id", "kind", "name", name="uq_category_org_kind_name"),)

    name = Column(String(100), nullable=False)
    kind = Column(String(10), nullable=False)  # INCOME | EXPENSE
    account_code = Column(String(10), nullable=False)
    system = Column(Boolean, nullable=False, default=False)
    active = Column(Boolean, nullable=False, default=True)
