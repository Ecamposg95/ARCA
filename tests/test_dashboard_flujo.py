"""Serie de entradas y salidas: granularidad y desglose para el tooltip."""

from datetime import date, timedelta
from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client):
    body = register(client, initial_cash="100000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    income_cats = client.get("/api/categories?kind=INCOME", headers=headers).json()
    expense_cats = client.get("/api/categories?kind=EXPENSE", headers=headers).json()
    ventas = next(c for c in income_cats if c["name"] == "Ventas")
    return headers, account, ventas, expense_cats


def _income(client, headers, account, category, amount, when):
    response = client.post(
        "/api/income",
        headers=headers,
        json={
            "date": when.isoformat(),
            "description": "Venta",
            "amount": amount,
            "category_id": category["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    assert response.status_code == 201, response.text


def _expense(client, headers, account, category, amount, when, status="PAID"):
    response = client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": when.isoformat(),
            "description": f"Gasto {category['name']}",
            "amount": amount,
            "category_id": category["id"],
            "financial_account_id": account["id"],
            "status": status,
        },
    )
    assert response.status_code == 201, response.text


def test_monthly_points_carry_inflows_outflows_and_net(client):
    headers, account, ventas, expense_cats = _setup(client)
    today = date.today()
    renta = next(c for c in expense_cats if c["name"] == "Renta")

    _income(client, headers, account, ventas, "30000", today)
    _expense(client, headers, account, renta, "12000", today)

    body = client.get("/api/dashboard/cash-flow", headers=headers).json()
    assert body["granularity"] == "month"
    assert len(body["points"]) == 6

    current = body["points"][-1]
    assert current["bucket"] == today.strftime("%Y-%m")
    assert Decimal(str(current["inflows"])) == Decimal("30000")
    assert Decimal(str(current["outflows"])) == Decimal("12000")
    assert Decimal(str(current["net"])) == Decimal("18000")


def test_week_granularity_buckets_by_iso_week(client):
    headers, account, ventas, _expense_cats = _setup(client)
    today = date.today()
    three_weeks_ago = today - timedelta(days=21)

    _income(client, headers, account, ventas, "10000", today)
    _income(client, headers, account, ventas, "7000", three_weeks_ago)

    body = client.get("/api/dashboard/cash-flow?granularity=week", headers=headers).json()
    assert body["granularity"] == "week"
    assert len(body["points"]) == 12

    def iso_bucket(day: date) -> str:
        year, week, _ = day.isocalendar()
        return f"{year}-W{week:02d}"

    by_bucket = {point["bucket"]: point for point in body["points"]}
    assert Decimal(str(by_bucket[iso_bucket(today)]["inflows"])) == Decimal("10000")
    assert Decimal(str(by_bucket[iso_bucket(three_weeks_ago)]["inflows"])) == Decimal("7000")
    # Cada punto trae su fecha de inicio para que la UI pueda etiquetar.
    assert all("start" in point for point in body["points"])


def test_top_categories_are_three_paid_and_ordered(client):
    headers, account, _ventas, expense_cats = _setup(client)
    today = date.today()
    amounts = {"Renta": "9000", "Software": "7000", "Marketing": "5000", "Honorarios": "3000"}
    for name, amount in amounts.items():
        category = next(c for c in expense_cats if c["name"] == name)
        _expense(client, headers, account, category, amount, today)
    # Un pendiente no ha movido dinero: no pertenece al desglose del flujo.
    nomina = next(c for c in expense_cats if c["name"] == "Nómina")
    _expense(client, headers, account, nomina, "50000", today, status="PENDING")

    body = client.get("/api/dashboard/cash-flow", headers=headers).json()
    current = body["points"][-1]
    tops = current["top_expense_categories"]

    assert [t["category"] for t in tops] == ["Renta", "Software", "Marketing"]
    assert Decimal(str(tops[0]["amount"])) == Decimal("9000")


def test_invalid_granularity_is_rejected(client):
    headers, _account, _ventas, _expense_cats = _setup(client)
    response = client.get("/api/dashboard/cash-flow?granularity=hora", headers=headers)
    assert response.status_code == 422


def test_cash_flow_is_isolated_by_organization(client):
    headers_a, account_a, ventas_a, _cats = _setup(client)
    _income(client, headers_a, account_a, ventas_a, "9999", date.today())

    body_b = register(client, email="otra@example.com", initial_cash="1000")
    headers_b = auth_headers(body_b)
    body = client.get("/api/dashboard/cash-flow", headers=headers_b).json()
    assert all(Decimal(str(p["inflows"])) == Decimal("0") for p in body["points"])
