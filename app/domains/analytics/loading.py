"""Orquesta los cargadores: resuelve etiquetas a unidades y contribuyentes de
la empresa y persiste con `replace_points`. Lo comparten el script y el
endpoint de carga.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy.orm import Session

from app.domains.analytics.loaders.control_general import load_control_general
from app.domains.analytics.loaders.efectivo import load_efectivo
from app.domains.analytics.loaders.reconstruccion import load_reconstruccion
from app.domains.analytics.loaders.toronja import SHEET as TORONJA_SHEET
from app.domains.analytics.loaders.toronja import load_toronja
from app.domains.analytics.points import Point, ResolvedPoint, replace_points, resolve
from app.models.business_unit import BusinessUnit
from app.models.fiscal_entity import FiscalEntity
from app.services.dimensions import normalize_alias

Loader = Callable[[bytes, str], list[Point]]

# familia → (cargador, nombre de hoja/sección para el `source`)
LOADERS: dict[str, tuple[Loader, str]] = {
    "toronja": (load_toronja, TORONJA_SHEET),
    "control_general": (load_control_general, "PROY+RESUTADOS+PRESTAMOS+INVERSIONES"),
    "reconstruccion": (load_reconstruccion, "03+04+17+18"),
    "efectivo": (load_efectivo, "meses"),
}


@dataclass
class LoadReport:
    loads: list[dict] = field(default_factory=list)
    unresolved_units: list[str] = field(default_factory=list)
    unresolved_entities: list[str] = field(default_factory=list)
    dry_run: bool = False


def _unit_index(db: Session, organization_id: str) -> dict[str, str]:
    """Nombre, código y alias normalizados → id. Todas las unidades, también
    las inactivas (una sucursal cerrada sigue teniendo historia)."""
    index: dict[str, str] = {}
    units = db.query(BusinessUnit).filter(BusinessUnit.organization_id == organization_id).all()
    for unit in units:
        for label in [unit.name, unit.code, *(unit.aliases or [])]:
            if label:
                index.setdefault(normalize_alias(str(label)), unit.id)
    return index


def _entity_index(db: Session, organization_id: str) -> dict[str, str]:
    index: dict[str, str] = {}
    for entity in db.query(FiscalEntity).filter(FiscalEntity.organization_id == organization_id).all():
        for label in (entity.name, entity.tax_id):
            if label:
                index.setdefault(normalize_alias(str(label)), entity.id)
    return index


def load_files(
    db: Session,
    organization_id: str,
    files: dict[str, tuple[str, bytes]],
    user_id: str | None,
    dry_run: bool = False,
) -> LoadReport:
    """`files`: familia → (nombre de archivo, bytes). Cada familia se carga y
    reemplaza por separado; en `dry_run` todo se revierte al final."""
    report = LoadReport(dry_run=dry_run)
    units = _unit_index(db, organization_id)
    entities = _entity_index(db, organization_id)
    unresolved_units: dict[str, None] = {}
    unresolved_entities: dict[str, None] = {}

    for family, (filename, content) in files.items():
        if family not in LOADERS:
            raise ValueError(f"fuente desconocida: {family}")
        loader, sheet = LOADERS[family]
        points = loader(content, filename)
        resolved: list[ResolvedPoint] = []
        for point in points:
            unit_id = entity_id = None
            if point.unit_label:
                unit_id = units.get(normalize_alias(point.unit_label))
                if unit_id is None:
                    unresolved_units.setdefault(point.unit_label)
            if point.entity_label:
                entity_id = entities.get(normalize_alias(point.entity_label))
                if entity_id is None:
                    unresolved_entities.setdefault(point.entity_label)
            resolved.append(resolve(point, business_unit_id=unit_id, fiscal_entity_id=entity_id))
        load = replace_points(
            db,
            organization_id,
            source_family=family,
            source=f"{family}:{filename}#{sheet}",
            points=resolved,
            user_id=user_id,
            commit=not dry_run,
        )
        report.loads.append(
            {
                "family": family,
                "source": load.source,
                "period_from": load.period_from,
                "period_to": load.period_to,
                "rows": load.rows,
            }
        )

    report.unresolved_units = list(unresolved_units)
    report.unresolved_entities = list(unresolved_entities)
    if dry_run:
        db.rollback()
    return report


