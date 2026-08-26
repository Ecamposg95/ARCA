"""Tablas profesionales: orden por columna, búsqueda en cartera, lotes y deducibilidad."""

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


def _income(client, headers, account, ventas, amount, day, description="Venta"):
    return client.post(
        "/api/income",
        headers=headers,
        json={
            "date": f"2026-08-{day:02d}",
            "description": description,
            "amount": amount,
            "category_id": ventas["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    ).json()


# --- Orden por columna -------------------------------------------------------


def test_sort_by_amount_descending(client):
    headers, account, ventas, _renta = _setup(client)
    for amount, day in (("100", 1), ("300", 2), ("200", 3)):
        _income(client, headers, account, ventas, amount, day)

    body = client.get("/api/income?sort=-amount", headers=headers).json()
    amounts = [Decimal(str(item["amount"])) for item in body["items"]]
    assert amounts == sorted(amounts, reverse=True)

    body = client.get("/api/income?sort=amount", headers=headers).json()
    amounts = [Decimal(str(item["amount"])) for item in body["items"]]
    assert amounts == sorted(amounts)


def test_sort_by_date_ascending_overrides_default(client):
    headers, account, ventas, _renta = _setup(client)
    for amount, day in (("100", 20), ("100", 5), ("100", 12)):
        _income(client, headers, account, ventas, amount, day)

    body = client.get("/api/income?sort=date", headers=headers).json()
    dates = [item["date"] for item in body["items"]]
    assert dates == sorted(dates)


def test_sort_outside_the_whitelist_is_rejected(client):
    headers, _account, _ventas, _renta = _setup(client)
    # Un campo que existe en el modelo pero no está permitido: ordenarse por él
    # expondría detalles internos y permitiría sondear columnas.
    response = client.get("/api/income?sort=organization_id", headers=headers)
    assert response.status_code == 422
    assert "ordenar" in response.json()["detail"].lower()


def test_sort_applies_to_expenses_receivables_and_payables(client):
    headers, account, ventas, renta = _setup(client)
    customer = client.post("/api/customers", headers=headers, json={"name": "C"}).json()
    vendor = client.post("/api/vendors", headers=headers, json={"name": "V"}).json()
    today = date.today()

    for amount, days in (("1000", 30), ("3000", 10), ("2000", 20)):
        client.post(
            "/api/receivables",
            headers=headers,
            json={
                "customer_id": customer["id"],
                "description": "Factura",
                "amount": amount,
                "due_date": (today + timedelta(days=days)).isoformat(),
                "category_id": ventas["id"],
            },
        )
        client.post(
            "/api/payables",
            headers=headers,
            json={
                "vendor_id": vendor["id"],
                "description": "Compromiso",
                "amount": amount,
                "due_date": (today + timedelta(days=days)).isoformat(),
                "category_id": renta["id"],
            },
        )
        client.post(
            "/api/expenses",
            headers=headers,
            json={
                "date": today.isoformat(),
                "description": "Gasto",
                "amount": amount,
                "category_id": renta["id"],
                "financial_account_id": account["id"],
                "status": "PAID",
            },
        )

    for resource in ("expenses", "receivables", "payables"):
        body = client.get(f"/api/{resource}?sort=-amount", headers=headers).json()
        amounts = [Decimal(str(item["amount"])) for item in body["items"]]
        assert amounts == sorted(amounts, reverse=True), resource

    # due_date sólo existe en cartera; en gastos debe rechazarse.
    assert client.get("/api/receivables?sort=due_date", headers=headers).status_code == 200
    assert client.get("/api/expenses?sort=due_date", headers=headers).status_code == 422


# --- Búsqueda en cartera -----------------------------------------------------


def test_receivables_and_payables_search_by_description(client):
    headers, _account, ventas, renta = _setup(client)
    customer = client.post("/api/customers", headers=headers, json={"name": "C"}).json()
    vendor = client.post("/api/vendors", headers=headers, json={"name": "V"}).json()
    today = date.today()

    for description in ("Factura F-0075 mantenimiento", "Iguala mensual"):
        client.post(
            "/api/receivables",
            headers=headers,
            json={
                "customer_id": customer["id"],
                "description": description,
                "amount": "1000",
                "due_date": today.isoformat(),
                "category_id": ventas["id"],
            },
        )
        client.post(
            "/api/payables",
            headers=headers,
            json={
                "vendor_id": vendor["id"],
                "description": description,
                "amount": "1000",
                "due_date": today.isoformat(),
                "category_id": renta["id"],
            },
        )

    for resource in ("receivables", "payables"):
        body = client.get(f"/api/{resource}?q=mantenimiento", headers=headers).json()
        assert body["total"] == 1, resource
        assert "mantenimiento" in body["items"][0]["description"]


# --- Deducibilidad filtrable -------------------------------------------------


def test_only_non_deductible_filter(client):
    headers, _account, _ventas, renta = _setup(client)
    caja = client.post(
        "/api/accounts", headers=headers, json={"name": "Caja chica", "type": "CASH"}
    ).json()
    banco = client.post(
        "/api/accounts", headers=headers, json={"name": "Banco", "type": "BANK"}
    ).json()

    def gasto(account, amount):
        client.post(
            "/api/expenses",
            headers=headers,
            json={
                "date": date.today().isoformat(),
                "description": "Gasto",
                "amount": amount,
                "category_id": renta["id"],
                "financial_account_id": account["id"],
                "status": "PAID",
            },
        )

    gasto(caja, "5000")  # efectivo > 2000 → no deducible
    gasto(caja, "1500")  # efectivo chico → deducible
    gasto(banco, "9000")  # transferencia → deducible

    body = client.get("/api/expenses?non_deductible=true", headers=headers).json()
    assert body["total"] == 1
    assert Decimal(str(body["items"][0]["amount"])) == Decimal("5000")
    assert body["items"][0]["deductibility_warning"] is not None


# --- PATCH mínimo: asignar proyecto ------------------------------------------


def test_patch_assigns_project_to_income_and_expense(client):
    headers, account, ventas, renta = _setup(client)
    project = client.post("/api/projects", headers=headers, json={"name": "Etiqueta"}).json()
    income = _income(client, headers, account, ventas, "1000", 5)
    expense = client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": date.today().isoformat(),
            "description": "Gasto",
            "amount": "500",
            "category_id": renta["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    ).json()

    for resource, item in (("income", income), ("expenses", expense)):
        response = client.patch(
            f"/api/{resource}/{item['id']}",
            headers=headers,
            json={"project_id": project["id"]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["project_id"] == project["id"]

    # El proyecto acumula la operación (los montos son subtotales sin IVA).
    row = client.get("/api/projects", headers=headers).json()["items"][0]
    assert Decimal(str(row["revenue"])) == Decimal("1000")
    assert Decimal(str(row["cost"])) == Decimal("500")


def test_patch_can_clear_the_project(client):
    headers, account, ventas, _renta = _setup(client)
    project = client.post("/api/projects", headers=headers, json={"name": "P"}).json()
    income = _income(client, headers, account, ventas, "1000", 5)
    client.patch(
        f"/api/income/{income['id']}", headers=headers, json={"project_id": project["id"]}
    )
    response = client.patch(
        f"/api/income/{income['id']}", headers=headers, json={"project_id": None}
    )
    assert response.status_code == 200
    assert response.json()["project_id"] is None


def test_patch_rejects_a_project_from_another_company(client):
    headers_a, account_a, ventas_a, _renta = _setup(client)
    income = _income(client, headers_a, account_a, ventas_a, "1000", 5)

    headers_b = auth_headers(register(client, email="otra@example.com", initial_cash="1000"))
    foreign_project = client.post(
        "/api/projects", headers=headers_b, json={"name": "Ajeno"}
    ).json()

    response = client.patch(
        f"/api/income/{income['id']}",
        headers=headers_a,
        json={"project_id": foreign_project["id"]},
    )
    assert response.status_code == 400


def test_patch_is_tenant_isolated(client):
    headers_a, account_a, ventas_a, _renta = _setup(client)
    income = _income(client, headers_a, account_a, ventas_a, "1000", 5)

    headers_b = auth_headers(register(client, email="otra@example.com", initial_cash="1000"))
    project_b = client.post("/api/projects", headers=headers_b, json={"name": "B"}).json()

    # La empresa B no puede tocar operaciones de la empresa A.
    response = client.patch(
        f"/api/income/{income['id']}",
        headers=headers_b,
        json={"project_id": project_b["id"]},
    )
    assert response.status_code == 404
