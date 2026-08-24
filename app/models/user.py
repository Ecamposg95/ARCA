from sqlalchemy import Column, String

from app.database import Base
from app.models.mixins import AuditMixin, UUIDPKMixin


class User(Base, UUIDPKMixin, AuditMixin):
    __tablename__ = "users"

    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="ACTIVE")
