"""Dimensiones opcionales del libro: unidad de negocio y entidad fiscal.

Cada mixin agrega la FK (nullable, con índice) y una relación de sólo lectura
para serializar el nombre sin una consulta por fila. Son etiquetas: no tocan
la partida doble ni cambian a qué cuentas va una operación.
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.orm import declarative_mixin, declared_attr, relationship


@declarative_mixin
class BusinessUnitDimension:
    @declared_attr
    def business_unit_id(cls):
        return Column(String(36), ForeignKey("business_units.id"), nullable=True, index=True)

    @declared_attr
    def business_unit(cls):
        return relationship("BusinessUnit", lazy="joined", viewonly=True)

    @property
    def business_unit_name(self) -> str | None:
        return self.business_unit.name if self.business_unit is not None else None


@declarative_mixin
class FiscalEntityDimension:
    @declared_attr
    def fiscal_entity_id(cls):
        return Column(String(36), ForeignKey("fiscal_entities.id"), nullable=True, index=True)

    @declared_attr
    def fiscal_entity(cls):
        return relationship("FiscalEntity", lazy="joined", viewonly=True)

    @property
    def fiscal_entity_name(self) -> str | None:
        return self.fiscal_entity.name if self.fiscal_entity is not None else None
