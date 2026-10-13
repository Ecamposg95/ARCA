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


# --- Reportes: el cierre no es un gasto (Task 3) ---


def _fake_close(db, organization_id, when, amount="5000"):
    """Póliza con origen de cierre anual (4100 → 3200), sin pasar por close_year."""
    entry = post_journal_entry(
        db,
        organization_id,
        date=when,
        description="Cierre simulado",
        lines=[LineSpec("4100", debit=Decimal(amount)), LineSpec("3200", credit=Decimal(amount))],
        source_type=YEAR_CLOSE_SOURCE,
        source_id=f"year_close:{when.year}",
        kind="DIARIO",
    )
    db.commit()
    return entry


def test_profit_and_loss_and_dashboard_ignore_the_closing_entry(client, db):
    headers, org_id, account, category = _setup(client)
    assert _income(client, headers, account, category, TODAY).status_code == 201
    _fake_close(db, org_id, TODAY)

    month = {"start": TODAY.replace(day=1).isoformat(), "end": TODAY.isoformat()}
    report = client.get("/api/reports/profit-loss", headers=headers, params=month).json()
    assert Decimal(str(report["total_revenue"])) == Decimal("5000")
    summary = client.get("/api/dashboard/summary", headers=headers).json()
    assert Decimal(str(summary["monthly_revenue"])) == Decimal("5000")


def test_balance_sheet_and_trial_balance_include_the_closing_entry(client, db):
    headers, org_id, account, category = _setup(client)
    assert _income(client, headers, account, category, TODAY).status_code == 201
    _fake_close(db, org_id, TODAY)

    sheet = client.get("/api/reports/balance-sheet", headers=headers).json()
    assert sheet["balanced"] is True
    equity = {row["code"]: Decimal(str(row["amount"])) for row in sheet["equity"]}
    assert "3999" not in equity
    assert equity["3200"] == Decimal("5000")
    trial = {row["code"]: row for row in client.get("/api/accounting/trial-balance", headers=headers).json()["rows"]}
    assert Decimal(str(trial["4100"]["debit"])) == Decimal("5000")
    assert Decimal(str(trial["4100"]["balance"])) == Decimal("0")


def test_entries_without_source_type_still_count_in_profit_and_loss(client, db):
    """`source_type` NULL (asientos antiguos o cargados a mano) no debe caer con el filtro del cierre."""
    from app.models.accounting import Account, JournalEntry, JournalEntryLine

    headers, org_id, _account, _category = _setup(client)
    accounts = {a.code: a for a in db.query(Account).filter(Account.organization_id == org_id).all()}
    entry = JournalEntry(
        organization_id=org_id, folio="Dr-9999-99-0001", kind="DIARIO", date=TODAY,
        description="Asiento heredado", status="POSTED", source_type=None,
    )
    db.add(entry)
    db.flush()
    db.add(JournalEntryLine(journal_entry_id=entry.id, account_id=accounts["1300"].id, debit=Decimal("700"), credit=0))
    db.add(JournalEntryLine(journal_entry_id=entry.id, account_id=accounts["4200"].id, debit=0, credit=Decimal("700")))
    db.commit()

    month = {"start": TODAY.replace(day=1).isoformat(), "end": TODAY.isoformat()}
    report = client.get("/api/reports/profit-loss", headers=headers, params=month).json()
    assert Decimal(str(report["total_revenue"])) == Decimal("700")
    summary = client.get("/api/dashboard/summary", headers=headers).json()
    assert Decimal(str(summary["monthly_revenue"])) == Decimal("700")


def test_a_reversal_can_bypass_the_lock_only_when_asked(client, db):
    from app.models.period import PeriodLock
    from app.services.accounting.rules import reversal_of

    _headers, org_id, _account, _category = _setup(client)
    original = post_journal_entry(db, org_id, date(LAST_YEAR, 12, 31), "Gasto", _simple_lines())
    db.add(PeriodLock(organization_id=org_id, year=LAST_YEAR, month=12))
    db.commit()

    with pytest.raises(ClosedPeriodError):
        reversal_of(db, org_id, original, "Reverso", date(LAST_YEAR, 12, 31))
    reversal = reversal_of(db, org_id, original, "Reverso", date(LAST_YEAR, 12, 31), bypass_period_lock=True)
    assert reversal.reference == f"reversal:{original.id}"


# --- Cierre y reapertura del ejercicio (Task 4) ---


def _close(client, headers, year, notes=None):
    return client.post(f"/api/periods/years/{year}/close", headers=headers, json={"notes": notes})


def _reopen(client, headers, year, reason="Faltó una factura de diciembre"):
    return client.post(f"/api/periods/years/{year}/reopen", headers=headers, json={"reason": reason})


def _entry(client, headers, entry_id):
    response = client.get(f"/api/accounting/journal-entries/{entry_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _lines_by_code(client, headers, entry):
    accounts = {a["id"]: a["code"] for a in client.get("/api/accounting/accounts", headers=headers).json()}
    return {
        accounts[line["account_id"]]: (Decimal(line["debit"]), Decimal(line["credit"])) for line in entry["lines"]
    }


def _trial(client, headers, as_of):
    rows = client.get("/api/accounting/trial-balance", headers=headers, params={"as_of": as_of.isoformat()}).json()
    return {row["code"]: Decimal(str(row["balance"])) for row in rows["rows"]}


def _last_year_with_profit(client, email="contador@example.com"):
    """Venta de 5,000 en junio y renta de 2,000 en julio del año pasado: utilidad de 3,000."""
    headers, org_id, account, category = _setup(client, email=email)
    assert _income(client, headers, account, category, date(LAST_YEAR, 6, 15)).status_code == 201
    assert _expense(client, headers, account, category, date(LAST_YEAR, 7, 20)).status_code == 201
    return headers, org_id, account, category


def test_closing_moves_the_result_to_retained_earnings(client):
    headers, _org_id, _account, _category = _last_year_with_profit(client)

    response = _close(client, headers, LAST_YEAR)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["year"] == LAST_YEAR and body["closed"] is True
    assert body["closing_folio"].startswith(f"Dr-{LAST_YEAR}-12-")

    entry = _entry(client, headers, body["closing_entry_id"])
    assert entry["date"] == f"{LAST_YEAR}-12-31"
    assert entry["source_type"] == "year_close"
    assert entry["source_id"] == f"year_close:{LAST_YEAR}"
    assert entry["description"] == f"Cierre del ejercicio {LAST_YEAR}"
    assert _lines_by_code(client, headers, entry) == {
        "4100": (Decimal("5000.00"), Decimal("0.00")),
        "5300": (Decimal("0.00"), Decimal("2000.00")),
        "3200": (Decimal("0.00"), Decimal("3000.00")),
    }

    year = {"start": f"{LAST_YEAR}-01-01", "end": f"{LAST_YEAR}-12-31"}
    report = client.get("/api/reports/profit-loss", headers=headers, params=year).json()
    assert Decimal(str(report["total_revenue"])) == Decimal("5000")
    assert Decimal(str(report["net_profit"])) == Decimal("3000")

    sheet = client.get("/api/reports/balance-sheet", headers=headers, params={"as_of": f"{LAST_YEAR}-12-31"}).json()
    assert sheet["balanced"] is True
    equity = {row["code"]: Decimal(str(row["amount"])) for row in sheet["equity"]}
    assert "3999" not in equity
    assert equity["3200"] == Decimal("3000")

    trial = _trial(client, headers, date(LAST_YEAR, 12, 31))
    assert trial["4100"] == Decimal("0") and trial["5300"] == Decimal("0")
    assert trial["3200"] == Decimal("3000")


def test_a_loss_is_charged_to_retained_earnings(client):
    headers, _org_id, account, category = _setup(client)
    assert _income(client, headers, account, category, date(LAST_YEAR, 6, 15), amount="1000").status_code == 201
    assert _expense(client, headers, account, category, date(LAST_YEAR, 7, 20), amount="4000").status_code == 201

    body = _close(client, headers, LAST_YEAR).json()
    lines = _lines_by_code(client, headers, _entry(client, headers, body["closing_entry_id"]))
    assert lines["3200"] == (Decimal("3000.00"), Decimal("0.00"))


def test_a_year_without_results_is_locked_without_an_entry(client):
    headers, _org_id, account, category = _setup(client)

    response = _close(client, headers, LAST_YEAR)
    assert response.status_code == 200, response.text
    assert response.json()["closing_entry_id"] is None
    assert response.json()["closing_folio"] is None
    blocked = _income(client, headers, account, category, date(LAST_YEAR, 6, 15))
    assert blocked.status_code == 400
    assert "ejercicio" in blocked.json()["detail"]


def test_the_current_year_cannot_be_closed_nor_twice(client):
    headers, _org_id, _account, _category = _last_year_with_profit(client)

    current = _close(client, headers, TODAY.year)
    assert current.status_code == 400
    assert current.json()["detail"] == f"El ejercicio {TODAY.year} todavía no termina."

    assert _close(client, headers, LAST_YEAR).status_code == 200
    again = _close(client, headers, LAST_YEAR)
    assert again.status_code == 400
    assert again.json()["detail"] == f"El ejercicio {LAST_YEAR} ya está cerrado."


def test_years_close_in_order_and_reopen_in_reverse(client):
    headers, _org_id, account, category = _last_year_with_profit(client)
    older = LAST_YEAR - 1
    assert _income(client, headers, account, category, date(older, 3, 10), amount="800").status_code == 201

    blocked = _close(client, headers, LAST_YEAR)
    assert blocked.status_code == 400
    assert blocked.json()["detail"] == f"Primero cierra el ejercicio {older}."

    assert _close(client, headers, older).status_code == 200
    assert _close(client, headers, LAST_YEAR).status_code == 200

    early = _reopen(client, headers, older)
    assert early.status_code == 400
    assert early.json()["detail"] == f"Primero reabre el ejercicio {LAST_YEAR}."
    assert _reopen(client, headers, LAST_YEAR).status_code == 200
    assert _reopen(client, headers, older).status_code == 200


def test_reopening_requires_a_reason_and_reverses_the_closing_entry(client):
    headers, _org_id, account, category = _last_year_with_profit(client)
    closing_id = _close(client, headers, LAST_YEAR).json()["closing_entry_id"]

    blocked = _income(client, headers, account, category, date(LAST_YEAR, 8, 1))
    assert blocked.status_code == 400
    assert "ejercicio" in blocked.json()["detail"]

    assert client.post(f"/api/periods/years/{LAST_YEAR}/reopen", headers=headers, json={}).status_code == 422
    not_closed = _reopen(client, headers, LAST_YEAR - 1)
    assert not_closed.status_code == 400
    assert not_closed.json()["detail"] == f"El ejercicio {LAST_YEAR - 1} no está cerrado."

    response = _reopen(client, headers, LAST_YEAR)
    assert response.status_code == 200, response.text
    assert response.json() == {"year": LAST_YEAR, "closed": False}

    diary = client.get(
        "/api/accounting/journal-entries", headers=headers, params={"source_type": "year_close"}
    ).json()["items"]
    reversal = next(item for item in diary if item["reversal_of"] == closing_id)
    assert reversal["date"] == f"{LAST_YEAR}-12-31"
    assert reversal["description"] == f"Reapertura del ejercicio {LAST_YEAR}: Faltó una factura de diciembre"
    assert _trial(client, headers, date(LAST_YEAR, 12, 31))["4100"] == Decimal("5000")

    assert _income(client, headers, account, category, date(LAST_YEAR, 8, 1)).status_code == 201


def test_reclosing_reuses_the_lock_and_closes_the_full_year(client, db):
    headers, org_id, account, category = _last_year_with_profit(client)
    first = _close(client, headers, LAST_YEAR).json()["closing_entry_id"]
    _reopen(client, headers, LAST_YEAR, reason="Faltó la venta de agosto")
    assert _income(client, headers, account, category, date(LAST_YEAR, 8, 1), amount="1000").status_code == 201

    second = _close(client, headers, LAST_YEAR)
    assert second.status_code == 200, second.text
    assert second.json()["closing_entry_id"] != first

    locks = db.query(FiscalYearLock).filter(
        FiscalYearLock.organization_id == org_id, FiscalYearLock.year == LAST_YEAR
    ).all()
    assert len(locks) == 1
    assert locks[0].reopened_at is None
    assert "Faltó la venta de agosto" in locks[0].notes

    # Cierre, reverso y cierre nuevo: resultados en cero y 3200 con la utilidad completa.
    trial = _trial(client, headers, date(LAST_YEAR, 12, 31))
    assert trial["4100"] == Decimal("0") and trial["5300"] == Decimal("0")
    assert trial["3200"] == Decimal("4000")
    lines = _lines_by_code(client, headers, _entry(client, headers, second.json()["closing_entry_id"]))
    assert lines["4100"] == (Decimal("6000.00"), Decimal("0.00"))


def test_a_december_closed_by_month_does_not_block_the_year(client):
    headers, _org_id, _account, _category = _last_year_with_profit(client)
    assert (
        client.post("/api/periods/close", headers=headers, json={"year": LAST_YEAR, "month": 12}).status_code
        == 200
    )

    closed = _close(client, headers, LAST_YEAR)
    assert closed.status_code == 200, closed.text
    assert closed.json()["closing_entry_id"] is not None
    assert _reopen(client, headers, LAST_YEAR).status_code == 200
    # Diciembre sigue cerrado por mes: el candado mensual es independiente.
    periods = client.get("/api/periods", headers=headers, params={"months": 36}).json()["items"]
    december = next(p for p in periods if p["year"] == LAST_YEAR and p["month"] == 12)
    assert december["closed"] is True


def test_the_years_listing(client):
    headers, _org_id, account, category = _last_year_with_profit(client)
    assert _income(client, headers, account, category, TODAY, amount="700").status_code == 201

    items = client.get("/api/periods/years", headers=headers).json()["items"]
    assert [item["year"] for item in items] == [TODAY.year, LAST_YEAR]
    current, last = items
    assert set(last) == {
        "year", "entries", "revenue", "expenses", "result", "closed", "can_close",
        "blocked_by", "closing_entry_id", "closing_folio", "reopened_at",
    }
    assert (last["revenue"], last["expenses"], last["result"]) == ("5000.00", "2000.00", "3000.00")
    assert last["entries"] == 2
    assert last["can_close"] is True and last["closed"] is False and last["blocked_by"] is None
    assert current["can_close"] is False  # todavía no termina

    _close(client, headers, LAST_YEAR)
    last = client.get("/api/periods/years", headers=headers).json()["items"][1]
    assert last["closed"] is True and last["can_close"] is False
    assert last["closing_folio"].startswith(f"Dr-{LAST_YEAR}-12-")
    # El cierre no es venta ni gasto: el año sigue mostrando lo que vendió.
    assert (last["revenue"], last["result"]) == ("5000.00", "3000.00")
    assert last["entries"] == 3

    _reopen(client, headers, LAST_YEAR)
    last = client.get("/api/periods/years", headers=headers).json()["items"][1]
    assert last["closed"] is False and last["closing_folio"] is None and last["reopened_at"] is not None


def test_only_the_next_year_in_order_can_be_closed(client):
    headers, _org_id, account, category = _last_year_with_profit(client)
    older = LAST_YEAR - 1
    _income(client, headers, account, category, date(older, 3, 10), amount="800")

    items = {item["year"]: item for item in client.get("/api/periods/years", headers=headers).json()["items"]}
    assert items[older]["can_close"] is True
    assert items[LAST_YEAR]["can_close"] is False
    assert items[LAST_YEAR]["blocked_by"] == older


def test_december_profit_survives_the_close_for_the_dashboard(client, db):
    from app.services.accounting.engine import account_type_balance

    headers, org_id, account, category = _setup(client)
    assert _income(client, headers, account, category, date(LAST_YEAR, 12, 10)).status_code == 201
    assert _close(client, headers, LAST_YEAR).status_code == 200

    december = {"start": date(LAST_YEAR, 12, 1), "end": date(LAST_YEAR, 12, 31)}
    assert account_type_balance(db, org_id, "REVENUE", **december) == Decimal("5000")
    assert account_type_balance(db, org_id, "REVENUE", include_closing=True, **december) == Decimal("0")


def test_a_closed_year_belongs_to_one_company(client):
    headers_a, _org_a, _account_a, _category_a = _last_year_with_profit(client)
    assert _close(client, headers_a, LAST_YEAR).status_code == 200

    headers_b, _org_b, account_b, category_b = _setup(client, email="otra@example.com")
    assert _income(client, headers_b, account_b, category_b, date(LAST_YEAR, 6, 15)).status_code == 201
    assert all(not item["closed"] for item in client.get("/api/periods/years", headers=headers_b).json()["items"])


def test_viewers_cannot_touch_years_and_years_are_bounded(client):
    headers, _org_id, _account, _category = _last_year_with_profit(client)
    client.post(
        "/api/organizations/current/members",
        headers=headers,
        json={"email": "mira@example.com", "name": "Mira", "role": "VIEWER", "password": "supersegura123"},
    )
    viewer = auth_headers(
        client.post("/api/auth/login", json={"email": "mira@example.com", "password": "supersegura123"}).json()
    )
    assert client.get("/api/periods/years", headers=viewer).status_code == 403
    assert _close(client, viewer, LAST_YEAR).status_code == 403
    assert _reopen(client, viewer, LAST_YEAR).status_code == 403

    assert _close(client, headers, 1999).status_code == 422
    assert _close(client, headers, 2101).status_code == 422


def test_reopening_with_a_two_character_reason_is_rejected(client):
    headers, _org_id, _account, _category = _last_year_with_profit(client)
    assert _close(client, headers, LAST_YEAR).status_code == 200

    assert _reopen(client, headers, LAST_YEAR, reason="ok").status_code == 422
    # Sigue cerrado: el rechazo no tocó nada.
    items = client.get("/api/periods/years", headers=headers).json()["items"]
    assert next(item for item in items if item["year"] == LAST_YEAR)["closed"] is True


def test_an_empty_year_reports_money_with_two_decimals(client):
    headers, _org_id, _account, _category = _setup(client)
    items = client.get("/api/periods/years", headers=headers).json()["items"]
    assert (items[0]["revenue"], items[0]["expenses"], items[0]["result"]) == ("0.00", "0.00", "0.00")


def test_a_closed_year_protects_every_earlier_date(client):
    headers, _org_id, account, category = _setup(client)
    older = LAST_YEAR - 1
    accounts = {a["code"]: a for a in client.get("/api/accounting/accounts", headers=headers).json()}
    opening = client.post(
        "/api/accounting/opening-balance",
        headers=headers,
        json={"date": date(older, 12, 31).isoformat(), "lines": [{"account_id": accounts["1191"]["id"], "amount": "100"}]},
    )
    assert opening.status_code == 201, opening.text
    assert _income(client, headers, account, category, date(LAST_YEAR, 6, 15)).status_code == 201
    assert _close(client, headers, LAST_YEAR).status_code == 200

    backdated = _income(client, headers, account, category, date(older, 6, 15))
    assert backdated.status_code == 400
    assert "cerrado" in backdated.json()["detail"]
    assert f"1 de enero de {LAST_YEAR + 1}" in backdated.json()["detail"]

    reverse = client.post(
        f"/api/accounting/journal-entries/{opening.json()['id']}/reverse",
        headers=headers,
        json={"date": TODAY.isoformat()},
    )
    assert reverse.status_code == 400
    assert "cerrado" in reverse.json()["detail"]

    assert _reopen(client, headers, LAST_YEAR).status_code == 200
    assert _income(client, headers, account, category, date(older, 6, 15)).status_code == 201


def test_a_year_close_entry_is_undone_by_reopening_the_year(client):
    headers, _org_id, _account, _category = _last_year_with_profit(client)
    closing_id = _close(client, headers, LAST_YEAR).json()["closing_entry_id"]
    # Un año cerrado rechaza el reverso por el mensaje propio de la póliza de cierre.
    response = client.post(
        f"/api/accounting/journal-entries/{closing_id}/reverse",
        headers=headers,
        json={"date": TODAY.isoformat()},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Una póliza de cierre se deshace reabriendo el ejercicio."
