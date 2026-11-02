"""Unidad de negocio y entidad fiscal: validación, herencia y etiquetado.

Las dos dimensiones son etiquetas del libro, no cuentas: aquí se valida que
pertenezcan a la empresa, se hereda la unidad desde la cuenta de dinero y se
copian a la póliza. Las reglas contables (`rules.py`) no se enteran.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import exists, or_
from sqlalchemy.orm import Session

from app.models.accounting import JournalEntry
from app.models.business_unit import BusinessUnit
from app.models.financial_account import FinancialAccount
from app.models.fiscal_entity import FiscalEntity
from app.models.transaction import FinancialTransaction


class DimensionNotFoundError(LookupError):
    """Unidad o entidad que no existe en esta empresa. Responde 404, como
    cualquier recurso ajeno: no se distingue "no existe" de "es de otro"."""


def normalize_alias(text: str) -> str:
    """Sin acentos, mayúsculas, espacios colapsados: 'vnsa   Móvil' == 'VNSA MOVIL'."""
    stripped = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in stripped if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped).strip().upper()


def derive_code(name: str) -> str:
    """Código por defecto: el nombre sin acentos ni espacios, en mayúsculas, 12 caracteres."""
    return re.sub(r"[^A-Z0-9]", "", normalize_alias(name))[:12] or "UNIDAD"


def get_business_unit(db: Session, organization_id: str, business_unit_id: str) -> BusinessUnit:
    unit = (
        db.query(BusinessUnit)
        .filter(BusinessUnit.id == business_unit_id, BusinessUnit.organization_id == organization_id)
        .first()
    )
    if unit is None:
        raise DimensionNotFoundError("La unidad de negocio no existe.")
    return unit


def get_fiscal_entity(db: Session, organization_id: str, fiscal_entity_id: str) -> FiscalEntity:
    entity = (
        db.query(FiscalEntity)
        .filter(FiscalEntity.id == fiscal_entity_id, FiscalEntity.organization_id == organization_id)
        .first()
    )
    if entity is None:
        raise DimensionNotFoundError("El contribuyente no existe.")
    return entity


def validate_dimensions(
    db: Session,
    organization_id: str,
    business_unit_id: str | None,
    fiscal_entity_id: str | None,
) -> None:
    """Para operaciones nuevas: la unidad y la entidad deben ser de la empresa y estar activas."""
    if business_unit_id:
        unit = get_business_unit(db, organization_id, business_unit_id)
        if not unit.active:
            raise ValueError(f"La unidad {unit.name} está inactiva: no acepta operaciones nuevas.")
    if fiscal_entity_id:
        entity = get_fiscal_entity(db, organization_id, fiscal_entity_id)
        if not entity.active:
            raise ValueError(f"El contribuyente {entity.name} está inactivo: no acepta operaciones nuevas.")


def inherit_business_unit(
    db: Session,
    organization_id: str,
    business_unit_id: str | None,
    financial_account_id: str | None,
) -> str | None:
    """La unidad de la operación; si no trae, la de la cuenta de dinero.

    Un gasto de Morelos pagado desde la caja central sigue siendo de Morelos:
    gana la de la operación. Nada se infiere para la entidad fiscal.
    """
    if business_unit_id or not financial_account_id:
        return business_unit_id
    account_unit = (
        db.query(FinancialAccount.business_unit_id)
        .filter(FinancialAccount.id == financial_account_id, FinancialAccount.organization_id == organization_id)
        .scalar()
    )
    return account_unit


def tag_entry(entry: JournalEntry, business_unit_id: str | None, fiscal_entity_id: str | None) -> JournalEntry:
    """Copia las dos dimensiones a una póliza ya asentada. No toca sus líneas."""
    entry.business_unit_id = business_unit_id
    entry.fiscal_entity_id = fiscal_entity_id
    return entry


def entry_filters(business_unit_id: str | None, fiscal_entity_id: str | None) -> list:
    """Condiciones sobre `JournalEntry` para balanza, reportes y diario. Sin
    filtros devuelve lista vacía: el resultado es idéntico al de siempre."""
    conditions = []
    if business_unit_id:
        conditions.append(JournalEntry.business_unit_id == business_unit_id)
    if fiscal_entity_id:
        conditions.append(JournalEntry.fiscal_entity_id == fiscal_entity_id)
    return conditions


def movement_entry_match():
    """Une un movimiento con las pólizas de su operación: mismo `source_id`
    (los reversos lo conservan) o, en un traspaso, el grupo del traspaso."""
    return or_(
        JournalEntry.source_id == FinancialTransaction.source_id,
        JournalEntry.source_id == FinancialTransaction.transfer_group_id,
    )


def transaction_filters(business_unit_id: str | None, fiscal_entity_id: str | None) -> list:
    """Condiciones sobre `FinancialTransaction` para movimientos, flujo y tablero.

    La unidad vive en el movimiento. La entidad no: se resuelve por la póliza
    de la operación que lo originó (un movimiento no declara impuestos, su
    operación sí).
    """
    conditions = []
    if business_unit_id:
        conditions.append(FinancialTransaction.business_unit_id == business_unit_id)
    if fiscal_entity_id:
        conditions.append(
            exists().where(
                JournalEntry.organization_id == FinancialTransaction.organization_id,
                JournalEntry.fiscal_entity_id == fiscal_entity_id,
                movement_entry_match(),
            )
        )
    return conditions
