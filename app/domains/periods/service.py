"""Cierre de periodo: proteger lo que ya se declaró.

Cerrar un mes no congela la verdad: obliga a reabrirlo a propósito para
cambiarla, y deja constancia de quién lo hizo y por qué. Sin eso, una corrección
de agosto puede alterar en silencio una declaración de marzo.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date as date_type
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.accounting import JournalEntry, JournalEntryLine
from app.models.period import PeriodLock


def _month_bounds(year: int, month: int) -> tuple[date_type, date_type]:
    return date_type(year, month, 1), date_type(year, month, monthrange(year, month)[1])


def is_closed(db: Session, organization_id: str, year: int, month: int) -> bool:
    return (
        db.query(PeriodLock)
        .filter(
            PeriodLock.organization_id == organization_id,
            PeriodLock.year == year,
            PeriodLock.month == month,
            PeriodLock.reopened_at.is_(None),
        )
        .first()
        is not None
    )


def close_period(
    db: Session,
    organization_id: str,
    year: int,
    month: int,
    user_id: str | None = None,
    notes: str | None = None,
) -> PeriodLock:
    start, end = _month_bounds(year, month)
    if end > date_type.today():
        raise ValueError("No puedes cerrar un mes que todavía no termina.")
    if is_closed(db, organization_id, year, month):
        raise ValueError("Ese mes ya está cerrado.")

    lock = PeriodLock(
        organization_id=organization_id,
        year=year,
        month=month,
        closed_by=user_id,
        notes=notes,
    )
    db.add(lock)
    db.commit()
    db.refresh(lock)
    return lock


def reopen_period(
    db: Session,
    organization_id: str,
    year: int,
    month: int,
    reason: str,
    user_id: str | None = None,
) -> PeriodLock:
    lock = (
        db.query(PeriodLock)
        .filter(
            PeriodLock.organization_id == organization_id,
            PeriodLock.year == year,
            PeriodLock.month == month,
            PeriodLock.reopened_at.is_(None),
        )
        .first()
    )
    if lock is None:
        raise ValueError("Ese mes no está cerrado.")

    lock.reopened_at = datetime.now(timezone.utc)
    lock.reopened_by = user_id
    lock.reopen_reason = reason
    db.commit()
    db.refresh(lock)
    return lock


def list_periods(db: Session, organization_id: str, months: int = 12) -> list[dict]:
    """Los últimos meses con su estado y lo que se movió en cada uno."""
    today = date_type.today()
    rows: list[dict] = []

    for offset in range(months):
        index = today.year * 12 + (today.month - 1) - offset
        year, month = divmod(index, 12)
        month += 1
        start, end = _month_bounds(year, month)

        totals = (
            db.query(
                func.count(func.distinct(JournalEntry.id)),
                func.coalesce(func.sum(JournalEntryLine.debit), 0),
            )
            .join(JournalEntryLine, JournalEntryLine.journal_entry_id == JournalEntry.id)
            .filter(
                JournalEntry.organization_id == organization_id,
                JournalEntry.status == "POSTED",
                JournalEntry.date >= start,
                JournalEntry.date <= end,
            )
            .one()
        )

        rows.append(
            {
                "year": year,
                "month": month,
                "label": start.strftime("%Y-%m"),
                "entries": totals[0],
                "movement": Decimal(totals[1] or 0),
                "closed": is_closed(db, organization_id, year, month),
                "can_close": end <= today,
            }
        )
    return rows
