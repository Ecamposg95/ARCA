"""Modelos SQLAlchemy de ARCA.

Importar aquí cada módulo de modelos: Base.metadata solo conoce las tablas
cuyos módulos fueron importados (crítico para create_all en tests y para
autogenerate de Alembic).
"""

from app.models.organization import Organization, OrganizationMember  # noqa: F401
from app.models.user import User  # noqa: F401

