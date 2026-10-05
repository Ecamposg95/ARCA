"""Pólizas del mes listas para exportar. Sólo lectura."""

from __future__ import annotations

from calendar import monthrange
from datetime import date

from sqlalchemy.orm import Session

from app.models.accounting import Account, JournalEntry, JournalEntryLine
from app.services.accounting.contpaqi import Movement, Voucher


def month_vouchers(
    db: Session, organization_id: str, year: int, month: int
) -> tuple[list[Voucher], list[dict]]:
    """Las pólizas contabilizadas del mes, en el orden del libro, y las cuentas
    usadas ese mes que todavía no tienen equivalente en CONTPAQi."""
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])

    entries = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.organization_id == organization_id,
            JournalEntry.status == "POSTED",
            JournalEntry.date >= start,
            JournalEntry.date <= end,
        )
        .order_by(JournalEntry.date, JournalEntry.folio)
        .all()
    )
    if not entries:
        return [], []

    rows = (
        db.query(JournalEntryLine, Account)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .join(Account, Account.id == JournalEntryLine.account_id)
        .filter(
            JournalEntry.organization_id == organization_id,
            JournalEntry.status == "POSTED",
            JournalEntry.date >= start,
            JournalEntry.date <= end,
        )
        .all()
    )
    lines_by_entry: dict[str, list[tuple[JournalEntryLine, Account]]] = {}
    unmapped: dict[str, dict] = {}
    for line, account in rows:
        lines_by_entry.setdefault(line.journal_entry_id, []).append((line, account))
        if not account.contpaqi_code:
            unmapped[account.id] = {"id": account.id, "code": account.code, "name": account.name}

    vouchers = []
    for entry in entries:
        # Las líneas no guardan orden propio: cargos primero y luego por cuenta,
        # como se lee una póliza en papel.
        pairs = sorted(
            lines_by_entry.get(entry.id, []),
            key=lambda pair: (0 if pair[0].debit > 0 else 1, pair[1].code),
        )
        vouchers.append(
            Voucher(
                folio=entry.folio,
                kind=entry.kind,
                date=entry.date,
                concept=entry.description,
                movements=tuple(
                    Movement(
                        account=account.contpaqi_code or account.code,
                        debit=line.debit,
                        credit=line.credit,
                        concept=line.description or entry.description,
                    )
                    for line, account in pairs
                ),
            )
        )
    return vouchers, sorted(unmapped.values(), key=lambda item: item["code"])
