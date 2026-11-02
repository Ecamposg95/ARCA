"""Unidades de negocio: alta, edición y desactivación. Nunca se borran."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.business_unit import BUSINESS_UNIT_KINDS, BusinessUnit
from app.models.financial_account import FinancialAccount
from app.services.dimensions import derive_code, normalize_alias


def _others(db: Session, organization_id: str, exclude_id: str | None):
    query = db.query(BusinessUnit).filter(BusinessUnit.organization_id == organization_id)
    if exclude_id:
        query = query.filter(BusinessUnit.id != exclude_id)
    return query


def _assert_name_free(db: Session, organization_id: str, name: str, exclude_id: str | None) -> None:
    taken = _others(db, organization_id, exclude_id).filter(func.lower(BusinessUnit.name) == name.lower()).first()
    if taken is not None:
        raise ValueError(f"Ya existe una unidad llamada {taken.name}.")


def _assert_code_free(db: Session, organization_id: str, code: str, exclude_id: str | None) -> None:
    if _others(db, organization_id, exclude_id).filter(BusinessUnit.code == code).first() is not None:
        raise ValueError(f"El código {code} ya lo usa otra unidad.")


def _assert_single_matriz(db: Session, organization_id: str, exclude_id: str | None) -> None:
    other = (
        _others(db, organization_id, exclude_id)
        .filter(BusinessUnit.kind == "MATRIZ", BusinessUnit.active.is_(True))
        .first()
    )
    if other is not None:
        raise ValueError(f"Sólo puede haber una matriz activa; hoy es {other.name}.")


def _clean_aliases(db: Session, organization_id: str, aliases: list[str], exclude_id: str | None) -> list[str]:
    """Se guardan como vienen; se comparan normalizados, dentro y entre unidades."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        alias = alias.strip()
        if not alias:
            continue
        key = normalize_alias(alias)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(alias)
    if not seen:
        return cleaned
    for unit in _others(db, organization_id, exclude_id).all():
        for existing in unit.aliases or []:
            if normalize_alias(existing) in seen:
                raise ValueError(f"El alias «{existing}» ya pertenece a la unidad {unit.name}.")
    return cleaned


def create_business_unit(db: Session, organization_id: str, payload) -> BusinessUnit:
    name = payload.name.strip()
    code = (payload.code or "").strip().upper() or derive_code(name)
    if payload.kind not in BUSINESS_UNIT_KINDS:
        raise ValueError("Tipo de unidad inválido.")
    _assert_name_free(db, organization_id, name, None)
    _assert_code_free(db, organization_id, code, None)
    if payload.kind == "MATRIZ":
        _assert_single_matriz(db, organization_id, None)

    unit = BusinessUnit(
        organization_id=organization_id,
        name=name,
        code=code,
        kind=payload.kind,
        opened_on=payload.opened_on,
        aliases=_clean_aliases(db, organization_id, payload.aliases, None),
        sort_order=payload.sort_order,
    )
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return unit


def _assert_can_deactivate(db: Session, unit: BusinessUnit) -> None:
    """Una unidad con cajas activas y saldo no se apaga: el dinero quedaría huérfano."""
    with_balance = (
        db.query(FinancialAccount.id)
        .filter(
            FinancialAccount.organization_id == unit.organization_id,
            FinancialAccount.business_unit_id == unit.id,
            FinancialAccount.deleted_at.is_(None),
            FinancialAccount.active.is_(True),
            FinancialAccount.current_balance != 0,
        )
        .first()
    )
    if with_balance is not None:
        raise ValueError("Primero traspasa el saldo de sus cajas.")


def update_business_unit(db: Session, unit: BusinessUnit, payload) -> BusinessUnit:
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        changes["name"] = changes["name"].strip()
        _assert_name_free(db, unit.organization_id, changes["name"], unit.id)
    if "code" in changes:
        changes["code"] = (changes["code"] or "").strip().upper() or derive_code(changes.get("name", unit.name))
        _assert_code_free(db, unit.organization_id, changes["code"], unit.id)
    if "aliases" in changes:
        changes["aliases"] = _clean_aliases(db, unit.organization_id, changes["aliases"] or [], unit.id)
    if changes.get("active") is False and unit.active:
        _assert_can_deactivate(db, unit)

    kind = changes.get("kind", unit.kind)
    active = changes.get("active", unit.active)
    if kind == "MATRIZ" and active and (kind != unit.kind or active != unit.active):
        _assert_single_matriz(db, unit.organization_id, unit.id)

    for field, value in changes.items():
        setattr(unit, field, value)
    db.commit()
    db.refresh(unit)
    return unit


def accounts_count_by_unit(db: Session, organization_id: str) -> dict[str, int]:
    rows = (
        db.query(FinancialAccount.business_unit_id, func.count(FinancialAccount.id))
        .filter(
            FinancialAccount.organization_id == organization_id,
            FinancialAccount.deleted_at.is_(None),
            FinancialAccount.business_unit_id.isnot(None),
        )
        .group_by(FinancialAccount.business_unit_id)
        .all()
    )
    return {unit_id: count for unit_id, count in rows}
