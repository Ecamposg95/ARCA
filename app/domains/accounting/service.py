"""Pólizas del mes listas para exportar. Sólo lectura."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.accounting import Account, JournalEntry, JournalEntryLine
from app.models.organization import Organization
from app.services.accounting.coa import CODE_RETAINED_EARNINGS
from app.services.accounting.sat import (
    BalanceRow,
    CatalogRow,
    SatError,
    is_valid_rfc,
    nature,
    normalize_rfc,
)
from app.services.accounting.contpaqi import Movement, Voucher, folio_consecutive


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
        .all()
    )
    if not entries:
        return [], []
    # Por fecha, tipo y consecutivo NUMÉRICO: ordenar por el texto del folio
    # pondría la póliza 10000 antes que la 9999.
    entries.sort(key=lambda e: (e.date, e.kind, folio_consecutive(e.folio), e.folio))

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


# --- Contabilidad electrónica (Anexo 24) ---

RESULT_ACCOUNT_TYPES = ("REVENUE", "EXPENSE")


def _active_accounts(db: Session, organization_id: str) -> list[Account]:
    return (
        db.query(Account)
        .filter(Account.organization_id == organization_id, Account.active.is_(True))
        .order_by(Account.code)
        .all()
    )


def sat_catalog(db: Session, organization_id: str) -> list[CatalogRow]:
    """Todas las cuentas activas: el SAT quiere el catálogo completo, padres incluidos."""
    accounts = _active_accounts(db, organization_id)
    by_id = {account.id: account for account in accounts}
    rows = []
    for account in accounts:
        parent = by_id.get(account.parent_id) if account.parent_id else None
        rows.append(
            CatalogRow(
                code=account.code,
                name=account.name,
                sat_code=account.sat_code or "",
                parent_code=parent.code if parent else None,
                level=2 if parent else 1,
                nature=nature(account.type, account.code),
            )
        )
    return rows


def _line_sums(
    db: Session, organization_id: str, start: date | None, end: date | None
) -> dict[str, tuple[Decimal, Decimal]]:
    """(cargos, abonos) por cuenta en un rango de fechas, sólo pólizas contabilizadas."""
    query = (
        db.query(
            JournalEntryLine.account_id,
            func.coalesce(func.sum(JournalEntryLine.debit), 0),
            func.coalesce(func.sum(JournalEntryLine.credit), 0),
        )
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .filter(JournalEntry.organization_id == organization_id, JournalEntry.status == "POSTED")
    )
    if start is not None:
        query = query.filter(JournalEntry.date >= start)
    if end is not None:
        query = query.filter(JournalEntry.date <= end)
    return {
        account_id: (Decimal(debit or 0), Decimal(credit or 0))
        for account_id, debit, credit in query.group_by(JournalEntryLine.account_id).all()
    }


def sat_balance(db: Session, organization_id: str, year: int, month: int) -> list[BalanceRow]:
    """Saldo inicial, movimientos del mes y saldo final por cuenta, en la
    naturaleza de cada una. Los padres suman los cargos y abonos de sus hijas y
    aplican SU naturaleza: así un contra-activo resta en el total de activo."""
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    year_start = date(year, 1, 1)
    # ARCA no tiene cierre anual, así que el XML lo hace virtual: ingresos y
    # gastos sólo arrastran saldo desde el 1 de enero, y el resultado neto de
    # los años anteriores abre en Resultados Acumulados. Sin esto, enero
    # mostraría las ventas de todos los años como saldo inicial.
    prior_years = _line_sums(db, organization_id, None, year_start - timedelta(days=1))
    this_year = _line_sums(db, organization_id, year_start, start - timedelta(days=1))
    during = _line_sums(db, organization_id, start, end)

    accounts = _active_accounts(db, organization_id)
    zero = (Decimal("0"), Decimal("0"))
    raw: dict[str, list[Decimal]] = {}  # id → [deb_before, cred_before, deb_month, cred_month]
    prior_result = Decimal("0")  # acreedor positivo: utilidad
    for account in accounts:
        dp, cp = prior_years.get(account.id, zero)
        dy, cy = this_year.get(account.id, zero)
        dm, cm = during.get(account.id, zero)
        if account.type in RESULT_ACCOUNT_TYPES:
            raw[account.id] = [dy, cy, dm, cm]
            if account.parent_id:  # sólo hojas: los padres se agregan abajo
                prior_result += cp - dp
        else:
            raw[account.id] = [dp + dy, cp + cy, dm, cm]
    retained = next((a for a in accounts if a.code == CODE_RETAINED_EARNINGS), None)
    if retained is not None and prior_result:
        if prior_result > 0:
            raw[retained.id][1] += prior_result
        else:
            raw[retained.id][0] += -prior_result
    for account in accounts:
        if account.parent_id in raw:
            for i in range(4):
                raw[account.parent_id][i] += raw[account.id][i]

    rows: list[BalanceRow] = []
    leaf_debe = leaf_haber = Decimal("0")
    for account in accounts:
        deb_before, cred_before, debe, haber = raw[account.id]
        if nature(account.type, account.code) == "D":
            saldo_ini = deb_before - cred_before
            saldo_fin = saldo_ini + debe - haber
        else:
            saldo_ini = cred_before - deb_before
            saldo_fin = saldo_ini - debe + haber
        if not any((saldo_ini, debe, haber, saldo_fin)):
            continue
        if account.parent_id:
            leaf_debe += debe
            leaf_haber += haber
        rows.append(BalanceRow(account.code, saldo_ini, debe, haber, saldo_fin))

    if leaf_debe != leaf_haber:
        raise SatError(
            f"La balanza de {year}-{month:02d} no cuadra: cargos {leaf_debe:.2f}, abonos {leaf_haber:.2f}."
        )
    return rows


def sat_requirements(db: Session, organization: Organization, year: int, month: int) -> dict:
    """Qué falta para poder generar los XML del mes."""
    accounts = _active_accounts(db, organization.id)
    missing = [
        {"id": a.id, "code": a.code, "name": a.name} for a in accounts if not a.sat_code
    ]
    rfc = normalize_rfc(organization.tax_id)
    rfc_ok = is_valid_rfc(rfc)
    return {
        "year": year,
        "month": month,
        "rfc": rfc or None,
        "rfc_ok": rfc_ok,
        "accounts": len(accounts),
        "missing_accounts": missing,
        "ready": rfc_ok and not missing,
    }
