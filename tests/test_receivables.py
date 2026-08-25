from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client):
    body = register(client, initial_cash="10000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    categories = client.get("/api/categories?kind=INCOME", headers=headers).json()
    ventas = next(c for c in categories if c["name"] == "Ventas")
    customer = client.post("/api/customers", headers=headers, json={"name": "Grupo Vega"}).json()
    return headers, account, ventas, customer


def _create(client, headers, ventas, customer, amount="7000", due="2026-09-15"):
    response = client.post(
        "/api/receivables",
        headers=headers,
        json={
            "customer_id": customer["id"],
            "description": "Factura a crédito",
            "amount": amount,
            "due_date": due,
            "category_id": ventas["id"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _trial(client, headers):
    report = client.get("/api/accounting/trial-balance", headers=headers).json()
    return {row["code"]: Decimal(str(row["balance"])) for row in report["rows"]}


def test_create_receivable_posts_accrual_not_cash(client):
    headers, account, ventas, customer = _setup(client)
    receivable = _create(client, headers, ventas, customer)
    assert receivable["status"] == "OPEN"
    assert receivable["balance"] == "7000.00"

    balances = _trial(client, headers)
    assert balances["1200"] == Decimal("7000")  # AR reconocida
    assert balances["4100"] == Decimal("7000")  # ingreso devengado
    # el efectivo NO se movió
    cash = client.get(f"/api/accounts/{account['id']}", headers=headers).json()["current_balance"]
    assert cash == "10000.00"


def test_partial_then_full_collection(client):
    headers, account, ventas, customer = _setup(client)
    receivable = _create(client, headers, ventas, customer)

    partial = client.post(
        f"/api/receivables/{receivable['id']}/collect",
        headers=headers,
        json={"amount": "2000", "financial_account_id": account["id"]},
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["status"] == "PARTIAL"
    assert partial.json()["balance"] == "5000.00"
    cash = client.get(f"/api/accounts/{account['id']}", headers=headers).json()["current_balance"]
    assert cash == "12000.00"

    final = client.post(
        f"/api/receivables/{receivable['id']}/collect",
        headers=headers,
        json={"amount": "5000", "financial_account_id": account["id"]},
    ).json()
    assert final["status"] == "PAID"
    balances = _trial(client, headers)
    assert balances["1200"] == Decimal("0")
    assert balances["1100"] == Decimal("17000")  # 10000 inicial + 7000 cobrados


def test_collection_cannot_exceed_balance(client):
    headers, account, ventas, customer = _setup(client)
    receivable = _create(client, headers, ventas, customer)
    response = client.post(
        f"/api/receivables/{receivable['id']}/collect",
        headers=headers,
        json={"amount": "7000.01", "financial_account_id": account["id"]},
    )
    assert response.status_code == 400
    assert "excede" in response.json()["detail"]


def test_cancel_unpaid_reverses_ledger(client):
    headers, _account, ventas, customer = _setup(client)
    receivable = _create(client, headers, ventas, customer)
    cancelled = client.post(f"/api/receivables/{receivable['id']}/cancel", headers=headers, json={})
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    balances = _trial(client, headers)
    assert balances.get("1200", Decimal("0")) == Decimal("0")
    assert balances.get("4100", Decimal("0")) == Decimal("0")


def test_cancel_with_collections_rejected(client):
    headers, account, ventas, customer = _setup(client)
    receivable = _create(client, headers, ventas, customer)
    client.post(
        f"/api/receivables/{receivable['id']}/collect",
        headers=headers,
        json={"amount": "1000", "financial_account_id": account["id"]},
    )
    response = client.post(f"/api/receivables/{receivable['id']}/cancel", headers=headers, json={})
    assert response.status_code == 400


def test_overdue_is_computed(client):
    headers, _account, ventas, customer = _setup(client)
    _create(client, headers, ventas, customer, due="2026-01-01")  # ya vencida
    body = client.get("/api/receivables?status=OVERDUE", headers=headers).json()
    assert body["total"] == 1
    assert body["items"][0]["display_status"] == "OVERDUE"
    assert body["items"][0]["is_overdue"] is True


def test_tenant_isolation_on_collect(client):
    headers_a, account_a, ventas_a, customer_a = _setup(client)
    body_b = register(client, email="b@example.com", business="Negocio B")
    headers_b = auth_headers(body_b)
    receivable = _create(client, headers_a, ventas_a, customer_a)
    response = client.post(
        f"/api/receivables/{receivable['id']}/collect",
        headers=headers_b,
        json={"amount": "1000", "financial_account_id": account_a["id"]},
    )
    assert response.status_code == 404
