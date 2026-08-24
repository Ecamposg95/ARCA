from sqlalchemy import Column, String

from app.database import Base
from app.models.mixins import AuditMixin, SoftDeleteMixin, TenantMixin, UUIDPKMixin


class _ContactColumns:
    name = Column(String(255), nullable=False)
    legal_name = Column(String(255), nullable=True)
    tax_id = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(30), nullable=True)
    notes = Column(String(1000), nullable=True)
    status = Column(String(20), nullable=False, default="ACTIVE")


class Customer(Base, UUIDPKMixin, TenantMixin, AuditMixin, SoftDeleteMixin, _ContactColumns):
    __tablename__ = "customers"


class Vendor(Base, UUIDPKMixin, TenantMixin, AuditMixin, SoftDeleteMixin, _ContactColumns):
    __tablename__ = "vendors"
