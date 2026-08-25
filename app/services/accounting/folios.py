"""Folios de póliza (convención mexicana): Ig-2026-08-0001.

Serie independiente por organización, tipo de póliza y mes; reinicia cada mes.
El número se toma bajo lock de fila del contador: dos operaciones simultáneas
nunca reciben el mismo folio.
"""

from __future__ import annotations

from datetime import date as date_type

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.accounting import ENTRY_KINDS, FolioCounter

PREFIXES = {"INGRESO": "Ig", "EGRESO": "Eg", "DIARIO": "Dr"}

KIND_LABELS = {"INGRESO": "Ingreso", "EGRESO": "Egreso", "DIARIO": "Diario"}


def period_of(date: date_type) -> str:
    return f"{date.year:04d}-{date.month:02d}"


def _get_counter(db: Session, organization_id: str, kind: str, period: str) -> FolioCounter:
    counter = (
        db.query(FolioCounter)
        .filter(
            FolioCounter.organization_id == organization_id,
            FolioCounter.kind == kind,
            FolioCounter.period == period,
        )
        .with_for_update()
        .first()
    )
    if counter is not None:
        return counter

    # Primera póliza del mes: dos transacciones podrían insertar a la vez, así que
    # el conflicto se resuelve releyendo con lock en lugar de fallar.
    try:
        with db.begin_nested():
            counter = FolioCounter(
                organization_id=organization_id,
                kind=kind,
                period=period,
                next_number=1,
            )
            db.add(counter)
            db.flush()
        return counter
    except IntegrityError:
        return (
            db.query(FolioCounter)
            .filter(
                FolioCounter.organization_id == organization_id,
                FolioCounter.kind == kind,
                FolioCounter.period == period,
            )
            .with_for_update()
            .one()
        )


def next_folio(db: Session, organization_id: str, kind: str, date: date_type) -> str:
    if kind not in ENTRY_KINDS:
        raise ValueError(f"Tipo de póliza inválido: {kind}")
    period = period_of(date)
    counter = _get_counter(db, organization_id, kind, period)
    number = counter.next_number
    counter.next_number = number + 1
    db.flush()
    return f"{PREFIXES[kind]}-{period}-{number:04d}"
