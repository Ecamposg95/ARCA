"""Patrimonio neto: lo que tienes menos lo que debes, tomado del libro."""

from datetime import date
from decimal import Decimal

from tests.helpers import auth_headers, register


def test_net_worth_starts_at_the_opening_cash(client):
    body = register(client, initial_cash="50000")
    headers = auth_headers(body)

    report = client.get("/api/reports/net-worth", headers=headers).json()
    assert Decimal(str(report["total_assets"])) == Decimal("50000")
    assert Decimal(str(report["total_liabilities"])) == Decimal("0")
    assert Decimal(str(report["net_worth"])) == Decimal("50000")


def test_card_debt_lowers_net_worth_without_touching_cash(client):
    body = register(client, initial_cash="50000")
    headers = auth_headers(body)
    card = client.post(
        "/api/accounts",
        headers=headers,
        json={"name": "AMEX", "type": "CREDIT_CARD", "credit_limit": "100000"},
    ).json()
    software = next(
        c
        for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json()
        if c["name"] == "Software"
    )

    before = client.get("/api/reports/net-worth", headers=headers).json()
    client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": date.today().isoformat(),
            "description": "Licencias",
            "amount": "8000",
            "category_id": software["id"],
            "financial_account_id": card["id"],
            "status": "PAID",
        },
    )
    after = client.get("/api/reports/net-worth", headers=headers).json()

    # El efectivo no se movió: lo que cambió es la deuda, y con ella el patrimonio.
    assert Decimal(str(after["total_assets"])) == Decimal(str(before["total_assets"]))
    assert Decimal(str(after["total_liabilities"])) == Decimal("8000")
    assert Decimal(str(after["net_worth"])) == Decimal(str(before["net_worth"])) - Decimal("8000")


def test_net_worth_matches_the_balance_sheet(client):
    body = register(client, initial_cash="30000")
    headers = auth_headers(body)
    ventas = next(
        c
        for c in client.get("/api/categories?kind=INCOME", headers=headers).json()
        if c["name"] == "Ventas"
    )
    account = client.get("/api/accounts", headers=headers).json()[0]
    client.post(
        "/api/income",
        headers=headers,
        json={
            "date": date.today().isoformat(),
            "description": "Venta",
            "amount": "11600",
            "tax_rate": "0.16",
            "category_id": ventas["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )

    net = client.get("/api/reports/net-worth", headers=headers).json()
    sheet = client.get("/api/reports/balance-sheet", headers=headers).json()

    assert Decimal(str(net["total_assets"])) == Decimal(str(sheet["total_assets"]))
    assert Decimal(str(net["total_liabilities"])) == Decimal(str(sheet["total_liabilities"]))
    # El patrimonio del reporte es el capital contable del balance.
    assert Decimal(str(net["net_worth"])) == Decimal(str(sheet["total_equity"]))
    assert sheet["balanced"] is True


def test_series_covers_the_requested_months(client):
    body = register(client, initial_cash="1000")
    headers = auth_headers(body)
    report = client.get("/api/reports/net-worth?months=6", headers=headers).json()
    assert len(report["series"]) == 6
    assert report["series"][-1]["month"] == date.today().strftime("%Y-%m")


def test_depreciation_lowers_net_worth(client):
    from datetime import timedelta

    body = register(client, initial_cash="100000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]

    # Un mes ya cerrado, para que la póliza no quede con fecha futura.
    closed = date.today().replace(day=1) - timedelta(days=1)
    bought = (closed.replace(day=1) - timedelta(days=1)).replace(day=1)

    client.post(
        "/api/fixed-assets",
        headers=headers,
        json={
            "name": "Laptop",
            "acquisition_date": bought.isoformat(),
            "cost": "36000",
            "useful_life_months": 36,
            "financial_account_id": account["id"],
        },
    )
    before = client.get("/api/reports/net-worth", headers=headers).json()
    # Comprar no cambia el patrimonio: cambias dinero por un activo.
    assert Decimal(str(before["net_worth"])) == Decimal("100000")

    client.post(
        "/api/fixed-assets/depreciate",
        headers=headers,
        json={"year": closed.year, "month": closed.month},
    )
    after = client.get("/api/reports/net-worth", headers=headers).json()
    # Depreciar sí: el activo vale menos y nada lo compensa.
    assert Decimal(str(after["net_worth"])) == Decimal("99000")
