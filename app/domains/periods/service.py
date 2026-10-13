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

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.models.accounting import Account, JournalEntry, JournalEntryLine
from app.models.fiscal_year import FiscalYearLock
from app.models.period import PeriodLock
from app.services.accounting.engine import TWO_PLACES, account_type_balance, lock_organization
from app.services.accounting.rules import reversal_of, year_close_entry


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

    # Un mes reabierto conserva su renglón (la llave única es empresa+año+mes):
    # volver a cerrarlo lo reutiliza, y la reapertura queda escrita en las notas
    # para no perder quién movió un mes ya declarado ni por qué.
    lock = (
        db.query(PeriodLock)
        .filter(
            PeriodLock.organization_id == organization_id,
            PeriodLock.year == year,
            PeriodLock.month == month,
        )
        .first()
    )
    if lock is None:
        lock = PeriodLock(organization_id=organization_id, year=year, month=month, notes=notes)
        db.add(lock)
    else:
        trace = f"Reabierto el {lock.reopened_at:%Y-%m-%d}: {lock.reopen_reason}"
        lock.notes = "\n".join(part for part in (lock.notes, trace, notes) if part)[-1000:]
        lock.reopened_at = None
        lock.reopened_by = None
        lock.reopen_reason = None
    lock.closed_by = user_id
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


# --- Ejercicios (C-2) ---


def _year_lock(db: Session, organization_id: str, year: int, live: bool = False) -> FiscalYearLock | None:
    query = db.query(FiscalYearLock).filter(
        FiscalYearLock.organization_id == organization_id,
        FiscalYearLock.year == year,
    )
    if live:
        query = query.filter(FiscalYearLock.reopened_at.is_(None))
    return query.first()


def is_year_closed(db: Session, organization_id: str, year: int) -> bool:
    return _year_lock(db, organization_id, year, live=True) is not None


def _years_with_results(db: Session, organization_id: str) -> set[int]:
    """Años con al menos una línea contabilizada en ingresos o gastos."""
    year_of = extract("year", JournalEntry.date)
    rows = (
        db.query(year_of)
        .join(JournalEntryLine, JournalEntryLine.journal_entry_id == JournalEntry.id)
        .join(Account, Account.id == JournalEntryLine.account_id)
        .filter(
            JournalEntry.organization_id == organization_id,
            JournalEntry.status == "POSTED",
            Account.type.in_(("REVENUE", "EXPENSE")),
        )
        .distinct()
        .all()
    )
    return {int(year) for (year,) in rows}


def _closed_years(db: Session, organization_id: str) -> set[int]:
    return {
        year
        for (year,) in db.query(FiscalYearLock.year).filter(
            FiscalYearLock.organization_id == organization_id,
            FiscalYearLock.reopened_at.is_(None),
        )
    }


def _pending_before(results: set[int], closed: set[int], year: int) -> int | None:
    """El año anterior más antiguo con resultados que sigue abierto: hay que cerrarlo primero."""
    pending = [other for other in results if other < year and other not in closed]
    return min(pending) if pending else None


def close_year(
    db: Session,
    organization_id: str,
    year: int,
    user_id: str | None = None,
    notes: str | None = None,
) -> FiscalYearLock:
    """Traspasa el resultado del año a 3200 y pone el candado anual. Hace commit."""
    # Antes de revisar el estado: dos cierres simultáneos asentarían dos pólizas
    # de cierre que ninguna pantalla puede deshacer.
    lock_organization(db, organization_id)
    if date_type(year, 12, 31) >= date_type.today():
        raise ValueError(f"El ejercicio {year} todavía no termina.")
    if is_year_closed(db, organization_id, year):
        raise ValueError(f"El ejercicio {year} ya está cerrado.")
    pending = _pending_before(_years_with_results(db, organization_id), _closed_years(db, organization_id), year)
    if pending is not None:
        raise ValueError(f"Primero cierra el ejercicio {pending}.")

    entry = year_close_entry(db, organization_id, year, created_by=user_id)

    # Un año reabierto conserva su renglón (la llave única es empresa+año): volver
    # a cerrarlo lo reutiliza y la reapertura queda escrita en las notas.
    lock = _year_lock(db, organization_id, year)
    if lock is None:
        lock = FiscalYearLock(organization_id=organization_id, year=year, notes=notes)
        db.add(lock)
    else:
        trace = f"Reabierto el {lock.reopened_at:%Y-%m-%d}: {lock.reopen_reason}"
        lock.notes = "\n".join(part for part in (lock.notes, trace, notes) if part)[-1000:]
        lock.reopened_at = None
        lock.reopened_by = None
        lock.reopen_reason = None
    lock.closed_by = user_id
    lock.closing_entry_id = entry.id if entry is not None else None
    db.commit()
    db.refresh(lock)
    return lock


def reopen_year(
    db: Session,
    organization_id: str,
    year: int,
    reason: str,
    user_id: str | None = None,
) -> FiscalYearLock:
    """Quita el candado anual y revierte la póliza de cierre al 31 de diciembre. Hace commit."""
    # Mismo candado que el cierre: dos reaperturas simultáneas duplicarían el reverso.
    lock_organization(db, organization_id)
    lock = _year_lock(db, organization_id, year, live=True)
    if lock is None:
        raise ValueError(f"El ejercicio {year} no está cerrado.")
    later = max((other for other in _closed_years(db, organization_id) if other > year), default=None)
    if later is not None:
        raise ValueError(f"Primero reabre el ejercicio {later}.")

    lock.reopened_at = datetime.now(timezone.utc)
    lock.reopened_by = user_id
    lock.reopen_reason = reason
    if lock.closing_entry_id:
        closing = (
            db.query(JournalEntry)
            .filter(JournalEntry.id == lock.closing_entry_id, JournalEntry.organization_id == organization_id)
            .one()
        )
        reversal_of(
            db,
            organization_id,
            closing,
            description=f"Reapertura del ejercicio {year}: {reason}"[:500],
            date=date_type(year, 12, 31),
            created_by=user_id,
            bypass_period_lock=True,
        )
    db.commit()
    db.refresh(lock)
    return lock


def entry_folio(db: Session, organization_id: str, entry_id: str | None) -> str | None:
    """Folio de una póliza de la empresa, o None si no hay póliza."""
    if not entry_id:
        return None
    return (
        db.query(JournalEntry.folio)
        .filter(JournalEntry.id == entry_id, JournalEntry.organization_id == organization_id)
        .scalar()
    )


def list_years(db: Session, organization_id: str) -> list[dict]:
    """Del año de la póliza más antigua al año en curso, el más reciente primero."""
    today = date_type.today()
    oldest = (
        db.query(func.min(JournalEntry.date))
        .filter(JournalEntry.organization_id == organization_id, JournalEntry.status == "POSTED")
        .scalar()
    )
    first_year = oldest.year if oldest is not None else today.year
    locks = {
        lock.year: lock
        for lock in db.query(FiscalYearLock).filter(FiscalYearLock.organization_id == organization_id).all()
    }
    closed = {year for year, lock in locks.items() if lock.reopened_at is None}
    results = _years_with_results(db, organization_id)
    folios = dict(
        db.query(JournalEntry.id, JournalEntry.folio)
        .filter(
            JournalEntry.organization_id == organization_id,
            JournalEntry.id.in_([lock.closing_entry_id for lock in locks.values() if lock.closing_entry_id]),
        )
        .all()
    )

    rows: list[dict] = []
    for year in range(today.year, first_year - 1, -1):
        start, end = date_type(year, 1, 1), date_type(year, 12, 31)
        entries = (
            db.query(func.count(JournalEntry.id))
            .filter(
                JournalEntry.organization_id == organization_id,
                JournalEntry.status == "POSTED",
                JournalEntry.date >= start,
                JournalEntry.date <= end,
            )
            .scalar()
        )
        # Sin include_closing: el cierre traspasa resultados, no es venta ni gasto.
        revenue = account_type_balance(db, organization_id, "REVENUE", start=start, end=end)
        expenses = account_type_balance(db, organization_id, "EXPENSE", start=start, end=end)
        lock = locks.get(year)
        is_closed_year = year in closed
        blocked_by = _pending_before(results, closed, year)
        closing_entry_id = lock.closing_entry_id if lock is not None and is_closed_year else None
        rows.append(
            {
                "year": year,
                "entries": entries or 0,
                "revenue": revenue.quantize(TWO_PLACES),
                "expenses": expenses.quantize(TWO_PLACES),
                "result": (revenue - expenses).quantize(TWO_PLACES),
                "closed": is_closed_year,
                "can_close": end < today and not is_closed_year and blocked_by is None,
                "blocked_by": blocked_by if not is_closed_year else None,
                "closing_entry_id": closing_entry_id,
                "closing_folio": folios.get(closing_entry_id) if closing_entry_id else None,
                "reopened_at": lock.reopened_at if lock is not None and not is_closed_year else None,
            }
        )
    return rows
