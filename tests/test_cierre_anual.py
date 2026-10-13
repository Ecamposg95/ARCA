"""Cierre de ejercicio: el resultado pasa a Resultados Acumulados y el año queda bajo candado."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.fiscal_year import FiscalYearLock
from app.services.accounting.engine import (
    YEAR_CLOSE_SOURCE,
    ClosedPeriodError,
    LineSpec,
    post_journal_entry,
)
from tests.helpers import auth_headers, register

TODAY = date.today()
LAST_YEAR = TODAY.year - 1


def _setup(client, email="contador@example.com"):
    """Empresa con 100,000 en caja (póliza de hoy) y las categorías que usan las pruebas."""
    body = register(client, email=email, initial_cash="100000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]

    def category(kind: str, name: str) -> str:
        rows = client.get(f"/api/categories?kind={kind}", headers=headers).json()
        return next(c["id"] for c in rows if c["name"] == name)

    return headers, body["organization"]["id"], account, category


def _income(client, headers, account, category, when, amount="5000"):
    """Venta cobrada sin IVA: 4100 recibe exactamente `amount`."""
    return client.post(
        "/api/income",
        headers=headers,
        json={
            "date": when.isoformat(),
            "description": "Venta",
            "amount": amount,
            "category_id": category("INCOME", "Ventas"),
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )


def _expense(client, headers, account, category, when, amount="2000"):
    """Renta pagada sin IVA: 5300 recibe exactamente `amount`."""
    return client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": when.isoformat(),
            "description": "Renta",
            "amount": amount,
            "category_id": category("EXPENSE", "Renta"),
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )


def _lock_year(db, organization_id, year):
    """Candado anual puesto a mano: esta parte prueba el motor antes de que exista close_year.

    commit (no flush): con la sesión de pruebas en modo SAVEPOINT, el rollback de
    una petición que falla desharía un flush pendiente."""
    lock = FiscalYearLock(organization_id=organization_id, year=year)
    db.add(lock)
    db.commit()
    return lock


def _simple_lines(amount="100"):
    return [LineSpec("5100", debit=Decimal(amount)), LineSpec("3100", credit=Decimal(amount))]


def test_year_close_source_is_a_fixed_constant():
    assert YEAR_CLOSE_SOURCE == "year_close"


def test_a_locked_year_rejects_entries(client, db):
    _headers, org_id, _account, _category = _setup(client)
    _lock_year(db, org_id, LAST_YEAR)

    with pytest.raises(ClosedPeriodError, match=f"El ejercicio {LAST_YEAR} está cerrado"):
        post_journal_entry(db, org_id, date(LAST_YEAR, 6, 15), "Gasto", _simple_lines())


def test_a_reopened_year_accepts_entries_again(client, db):
    from datetime import datetime, timezone

    _headers, org_id, _account, _category = _setup(client)
    lock = _lock_year(db, org_id, LAST_YEAR)
    lock.reopened_at = datetime.now(timezone.utc)
    lock.reopen_reason = "Faltó una factura"
    db.commit()

    entry = post_journal_entry(db, org_id, date(LAST_YEAR, 6, 15), "Gasto", _simple_lines())
    assert entry.folio.startswith(f"Dr-{LAST_YEAR}-06-")


def test_bypass_skips_both_the_year_and_the_month_lock(client, db):
    from app.models.period import PeriodLock

    _headers, org_id, _account, _category = _setup(client)
    _lock_year(db, org_id, LAST_YEAR)
    db.add(PeriodLock(organization_id=org_id, year=LAST_YEAR, month=12))
    db.commit()

    with pytest.raises(ClosedPeriodError):
        post_journal_entry(db, org_id, date(LAST_YEAR, 12, 31), "Cierre", _simple_lines())
    entry = post_journal_entry(
        db, org_id, date(LAST_YEAR, 12, 31), "Cierre", _simple_lines(), bypass_period_lock=True
    )
    assert entry.date == date(LAST_YEAR, 12, 31)


def test_a_locked_year_rejects_operations_through_the_api(client, db):
    headers, org_id, account, category = _setup(client)
    _lock_year(db, org_id, LAST_YEAR)

    response = _income(client, headers, account, category, date(LAST_YEAR, 6, 15))
    assert response.status_code == 400
    assert "ejercicio" in response.json()["detail"]
    # El año en curso no tiene candado.
    assert _income(client, headers, account, category, TODAY).status_code == 201


def test_the_year_lock_belongs_to_one_company(client, db):
    _headers, org_a, _account, _category = _setup(client)
    _lock_year(db, org_a, LAST_YEAR)

    headers_b, _org_b, account_b, category_b = _setup(client, email="otra@example.com")
    assert _income(client, headers_b, account_b, category_b, date(LAST_YEAR, 6, 15)).status_code == 201
