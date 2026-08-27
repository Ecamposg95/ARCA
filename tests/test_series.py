"""Series para el terminal de análisis: la historia diaria del efectivo.

La serie se reconstruye caminando HACIA ATRÁS desde el saldo actual con los
movimientos diarios: así el último punto siempre coincide con lo que dice el
tablero, que es la única verdad que el usuario puede verificar a ojo.
"""

from datetime import date, timedelta
from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client, email="dueno@example.com"):
    body = register(client, email=email, initial_cash="100000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    ventas = next(
        c
        for c in client.get("/api/categories?kind=INCOME", headers=headers).json()
        if c["name"] == "Ventas"
    )
    renta = next(
        c
        for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json()
        if c["name"] == "Renta"
    )
    return headers, account, ventas, renta


def _income(client, headers, account, categoria, amount, when):
    client.post(
        "/api/income",
        headers=headers,
        json={
            "date": when.isoformat(),
            "description": "Venta",
            "amount": amount,
            "category_id": categoria["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )


def _expense(client, headers, account, categoria, amount, when):
    client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": when.isoformat(),
            "description": "Renta",
            "amount": amount,
            "category_id": categoria["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )


def test_the_series_ends_at_todays_real_cash(client):
    headers, account, ventas, renta = _setup(client)
    today = date.today()
    _income(client, headers, account, ventas, "20000", today - timedelta(days=5))
    _expense(client, headers, account, renta, "8000", today - timedelta(days=2))

    body = client.get("/api/reports/cash-series?days=30", headers=headers).json()
    points = body["points"]

    # Un punto por día, sin huecos, terminando HOY.
    assert len(points) == 30
    assert points[-1]["date"] == today.isoformat()
    dates = [p["date"] for p in points]
    assert dates == sorted(dates)

    # El último saldo es el efectivo real: 100,000 + 20,000 − 8,000.
    assert Decimal(str(points[-1]["balance"])) == Decimal("112000")


def test_each_day_carries_its_flows_and_balance(client):
    headers, account, ventas, renta = _setup(client)
    today = date.today()
    _income(client, headers, account, ventas, "20000", today - timedelta(days=5))
    _expense(client, headers, account, renta, "8000", today - timedelta(days=2))

    points = client.get("/api/reports/cash-series?days=30", headers=headers).json()["points"]
    by_date = {p["date"]: p for p in points}

    day_in = by_date[(today - timedelta(days=5)).isoformat()]
    assert Decimal(str(day_in["inflow"])) == Decimal("20000")
    assert Decimal(str(day_in["balance"])) == Decimal("120000")

    day_out = by_date[(today - timedelta(days=2)).isoformat()]
    assert Decimal(str(day_out["outflow"])) == Decimal("8000")
    assert Decimal(str(day_out["balance"])) == Decimal("112000")

    # Un día sin movimientos arrastra el saldo, no lo inventa.
    quiet = by_date[(today - timedelta(days=3)).isoformat()]
    assert Decimal(str(quiet["inflow"])) == Decimal("0")
    assert Decimal(str(quiet["balance"])) == Decimal("120000")


def test_card_movements_do_not_touch_the_cash_series(client):
    headers, _account, _ventas, renta = _setup(client)
    card = client.post(
        "/api/accounts",
        headers=headers,
        json={"name": "AMEX", "type": "CREDIT_CARD", "credit_limit": "50000"},
    ).json()
    _expense(client, headers, card, renta, "9000", date.today() - timedelta(days=1))

    points = client.get("/api/reports/cash-series?days=10", headers=headers).json()["points"]
    # La tarjeta es deuda: gastar con ella no mueve la curva de efectivo.
    assert Decimal(str(points[-1]["balance"])) == Decimal("100000")
    assert all(Decimal(str(p["outflow"])) == Decimal("0") for p in points)


def test_accounts_come_with_their_own_sparkline(client):
    headers, account, ventas, _renta = _setup(client)
    banco = client.post(
        "/api/accounts", headers=headers, json={"name": "BBVA", "type": "BANK"}
    ).json()
    _income(client, headers, banco, ventas, "30000", date.today() - timedelta(days=3))

    body = client.get("/api/reports/cash-series?days=30", headers=headers).json()
    accounts = {a["name"]: a for a in body["accounts"]}

    assert Decimal(str(accounts["BBVA"]["balance"])) == Decimal("30000")
    assert len(accounts["BBVA"]["series"]) == 30
    # La caja original no se contamina con el ingreso del banco.
    assert Decimal(str(accounts["Caja"]["series"][-1])) == Decimal("100000")
    # El cambio del periodo es lo que entró al banco.
    assert Decimal(str(accounts["BBVA"]["change"])) == Decimal("30000")


def test_runway_reports_months_of_survival(client):
    headers, account, _ventas, renta = _setup(client)
    today = date.today()
    # Quema neta: 15,000/mes de renta sin ingresos, tres meses seguidos.
    for months_ago in (1, 2, 3):
        when = (today.replace(day=15) - timedelta(days=30 * months_ago))
        _expense(client, headers, account, renta, "15000", when)

    body = client.get("/api/reports/cash-series?days=120", headers=headers).json()
    assert Decimal(str(body["avg_monthly_burn"])) > 0
    # 55,000 restantes / ~15,000 de quema ≈ 3.6 meses; el punto es que sea finito y sensato.
    assert 2 < float(body["runway_months"]) < 6


def test_runway_is_null_when_the_business_grows(client):
    headers, account, ventas, _renta = _setup(client)
    _income(client, headers, account, ventas, "50000", date.today() - timedelta(days=10))
    body = client.get("/api/reports/cash-series?days=90", headers=headers).json()
    # Con flujo neto positivo no hay cuenta regresiva que inventar.
    assert body["runway_months"] is None


def test_series_is_isolated_by_organization(client):
    headers_a, account_a, ventas_a, _renta = _setup(client)
    _income(client, headers_a, account_a, ventas_a, "40000", date.today())

    headers_b, _acc, _v, _r = _setup(client, email="otra@example.com")
    points = client.get("/api/reports/cash-series?days=10", headers=headers_b).json()["points"]
    assert Decimal(str(points[-1]["balance"])) == Decimal("100000")


def test_category_series_stacks_paid_expenses_by_month(client):
    headers, account, _ventas, renta = _setup(client)
    today = date.today()
    client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": today.replace(day=10).isoformat(),
            "description": "Renta con IVA",
            "amount": "11600",
            "tax_rate": "0.16",
            "category_id": renta["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )

    body = client.get("/api/reports/category-series?months=3", headers=headers).json()
    assert "Renta" in body["categories"]
    current = next(p for p in body["points"] if p["month"] == today.strftime("%Y-%m"))
    # Sin IVA: el costo real del gasto, consistente con el P&L.
    assert Decimal(str(current["Renta"])) == Decimal("10000")
    assert len(body["points"]) == 3
