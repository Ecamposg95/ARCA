from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client):
    body = register(client, initial_cash="10000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    renta = next(
        c for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json() if c["name"] == "Renta"
    )
    vendor = client.post("/api/vendors", headers=headers, json={"name": "Inmobiliaria Centro"}).json()
    return headers, account, renta, vendor


def _create(client, headers, renta, vendor, amount="4000", due="2026-09-30"):
    response = client.post(
        "/api/payables",
        headers=headers,
        json={
            "vendor_id": vendor["id"],
            "description": "Renta septiembre",
            "amount": amount,
            "due_date": due,
            "category_id": renta["id"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _trial(client, headers):
    report = client.get("/api/accounting/trial-balance", headers=headers).json()
    return {row["code"]: Decimal(str(row["balance"])) for row in report["rows"]}


def test_create_payable_posts_accrual(client):
    headers, account, renta, vendor = _setup(client)
    payable = _create(client, headers, renta, vendor)
    assert payable["status"] == "OPEN"
    balances = _trial(client, headers)
    assert balances["2100"] == Decimal("4000")  # pasivo reconocido
    assert balances["5300"] == Decimal("4000")  # gasto devengado
    cash = client.get(f"/api/accounts/{account['id']}", headers=headers).json()["current_balance"]
    assert cash == "10000.00"


def test_partial_then_full_payment(client):
    headers, account, renta, vendor = _setup(client)
    payable = _create(client, headers, renta, vendor)

    partial = client.post(
        f"/api/payables/{payable['id']}/pay",
        headers=headers,
        json={"amount": "1500", "financial_account_id": account["id"]},
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["status"] == "PARTIAL"
    cash = client.get(f"/api/accounts/{account['id']}", headers=headers).json()["current_balance"]
    assert cash == "8500.00"

    final = client.post(
        f"/api/payables/{payable['id']}/pay",
        headers=headers,
        json={"amount": "2500", "financial_account_id": account["id"]},
    ).json()
    assert final["status"] == "PAID"
    balances = _trial(client, headers)
    assert balances["2100"] == Decimal("0")
    assert balances["1100"] == Decimal("6000")


def test_balance_sheet_shows_pending_liability(client):
    headers, _account, renta, vendor = _setup(client)
    _create(client, headers, renta, vendor)
    report = client.get("/api/reports/balance-sheet?as_of=2026-12-31", headers=headers).json()
    assert report["balanced"] is True
    liabilities = {row["code"]: row["amount"] for row in report["liabilities"]}
    assert Decimal(str(liabilities["2100"])) == Decimal("4000")


def test_cancel_unpaid_payable_reverses(client):
    headers, _account, renta, vendor = _setup(client)
    payable = _create(client, headers, renta, vendor)
    cancelled = client.post(f"/api/payables/{payable['id']}/cancel", headers=headers, json={})
    assert cancelled.status_code == 200
    balances = _trial(client, headers)
    assert balances.get("2100", Decimal("0")) == Decimal("0")
    assert balances.get("5300", Decimal("0")) == Decimal("0")


def test_payment_cannot_exceed_balance(client):
    headers, account, renta, vendor = _setup(client)
    payable = _create(client, headers, renta, vendor)
    response = client.post(
        f"/api/payables/{payable['id']}/pay",
        headers=headers,
        json={"amount": "4000.01", "financial_account_id": account["id"]},
    )
    assert response.status_code == 400
