"""Proyección de liquidez: sólo compromisos con fecha, nunca pronósticos."""

from datetime import date, timedelta
from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client):
    body = register(client, initial_cash="50000")
    headers = auth_headers(body)
    ventas = next(
        c for c in client.get("/api/categories?kind=INCOME", headers=headers).json() if c["name"] == "Ventas"
    )
    renta = next(
        c for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json() if c["name"] == "Renta"
    )
    customer = client.post("/api/customers", headers=headers, json={"name": "Cliente"}).json()
    vendor = client.post("/api/vendors", headers=headers, json={"name": "Proveedor"}).json()
    return headers, ventas, renta, customer, vendor


def test_projection_uses_committed_amounts(client):
    headers, ventas, renta, customer, vendor = _setup(client)
    today = date.today()

    client.post(
        "/api/receivables",
        headers=headers,
        json={
            "customer_id": customer["id"],
            "description": "Factura por cobrar",
            "amount": "30000",
            "due_date": (today + timedelta(days=10)).isoformat(),
            "category_id": ventas["id"],
        },
    )
    client.post(
        "/api/payables",
        headers=headers,
        json={
            "vendor_id": vendor["id"],
            "description": "Renta por pagar",
            "amount": "12000",
            "due_date": (today + timedelta(days=20)).isoformat(),
            "category_id": renta["id"],
        },
    )

    report = client.get("/api/reports/cash-projection?days=90", headers=headers).json()
    assert Decimal(str(report["opening_cash"])) == Decimal("50000")
    assert Decimal(str(report["expected_inflows"])) == Decimal("30000")
    assert Decimal(str(report["expected_outflows"])) == Decimal("12000")
    assert Decimal(str(report["projected_cash"])) == Decimal("68000")
    assert report["shortfall_date"] is None


def test_projection_flags_the_day_money_runs_out(client):
    headers, _ventas, renta, _customer, vendor = _setup(client)
    today = date.today()

    # Un compromiso mayor al efectivo disponible.
    client.post(
        "/api/payables",
        headers=headers,
        json={
            "vendor_id": vendor["id"],
            "description": "Pago grande",
            "amount": "80000",
            "due_date": (today + timedelta(days=15)).isoformat(),
            "category_id": renta["id"],
        },
    )
    report = client.get("/api/reports/cash-projection", headers=headers).json()
    assert Decimal(str(report["projected_cash"])) == Decimal("-30000")
    assert report["shortfall_date"] == (today + timedelta(days=15)).isoformat()


def test_overdue_counts_as_due_today(client):
    headers, ventas, _renta, customer, _vendor = _setup(client)
    today = date.today()
    client.post(
        "/api/receivables",
        headers=headers,
        json={
            "customer_id": customer["id"],
            "description": "Factura vencida",
            "amount": "5000",
            "due_date": (today - timedelta(days=30)).isoformat(),
            "category_id": ventas["id"],
        },
    )
    report = client.get("/api/reports/cash-projection", headers=headers).json()
    # Lo vencido es exigible hoy: no se proyecta al pasado.
    assert report["points"][1]["date"] == today.isoformat()


def test_partial_collection_only_projects_the_balance(client):
    headers, ventas, _renta, customer, _vendor = _setup(client)
    today = date.today()
    account = client.get("/api/accounts", headers=headers).json()[0]
    receivable = client.post(
        "/api/receivables",
        headers=headers,
        json={
            "customer_id": customer["id"],
            "description": "Factura parcial",
            "amount": "20000",
            "due_date": (today + timedelta(days=5)).isoformat(),
            "category_id": ventas["id"],
        },
    ).json()
    client.post(
        f"/api/receivables/{receivable['id']}/collect",
        headers=headers,
        json={"amount": "8000", "financial_account_id": account["id"]},
    )
    report = client.get("/api/reports/cash-projection", headers=headers).json()
    # Ya entraron 8,000 (están en el efectivo); sólo faltan 12,000 por cobrar.
    assert Decimal(str(report["expected_inflows"])) == Decimal("12000")
    assert Decimal(str(report["opening_cash"])) == Decimal("58000")


def test_projection_points_name_their_commitment(client):
    headers, ventas, _renta, customer, _vendor = _setup(client)
    today = date.today()
    client.post(
        "/api/receivables",
        headers=headers,
        json={
            "customer_id": customer["id"],
            "description": "Factura F-0099",
            "amount": "10000",
            "due_date": (today + timedelta(days=10)).isoformat(),
            "category_id": ventas["id"],
        },
    )
    points = client.get("/api/reports/cash-projection", headers=headers).json()["points"]
    # El primer punto es "hoy" (sin concepto); los compromisos dicen cuál son.
    assert points[1]["description"] == "Factura F-0099"
