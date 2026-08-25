"""Saldo corriente: debe reconstruir el estado de cuenta movimiento por movimiento."""

from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client):
    body = register(client, initial_cash="10000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    ventas = next(
        c for c in client.get("/api/categories?kind=INCOME", headers=headers).json() if c["name"] == "Ventas"
    )
    renta = next(
        c for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json() if c["name"] == "Renta"
    )
    return headers, account, ventas, renta


def test_running_balance_reconstructs_statement(client):
    headers, account, ventas, renta = _setup(client)
    for date, amount, kind, category in (
        ("2026-08-01", "5000", "income", ventas),
        ("2026-08-05", "2000", "expenses", renta),
        ("2026-08-10", "3000", "income", ventas),
    ):
        endpoint = "/api/income" if kind == "income" else "/api/expenses"
        client.post(
            endpoint,
            headers=headers,
            json={
                "date": date,
                "description": f"{kind} {date}",
                "amount": amount,
                "category_id": category["id"],
                "financial_account_id": account["id"],
                "status": "PAID",
            },
        )

    body = client.get(f"/api/transactions?account_id={account['id']}", headers=headers).json()
    items = body["items"]
    # Orden descendente: el más reciente primero. 10000 + 5000 - 2000 + 3000 = 16000
    assert [Decimal(item["running_balance"]) for item in items] == [
        Decimal("16000.00"),  # tras el ingreso del 10
        Decimal("13000.00"),  # tras el gasto del 5
        Decimal("15000.00"),  # tras el ingreso del 1
    ]


def test_running_balance_absent_without_account_filter(client):
    headers, account, ventas, _renta = _setup(client)
    client.post(
        "/api/income",
        headers=headers,
        json={
            "date": "2026-08-01",
            "description": "Venta",
            "amount": "1000",
            "category_id": ventas["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    body = client.get("/api/transactions", headers=headers).json()
    assert all(item["running_balance"] is None for item in body["items"])


def test_running_balance_survives_pagination(client):
    headers, account, ventas, _renta = _setup(client)
    for day in range(1, 6):
        client.post(
            "/api/income",
            headers=headers,
            json={
                "date": f"2026-08-{day:02d}",
                "description": f"Venta {day}",
                "amount": "1000",
                "category_id": ventas["id"],
                "financial_account_id": account["id"],
                "status": "PAID",
            },
        )
    # Segunda página: el acumulado debe seguir siendo correcto, no reiniciarse.
    page = client.get(
        f"/api/transactions?account_id={account['id']}&limit=2&offset=2", headers=headers
    ).json()
    # 10000 + 5 ventas de 1000 = 15000; la 3ª y 4ª más recientes dejan 13000 y 12000.
    assert [Decimal(item["running_balance"]) for item in page["items"]] == [
        Decimal("13000.00"),
        Decimal("12000.00"),
    ]


def test_dashboard_exposes_previous_period(client):
    headers, account, ventas, _renta = _setup(client)
    summary = client.get("/api/dashboard/summary", headers=headers).json()
    for key in ("previous_revenue", "previous_expenses", "previous_profit"):
        assert key in summary
