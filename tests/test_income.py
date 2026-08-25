from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client):
    body = register(client, initial_cash="10000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    categories = client.get("/api/categories?kind=INCOME", headers=headers).json()
    ventas = next(c for c in categories if c["name"] == "Ventas")
    return headers, account, ventas


def test_paid_income_increases_cash_and_revenue(client):
    headers, account, ventas = _setup(client)
    response = client.post(
        "/api/income",
        headers=headers,
        json={
            "date": "2026-08-10",
            "description": "Venta de mostrador",
            "amount": "1500.50",
            "category_id": ventas["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    assert response.status_code == 201, response.text
    income = response.json()
    assert income["status"] == "PAID"

    # cash ↑
    updated = client.get(f"/api/accounts/{account['id']}", headers=headers).json()
    assert updated["current_balance"] == "11500.50"

    # movimiento creado
    movements = client.get("/api/transactions", headers=headers).json()
    assert any(m["source_id"] == income["id"] and m["transaction_type"] == "INCOME" for m in movements["items"])


def test_pending_income_moves_nothing_until_paid(client):
    headers, account, ventas = _setup(client)
    created = client.post(
        "/api/income",
        headers=headers,
        json={
            "date": "2026-08-10",
            "description": "Factura por cobrar",
            "amount": "2000",
            "category_id": ventas["id"],
        },
    ).json()
    assert created["status"] == "PENDING"
    balance = client.get(f"/api/accounts/{account['id']}", headers=headers).json()["current_balance"]
    assert balance == "10000.00"

    paid = client.post(
        f"/api/income/{created['id']}/pay",
        headers=headers,
        json={"financial_account_id": account["id"]},
    )
    assert paid.status_code == 200, paid.text
    balance = client.get(f"/api/accounts/{account['id']}", headers=headers).json()["current_balance"]
    assert balance == "12000.00"


def test_income_rejects_zero_amount(client):
    headers, account, ventas = _setup(client)
    response = client.post(
        "/api/income",
        headers=headers,
        json={
            "date": "2026-08-10",
            "description": "inválido",
            "amount": "0",
            "category_id": ventas["id"],
        },
    )
    assert response.status_code == 422


def test_paid_income_cannot_be_cancelled_yet(client):
    headers, account, ventas = _setup(client)
    income = client.post(
        "/api/income",
        headers=headers,
        json={
            "date": "2026-08-10",
            "description": "Venta",
            "amount": "100",
            "category_id": ventas["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    ).json()
    response = client.post(f"/api/income/{income['id']}/cancel", headers=headers, json={})
    assert response.status_code == 400


def test_income_list_pagination_envelope(client):
    headers, _account, _ventas = _setup(client)
    body = client.get("/api/income", headers=headers).json()
    # Las cuatro llaves canónicas Atlas siempre están; las listas de dinero
    # añaden total_amount (suma de TODO el filtro, no sólo de la página).
    assert {"items", "total", "limit", "offset"} <= set(body.keys())
    assert set(body.keys()) - {"items", "total", "limit", "offset"} == {"total_amount"}


def test_income_total_amount_covers_whole_filter(client):
    headers, account, ventas = _setup(client)
    for amount in ("1000", "2500"):
        client.post(
            "/api/income",
            headers=headers,
            json={
                "date": "2026-08-10",
                "description": "Venta",
                "amount": amount,
                "category_id": ventas["id"],
                "financial_account_id": account["id"],
                "status": "PAID",
            },
        )
    body = client.get("/api/income?limit=1", headers=headers).json()
    assert len(body["items"]) == 1  # una sola fila en la página…
    assert Decimal(str(body["total_amount"])) == Decimal("3500")  # …pero el total es del filtro
