"""Catálogo y balanza del Anexo 24: válidos, cuadrados con el libro y sólo de la empresa."""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import xmlschema

from tests.helpers import auth_headers, register

FIXTURES = Path(__file__).parent / "fixtures" / "sat"
CATALOGO_XSD = xmlschema.XMLSchema(str(FIXTURES / "CatalogoCuentas_1_3.xsd"))
BALANZA_XSD = xmlschema.XMLSchema(str(FIXTURES / "BalanzaComprobacion_1_3.xsd"))
TODAY = date.today()
MONTH = {"year": TODAY.year, "month": TODAY.month}
LAST_MONTH_END = TODAY.replace(day=1) - timedelta(days=1)


def _setup(client, email="dueno@example.com", business="Mi Changarro", rfc="FET180312AB1"):
    headers = auth_headers(register(client, email=email, business=business, initial_cash="100000"))
    if rfc is not None:
        assert client.patch("/api/organizations/current", headers=headers, json={"tax_id": rfc}).status_code == 200
    account = client.get("/api/accounts", headers=headers).json()[0]

    def category(kind: str, name: str) -> str:
        rows = client.get(f"/api/categories?kind={kind}", headers=headers).json()
        return next(c["id"] for c in rows if c["name"] == name)

    return headers, account, category


def _income(client, headers, account, category, amount="11600", when=None, description="Venta"):
    response = client.post(
        "/api/income",
        headers=headers,
        json={
            "date": (when or TODAY).isoformat(),
            "description": description,
            "amount": amount,
            "tax_rate": "0.16",
            "category_id": category("INCOME", "Ventas"),
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    assert response.status_code == 201, response.text


def _expense(client, headers, account, category, amount="5800", when=None):
    response = client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": (when or TODAY).isoformat(),
            "description": "Renta",
            "amount": amount,
            "tax_rate": "0.16",
            "category_id": category("EXPENSE", "Renta"),
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    assert response.status_code == 201, response.text


def _balanza(client, headers, **params) -> dict:
    response = client.get("/api/accounting/sat/balanza", headers=headers, params=params or MONTH)
    assert response.status_code == 200, response.text
    text = response.content.decode("utf-8")
    BALANZA_XSD.validate(text)
    decoded = BALANZA_XSD.to_dict(text)
    return {row["@NumCta"]: row for row in decoded["BCE:Ctas"]}


def _catalogo(client, headers) -> dict:
    response = client.get("/api/accounting/sat/catalogo", headers=headers, params=MONTH)
    assert response.status_code == 200, response.text
    text = response.content.decode("utf-8")
    CATALOGO_XSD.validate(text)
    return {row["@NumCta"]: row for row in CATALOGO_XSD.to_dict(text)["catalogocuentas:Ctas"]}


def test_catalog_is_valid_and_carries_levels_and_natures(client):
    headers, _account, _category = _setup(client)
    response = client.get("/api/accounting/sat/catalogo", headers=headers, params=MONTH)
    assert response.headers["content-type"].startswith("application/xml")
    expected_name = f'FET180312AB1{TODAY.year}{TODAY.month:02d}CT.xml'
    assert response.headers["content-disposition"] == f'attachment; filename="{expected_name}"'

    rows = _catalogo(client, headers)
    assert rows["1000"]["@Nivel"] == 1 and "@SubCtaDe" not in rows["1000"]
    assert rows["1100"]["@Nivel"] == 2 and rows["1100"]["@SubCtaDe"] == "1000"
    assert rows["1100"]["@CodAgrup"] == "102.01" and rows["1100"]["@Natur"] == "D"
    assert rows["2100"]["@Natur"] == "A" and rows["4100"]["@Natur"] == "A"
    assert rows["1490"]["@Natur"] == "A"  # contra-activo


def test_balance_matches_the_ledger_and_balances_by_nature(client):
    headers, account, category = _setup(client)
    _income(client, headers, account, category)
    _expense(client, headers, account, category)

    rows = _balanza(client, headers)
    trial = {
        r["code"]: r
        for r in client.get("/api/accounting/trial-balance", headers=headers).json()["rows"]
    }
    for code, row in rows.items():
        if code in trial and code != "1490":
            assert row["@SaldoFin"] == Decimal(str(trial[code]["balance"])), code
    leaves = [row for code, row in rows.items() if len(code) == 4 and code[1:] != "000"]
    assert sum(r["@Debe"] for r in leaves) == sum(r["@Haber"] for r in leaves) > 0
    # Ecuación por naturaleza: deudora suma el debe; acreedora suma el haber.
    caja = rows["1100"]
    assert caja["@SaldoFin"] == caja["@SaldoIni"] + caja["@Debe"] - caja["@Haber"]
    ventas = rows["4100"]
    assert ventas["@SaldoFin"] == ventas["@SaldoIni"] - ventas["@Debe"] + ventas["@Haber"]
    assert ventas["@SaldoFin"] == Decimal("10000.00")


def test_parents_add_up_their_children_and_subtract_contra_assets(client, db):
    headers, account, category = _setup(client)
    _income(client, headers, account, category)
    from app.models.accounting import Account, JournalEntry, JournalEntryLine

    # Se simula depreciación acumulada: abono a 1490 contra gasto 5800, dentro del mes.
    org_id = db.query(Account).filter(Account.code == "1490").one().organization_id
    dep = db.query(Account).filter(Account.code == "1490", Account.organization_id == org_id).one()
    gasto = db.query(Account).filter(Account.code == "5800", Account.organization_id == org_id).one()
    entry = JournalEntry(
        organization_id=org_id, folio="Dr-9999-99-0001", kind="DIARIO", date=TODAY,
        description="Depreciación", status="POSTED",
    )
    db.add(entry)
    db.flush()
    db.add(JournalEntryLine(journal_entry_id=entry.id, account_id=gasto.id, debit=Decimal("300"), credit=0))
    db.add(JournalEntryLine(journal_entry_id=entry.id, account_id=dep.id, debit=0, credit=Decimal("300")))
    db.flush()

    rows = _balanza(client, headers)
    assert rows["1490"]["@SaldoFin"] == Decimal("300.00")  # acreedora, positiva en su naturaleza
    # El activo total resta la depreciación acumulada en vez de sumarla.
    expected_asset = sum(
        (-row["@SaldoFin"] if code == "1490" else row["@SaldoFin"])
        for code, row in rows.items()
        if len(code) == 4 and code.startswith("1") and code != "1000"
    )
    assert rows["1000"]["@SaldoFin"] == expected_asset
    assert rows["1000"]["@SaldoFin"] < sum(
        row["@SaldoFin"] for code, row in rows.items() if len(code) == 4 and code.startswith("1") and code != "1000"
    )


def test_last_month_movements_become_this_months_opening_balance(client):
    headers, account, category = _setup(client)
    _income(client, headers, account, category, amount="2320", when=LAST_MONTH_END)
    _income(client, headers, account, category, amount="1160")

    rows = _balanza(client, headers)
    ventas = rows["4100"]
    assert (ventas["@SaldoIni"], ventas["@Haber"], ventas["@SaldoFin"]) == (
        Decimal("2000.00"),
        Decimal("1000.00"),
        Decimal("3000.00"),
    )


def test_an_overdrawn_bank_shows_a_negative_balance_in_its_nature(client):
    headers, account, category = _setup(client)
    # 100,000 en caja; un gasto mayor deja la cuenta en saldo acreedor.
    _expense(client, headers, account, category, amount="150000")

    caja = _balanza(client, headers)["1100"]
    assert caja["@SaldoFin"] == Decimal("-50000.00")
    assert caja["@SaldoFin"] == caja["@SaldoIni"] + caja["@Debe"] - caja["@Haber"]


def test_a_complementary_balance_is_requested_with_tipo_c(client):
    headers, account, category = _setup(client)
    _income(client, headers, account, category)
    response = client.get(
        "/api/accounting/sat/balanza", headers=headers, params={**MONTH, "tipo": "C"}
    )
    assert response.status_code == 200
    text = response.content.decode("utf-8")
    BALANZA_XSD.validate(text)
    decoded = BALANZA_XSD.to_dict(text)
    assert decoded["@TipoEnvio"] == "C" and decoded["@FechaModBal"] == TODAY.isoformat()
    assert response.headers["content-disposition"].endswith('BC.xml"')


def test_preview_and_errors_when_the_company_is_not_ready(client):
    headers, account, category = _setup(client, rfc=None)
    _income(client, headers, account, category)
    renta = next(
        a for a in client.get("/api/accounting/accounts", headers=headers).json() if a["code"] == "5300"
    )
    client.patch(f"/api/accounting/accounts/{renta['id']}", headers=headers, json={"sat_code": ""})

    preview = client.get("/api/accounting/sat/preview", headers=headers, params=MONTH).json()
    assert preview["rfc_ok"] is False and preview["ready"] is False
    assert [a["code"] for a in preview["missing_accounts"]] == ["5300"]

    response = client.get("/api/accounting/sat/catalogo", headers=headers, params=MONTH)
    assert response.status_code == 400
    assert "RFC" in response.json()["detail"]

    client.patch("/api/organizations/current", headers=headers, json={"tax_id": "fet180312ab1"})
    response = client.get("/api/accounting/sat/balanza", headers=headers, params=MONTH)
    assert response.status_code == 400
    assert "5300" in response.json()["detail"]

    client.patch(f"/api/accounting/accounts/{renta['id']}", headers=headers, json={"sat_code": "601.45"})
    preview = client.get("/api/accounting/sat/preview", headers=headers, params=MONTH).json()
    assert preview["ready"] is True and preview["rfc"] == "FET180312AB1"
    assert _catalogo(client, headers)["5300"]["@CodAgrup"] == "601.45"


def test_only_the_active_company_goes_out(client):
    mine, my_account, my_category = _setup(client, email="yo@example.com", business="Mía")
    theirs, their_account, their_category = _setup(
        client, email="otro@example.com", business="Ajena", rfc="AJE010101AB1"
    )
    _income(client, mine, my_account, my_category, amount="1160")
    _income(client, theirs, their_account, their_category, amount="116000")

    assert _balanza(client, mine)["4100"]["@SaldoFin"] == Decimal("1000.00")


def test_a_viewer_cannot_download(client):
    owner, _account, _category = _setup(client)
    client.post(
        "/api/organizations/current/members",
        headers=owner,
        json={"email": "mira@example.com", "name": "Mira", "role": "VIEWER", "password": "supersegura123"},
    )
    viewer = auth_headers(
        client.post(
            "/api/auth/login", json={"email": "mira@example.com", "password": "supersegura123"}
        ).json()
    )
    assert client.get("/api/accounting/sat/catalogo", headers=viewer, params=MONTH).status_code == 403
