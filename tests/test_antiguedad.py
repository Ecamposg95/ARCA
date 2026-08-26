"""Antigüedad de saldos: los tramos se miden desde el vencimiento, no desde la emisión."""

from datetime import date, timedelta
from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client, email="dueno@example.com"):
    body = register(client, email=email, initial_cash="50000")
    headers = auth_headers(body)
    ventas = next(
        c
        for c in client.get("/api/categories?kind=INCOME", headers=headers).json()
        if c["name"] == "Ventas"
    )
    return headers, ventas


def _receivable(client, headers, category, customer_id, amount, days_overdue):
    today = date.today()
    return client.post(
        "/api/receivables",
        headers=headers,
        json={
            "customer_id": customer_id,
            "description": f"Factura vencida {days_overdue}d",
            "amount": amount,
            "date": (today - timedelta(days=days_overdue + 30)).isoformat(),
            "due_date": (today - timedelta(days=days_overdue)).isoformat(),
            "category_id": category["id"],
        },
    ).json()


def test_buckets_split_by_days_past_due(client):
    headers, ventas = _setup(client)
    customer = client.post("/api/customers", headers=headers, json={"name": "Cliente"}).json()

    _receivable(client, headers, ventas, customer["id"], "1000", 10)  # 1-30
    _receivable(client, headers, ventas, customer["id"], "2000", 45)  # 31-60
    _receivable(client, headers, ventas, customer["id"], "4000", 75)  # 61-90
    _receivable(client, headers, ventas, customer["id"], "8000", 200)  # +90

    report = client.get("/api/reports/aging", headers=headers).json()
    totals = report["totals"]
    assert Decimal(str(totals["1-30"])) == Decimal("1000")
    assert Decimal(str(totals["31-60"])) == Decimal("2000")
    assert Decimal(str(totals["61-90"])) == Decimal("4000")
    assert Decimal(str(totals["+90"])) == Decimal("8000")
    assert Decimal(str(report["total"])) == Decimal("15000")


def test_not_yet_due_is_not_aged(client):
    headers, ventas = _setup(client)
    customer = client.post("/api/customers", headers=headers, json={"name": "Cliente"}).json()
    today = date.today()
    client.post(
        "/api/receivables",
        headers=headers,
        json={
            "customer_id": customer["id"],
            "description": "Factura por vencer",
            "amount": "5000",
            "date": today.isoformat(),
            "due_date": (today + timedelta(days=20)).isoformat(),
            "category_id": ventas["id"],
        },
    )
    report = client.get("/api/reports/aging", headers=headers).json()
    # Lo que aún no vence va a su propio tramo: no ensucia lo vencido.
    assert Decimal(str(report["totals"]["Por vencer"])) == Decimal("5000")
    assert Decimal(str(report["totals"]["1-30"])) == Decimal("0")
    assert Decimal(str(report["overdue"])) == Decimal("0")
    assert report["average_days"] == 0


def test_only_the_unpaid_balance_ages(client):
    headers, ventas = _setup(client)
    customer = client.post("/api/customers", headers=headers, json={"name": "Cliente"}).json()
    account = client.get("/api/accounts", headers=headers).json()[0]
    receivable = _receivable(client, headers, ventas, customer["id"], "10000", 40)
    client.post(
        f"/api/receivables/{receivable['id']}/collect",
        headers=headers,
        json={"amount": "6000", "financial_account_id": account["id"]},
    )
    report = client.get("/api/reports/aging", headers=headers).json()
    assert Decimal(str(report["total"])) == Decimal("4000")
    assert Decimal(str(report["contacts"][0]["total"])) == Decimal("4000")


def test_average_days_weighs_by_balance(client):
    headers, ventas = _setup(client)
    customer = client.post("/api/customers", headers=headers, json={"name": "Cliente"}).json()
    # 1,000 a 10 días y 9,000 a 100: el promedio debe acercarse a 100, no a 55.
    _receivable(client, headers, ventas, customer["id"], "1000", 10)
    _receivable(client, headers, ventas, customer["id"], "9000", 100)
    report = client.get("/api/reports/aging", headers=headers).json()
    assert report["average_days"] == 91


def test_payables_use_the_same_report(client):
    headers, _ventas = _setup(client)
    gastos = next(
        c
        for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json()
        if c["name"] == "Renta"
    )
    vendor = client.post("/api/vendors", headers=headers, json={"name": "Proveedor"}).json()
    today = date.today()
    client.post(
        "/api/payables",
        headers=headers,
        json={
            "vendor_id": vendor["id"],
            "description": "Renta vencida",
            "amount": "3000",
            "due_date": (today - timedelta(days=50)).isoformat(),
            "category_id": gastos["id"],
        },
    )
    report = client.get("/api/reports/aging?kind=payable", headers=headers).json()
    assert report["kind"] == "payable"
    assert Decimal(str(report["totals"]["31-60"])) == Decimal("3000")
    assert report["contacts"][0]["name"] == "Proveedor"


def test_aging_is_isolated_by_organization(client):
    headers_a, ventas_a = _setup(client)
    customer_a = client.post("/api/customers", headers=headers_a, json={"name": "A"}).json()
    _receivable(client, headers_a, ventas_a, customer_a["id"], "7000", 45)

    headers_b, _ventas_b = _setup(client, email="otra@example.com")
    report_b = client.get("/api/reports/aging", headers=headers_b).json()
    assert Decimal(str(report_b["total"])) == Decimal("0")
    assert report_b["contacts"] == []


def test_previous_average_days_reflects_last_month_state(client):
    headers, ventas = _setup(client)
    customer = client.post("/api/customers", headers=headers, json={"name": "Cliente"}).json()
    # Vencida hace 40 días: hoy promedia 40; hace 30 días llevaba 10 de vencida.
    _receivable(client, headers, ventas, customer["id"], "10000", 40)

    report = client.get("/api/reports/aging", headers=headers).json()
    assert report["average_days"] == 40
    assert report["previous_average_days"] == 10


def test_recent_receivables_do_not_exist_in_the_previous_snapshot(client):
    headers, ventas = _setup(client)
    customer = client.post("/api/customers", headers=headers, json={"name": "Cliente"}).json()
    today = date.today()
    # Emitida hace 5 días: hace un mes no existía.
    client.post(
        "/api/receivables",
        headers=headers,
        json={
            "customer_id": customer["id"],
            "description": "Factura nueva",
            "amount": "8000",
            "date": (today - timedelta(days=5)).isoformat(),
            "due_date": (today + timedelta(days=25)).isoformat(),
            "category_id": ventas["id"],
        },
    )
    report = client.get("/api/reports/aging", headers=headers).json()
    assert report["previous_average_days"] == 0


def test_collections_after_the_snapshot_do_not_shrink_the_previous_balance(client):
    headers, ventas = _setup(client)
    customer = client.post("/api/customers", headers=headers, json={"name": "Cliente"}).json()
    account = client.get("/api/accounts", headers=headers).json()[0]

    receivable = _receivable(client, headers, ventas, customer["id"], "10000", 60)
    # Cobro reciente: hoy el saldo es 2,000, pero hace 30 días eran los 10,000.
    client.post(
        f"/api/receivables/{receivable['id']}/collect",
        headers=headers,
        json={"amount": "8000", "financial_account_id": account["id"]},
    )

    report = client.get("/api/reports/aging", headers=headers).json()
    assert report["average_days"] == 60  # el saldo restante sigue igual de viejo
    assert report["previous_average_days"] == 30


def test_a_fully_collected_receivable_still_counts_in_the_snapshot(client):
    headers, ventas = _setup(client)
    customer = client.post("/api/customers", headers=headers, json={"name": "Cliente"}).json()
    account = client.get("/api/accounts", headers=headers).json()[0]

    receivable = _receivable(client, headers, ventas, customer["id"], "6000", 45)
    client.post(
        f"/api/receivables/{receivable['id']}/collect",
        headers=headers,
        json={"amount": "6000", "financial_account_id": account["id"]},
    )

    report = client.get("/api/reports/aging", headers=headers).json()
    # Hoy no debe nada… pero hace 30 días llevaba 15 días de vencida.
    assert Decimal(str(report["total"])) == Decimal("0")
    assert report["previous_average_days"] == 15
