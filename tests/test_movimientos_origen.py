"""Filtro de movimientos por origen: el historial de UNA cuenta por cobrar."""

from datetime import date, timedelta

from tests.helpers import auth_headers, register


def test_movements_filter_by_source(client):
    body = register(client, initial_cash="50000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    ventas = next(
        c
        for c in client.get("/api/categories?kind=INCOME", headers=headers).json()
        if c["name"] == "Ventas"
    )
    customer = client.post("/api/customers", headers=headers, json={"name": "Cliente"}).json()
    receivable = client.post(
        "/api/receivables",
        headers=headers,
        json={
            "customer_id": customer["id"],
            "description": "Factura con dos cobros",
            "amount": "10000",
            "due_date": (date.today() + timedelta(days=30)).isoformat(),
            "category_id": ventas["id"],
        },
    ).json()
    for amount in ("4000", "3000"):
        client.post(
            f"/api/receivables/{receivable['id']}/collect",
            headers=headers,
            json={"amount": amount, "financial_account_id": account["id"]},
        )
    # Ruido: un ingreso directo que NO debe aparecer en el historial.
    client.post(
        "/api/income",
        headers=headers,
        json={
            "date": date.today().isoformat(),
            "description": "Venta directa",
            "amount": "2000",
            "category_id": ventas["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )

    page = client.get(
        f"/api/transactions?source_type=receivable&source_id={receivable['id']}",
        headers=headers,
    ).json()
    assert page["total"] == 2
    amounts = sorted(float(t["amount"]) for t in page["items"])
    assert amounts == [3000.0, 4000.0]
    assert all(t["transaction_type"] == "RECEIVABLE_COLLECTION" for t in page["items"])


def test_source_filter_is_tenant_isolated(client):
    body_a = register(client, email="a@example.com", initial_cash="1000")
    headers_a = auth_headers(body_a)
    body_b = register(client, email="b@example.com", initial_cash="1000")
    headers_b = auth_headers(body_b)

    # B no puede leer movimientos de A ni con el source_id correcto.
    page = client.get(
        "/api/transactions?source_type=receivable&source_id=cualquiera",
        headers=headers_b,
    ).json()
    assert page["total"] == 0
    assert headers_a != headers_b
