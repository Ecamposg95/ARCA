"""Puntos del histórico y reemplazo por rango.

Un cargador devuelve `Point`s puros (etiquetas, sin ids). `loading.py` los
resuelve a `ResolvedPoint` (ids de unidad y contribuyente) y `replace_points`
los persiste reemplazando, en una sola transacción, lo que la misma familia
de archivo ya había cargado para esos datasets en ese rango.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, delete, or_
from sqlalchemy.orm import Session

from app.models.historical import DATASETS, GRAINS, SOURCE_FAMILIES, HistoricalLoad, HistoricalPoint


class HistoricalFormatError(ValueError):
    """El archivo no tiene el formato que el cargador espera (mensaje en español)."""


@dataclass(frozen=True)
class Point:
    dataset: str
    metric: str
    period_start: date
    period_grain: str
    value: Decimal
    unit_label: str | None = None
    entity_label: str | None = None
    payment_method: str | None = None
    account_code: str | None = None
    account_label: str | None = None

    def __post_init__(self) -> None:
        if self.dataset not in DATASETS:
            raise ValueError(f"dataset desconocido: {self.dataset}")
        if self.period_grain not in GRAINS:
            raise ValueError(f"granularidad desconocida: {self.period_grain}")


@dataclass(frozen=True)
class ResolvedPoint(Point):
    business_unit_id: str | None = None
    fiscal_entity_id: str | None = None


def resolve(point: Point, *, business_unit_id: str | None, fiscal_entity_id: str | None) -> ResolvedPoint:
    return ResolvedPoint(
        **{field: getattr(point, field) for field in Point.__dataclass_fields__},
        business_unit_id=business_unit_id,
        fiscal_entity_id=fiscal_entity_id,
    )


def replace_points(
    db: Session,
    organization_id: str,
    *,
    source_family: str,
    source: str,
    points: list[ResolvedPoint],
    user_id: str | None,
    notes: str | None = None,
) -> HistoricalLoad:
    """Borra los puntos de la misma familia en el rango (por dataset) que traen
    `points`, inserta los nuevos y registra la carga. Un solo commit.

    El borrado es real: el histórico es una capa de análisis reemplazable, no
    un registro contable.
    """
    if source_family not in SOURCE_FAMILIES:
        raise ValueError(f"familia de fuente desconocida: {source_family}")
    if not points:
        raise HistoricalFormatError("El archivo no trae datos que cargar")

    ranges: dict[str, tuple[date, date]] = {}
    for point in points:
        lo, hi = ranges.get(point.dataset, (point.period_start, point.period_start))
        ranges[point.dataset] = (min(lo, point.period_start), max(hi, point.period_start))

    db.execute(
        delete(HistoricalPoint).where(
            HistoricalPoint.organization_id == organization_id,
            HistoricalPoint.source.like(f"{source_family}:%"),
            or_(
                *[
                    and_(
                        HistoricalPoint.dataset == dataset,
                        HistoricalPoint.period_start >= lo,
                        HistoricalPoint.period_start <= hi,
                    )
                    for dataset, (lo, hi) in ranges.items()
                ]
            ),
        )
    )

    load = HistoricalLoad(
        organization_id=organization_id,
        source=source,
        period_from=min(lo for lo, _ in ranges.values()),
        period_to=max(hi for _, hi in ranges.values()),
        rows=len(points),
        loaded_by=user_id,
        notes=notes,
    )
    db.add(load)
    db.flush()
    db.bulk_save_objects(
        [
            HistoricalPoint(
                organization_id=organization_id,
                load_id=load.id,
                dataset=point.dataset,
                metric=point.metric,
                period_start=point.period_start,
                period_grain=point.period_grain,
                business_unit_id=point.business_unit_id,
                unit_label=point.unit_label,
                fiscal_entity_id=point.fiscal_entity_id,
                payment_method=point.payment_method,
                account_code=point.account_code,
                account_label=point.account_label,
                value=point.value,
                source=source,
            )
            for point in points
        ]
    )
    db.commit()
    return load
