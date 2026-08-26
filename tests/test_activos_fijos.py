"""Activos fijos: el costo no es gasto del mes, se lleva a resultados poco a poco."""

from datetime import date
from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client, email="dueno@example.com"):
    body = register(client, email=email, initial_cash="500000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    return headers, account


def _create_asset(client, headers, account, **overrides):
    payload = {
        "name": "Laptop del equipo",
        "category": "EQUIPO_COMPUTO",
        "acquisition_date": "2026-01-15",
        "cost": "36000",
        "tax_amount": "5760",
        "useful_life_months": 36,
        "financial_account_id": account["id"],
    }
    payload.update(overrides)
    response = client.post("/api/fixed-assets", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_purchase_lands_in_the_asset_not_in_expenses(client):
    headers, account = _setup(client)
    _create_asset(client, headers, account)

    balance = client.get("/api/accounting/trial-balance", headers=headers).json()
    rows = {row["code"]: Decimal(str(row["debit"])) for row in balance["rows"]}
    # El costo vive en 1400, no en una cuenta de gasto.
    assert rows.get("1400") == Decimal("36000")

    pl = client.get("/api/reports/profit-loss", headers=headers).json()
    assert Decimal(str(pl["total_expenses"])) == Decimal("0")


def test_monthly_depreciation_is_straight_line(client):
    headers, account = _setup(client)
    asset = _create_asset(client, headers, account, salvage_value="0")
    # 36,000 entre 36 meses.
    assert Decimal(str(asset["monthly_depreciation"])) == Decimal("1000")


def test_salvage_value_is_not_depreciated(client):
    headers, account = _setup(client)
    asset = _create_asset(
        client, headers, account, cost="40000", salvage_value="4000", useful_life_months="36"
    )
    # Sólo se deprecian 36,000 de los 40,000.
    assert Decimal(str(asset["monthly_depreciation"])) == Decimal("1000")


def test_running_depreciation_posts_and_moves_book_value(client):
    headers, account = _setup(client)
    _create_asset(client, headers, account)

    run = client.post(
        "/api/fixed-assets/depreciate", headers=headers, json={"year": 2026, "month": 3}
    ).json()
    assert len(run["posted"]) == 1
    assert Decimal(str(run["total"])) == Decimal("1000")

    asset = client.get("/api/fixed-assets", headers=headers).json()["items"][0]
    assert Decimal(str(asset["accumulated_depreciation"])) == Decimal("1000")
    assert Decimal(str(asset["book_value"])) == Decimal("35000")

    pl = client.get(
        "/api/reports/profit-loss?start=2026-03-01&end=2026-03-31", headers=headers
    ).json()
    assert Decimal(str(pl["total_expenses"])) == Decimal("1000")


def test_depreciation_is_idempotent_per_month(client):
    headers, account = _setup(client)
    _create_asset(client, headers, account)

    client.post("/api/fixed-assets/depreciate", headers=headers, json={"year": 2026, "month": 3})
    again = client.post(
        "/api/fixed-assets/depreciate", headers=headers, json={"year": 2026, "month": 3}
    ).json()

    # Un mes contable no puede depreciarse dos veces.
    assert again["posted"] == []
    assert again["skipped"][0]["reason"] == "ya asentado"
    asset = client.get("/api/fixed-assets", headers=headers).json()["items"][0]
    assert Decimal(str(asset["accumulated_depreciation"])) == Decimal("1000")


def test_the_month_of_purchase_is_not_depreciated(client):
    headers, account = _setup(client)
    _create_asset(client, headers, account, acquisition_date="2026-01-15")
    run = client.post(
        "/api/fixed-assets/depreciate", headers=headers, json={"year": 2026, "month": 1}
    ).json()
    assert run["posted"] == []
    assert run["skipped"][0]["reason"] == "aún no cumple un mes"


def test_depreciation_never_exceeds_the_depreciable_amount(client):
    headers, account = _setup(client)
    # Un activo de vida corta para llegar al final rápido.
    _create_asset(client, headers, account, cost="3000", useful_life_months=3, tax_amount="0")

    for month in (2, 3, 4, 5, 6):
        client.post(
            "/api/fixed-assets/depreciate", headers=headers, json={"year": 2026, "month": month}
        )

    asset = client.get("/api/fixed-assets", headers=headers).json()["items"][0]
    assert Decimal(str(asset["accumulated_depreciation"])) == Decimal("3000")
    assert Decimal(str(asset["book_value"])) == Decimal("0")


def test_ledger_stays_balanced_after_depreciation(client):
    headers, account = _setup(client)
    _create_asset(client, headers, account)
    client.post("/api/fixed-assets/depreciate", headers=headers, json={"year": 2026, "month": 4})

    balance = client.get("/api/accounting/trial-balance", headers=headers).json()
    assert Decimal(str(balance["total_debit"])) == Decimal(str(balance["total_credit"]))


def test_disposed_assets_stop_depreciating(client):
    headers, account = _setup(client)
    asset = _create_asset(client, headers, account)
    client.post(
        f"/api/fixed-assets/{asset['id']}/dispose",
        headers=headers,
        json={"disposed_at": date(2026, 3, 1).isoformat()},
    )
    run = client.post(
        "/api/fixed-assets/depreciate", headers=headers, json={"year": 2026, "month": 5}
    ).json()
    assert run["posted"] == []


def test_salvage_above_cost_is_rejected(client):
    headers, account = _setup(client)
    response = client.post(
        "/api/fixed-assets",
        headers=headers,
        json={
            "name": "Absurdo",
            "acquisition_date": "2026-01-01",
            "cost": "1000",
            "salvage_value": "1000",
            "useful_life_months": 12,
            "financial_account_id": account["id"],
        },
    )
    assert response.status_code == 400
    assert "rescate" in response.json()["detail"]


def test_assets_are_isolated_by_organization(client):
    headers_a, account_a = _setup(client)
    _create_asset(client, headers_a, account_a)

    headers_b, _account_b = _setup(client, email="otra@example.com")
    assert client.get("/api/fixed-assets", headers=headers_b).json()["items"] == []


def test_cannot_depreciate_a_month_that_has_not_ended(client):
    headers, account = _setup(client)
    _create_asset(client, headers, account)
    today = date.today()
    response = client.post(
        "/api/fixed-assets/depreciate",
        headers=headers,
        json={"year": today.year, "month": today.month},
    )
    # Asentar al 31 con fecha futura escondería el gasto hasta que llegue el día.
    assert response.status_code == 400
    assert "todavía no termina" in response.json()["detail"]


def test_the_idempotency_key_fits_in_the_column(client):
    """SQLite ignora el largo de VARCHAR; PostgreSQL no.

    Esta prueba existe porque la clave `{activo}:{AAAA-MM}` medía 44 caracteres
    contra una columna de 36: en SQLite pasaba y en producción reventaba.
    """
    from app.models.accounting import JournalEntry

    headers, account = _setup(client)
    _create_asset(client, headers, account)
    client.post("/api/fixed-assets/depreciate", headers=headers, json={"year": 2026, "month": 3})

    limit = JournalEntry.__table__.c.source_id.type.length
    entries = client.get(
        "/api/accounting/journal-entries?source_type=depreciation", headers=headers
    ).json()["items"]
    assert entries, "la depreciación debe dejar su póliza"
    for entry in entries:
        assert len(entry["source_id"]) <= limit, (
            f"la clave mide {len(entry['source_id'])} y la columna acepta {limit}"
        )
