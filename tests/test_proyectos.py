"""Proyectos: una dimensión analítica que no toca la contabilidad."""

from datetime import date
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
    nomina = next(
        c
        for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json()
        if c["name"] == "Nómina"
    )
    return headers, account, ventas, nomina


def _income(client, headers, account, category, amount, project_id=None):
    payload = {
        "date": date.today().isoformat(),
        "description": "Servicio",
        "amount": amount,
        "category_id": category["id"],
        "financial_account_id": account["id"],
        "status": "PAID",
    }
    if project_id:
        payload["project_id"] = project_id
    return client.post("/api/income", headers=headers, json=payload).json()


def _expense(client, headers, account, category, amount, project_id=None):
    payload = {
        "date": date.today().isoformat(),
        "description": "Costo",
        "amount": amount,
        "category_id": category["id"],
        "financial_account_id": account["id"],
        "status": "PAID",
    }
    if project_id:
        payload["project_id"] = project_id
    return client.post("/api/expenses", headers=headers, json=payload).json()


def test_profitability_is_revenue_minus_cost(client):
    headers, account, ventas, nomina = _setup(client)
    project = client.post(
        "/api/projects", headers=headers, json={"name": "ERP Fase 2", "budget": "200000"}
    ).json()

    _income(client, headers, account, ventas, "150000", project["id"])
    _expense(client, headers, account, nomina, "90000", project["id"])

    row = client.get("/api/projects", headers=headers).json()["items"][0]
    assert Decimal(str(row["revenue"])) == Decimal("150000")
    assert Decimal(str(row["cost"])) == Decimal("90000")
    assert Decimal(str(row["margin"])) == Decimal("60000")
    assert Decimal(str(row["margin_pct"])) == Decimal("40.0")


def test_vat_is_not_counted_as_revenue_or_cost(client):
    headers, account, ventas, _nomina = _setup(client)
    project = client.post("/api/projects", headers=headers, json={"name": "Con IVA"}).json()
    client.post(
        "/api/income",
        headers=headers,
        json={
            "date": date.today().isoformat(),
            "description": "Servicio con IVA",
            "amount": "116000",
            "tax_rate": "0.16",
            "category_id": ventas["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
            "project_id": project["id"],
        },
    )
    row = client.get("/api/projects", headers=headers).json()["items"][0]
    # El IVA no es tuyo: la rentabilidad se mide sobre el subtotal.
    assert Decimal(str(row["revenue"])) == Decimal("100000")


def test_operations_without_project_land_in_unassigned(client):
    headers, account, ventas, _nomina = _setup(client)
    client.post("/api/projects", headers=headers, json={"name": "Proyecto"})
    _income(client, headers, account, ventas, "50000")  # sin proyecto

    body = client.get("/api/projects", headers=headers).json()
    assert Decimal(str(body["items"][0]["revenue"])) == Decimal("0")
    assert Decimal(str(body["unassigned"]["revenue"])) == Decimal("50000")


def test_budget_usage_is_reported(client):
    headers, account, ventas, _nomina = _setup(client)
    project = client.post(
        "/api/projects", headers=headers, json={"name": "Con presupuesto", "budget": "100000"}
    ).json()
    _income(client, headers, account, ventas, "75000", project["id"])
    row = client.get("/api/projects", headers=headers).json()["items"][0]
    assert Decimal(str(row["budget_used_pct"])) == Decimal("75.0")


def test_projects_do_not_change_the_ledger(client):
    headers, account, ventas, _nomina = _setup(client)
    _income(client, headers, account, ventas, "50000")
    before = client.get("/api/accounting/trial-balance", headers=headers).json()

    project = client.post("/api/projects", headers=headers, json={"name": "Etiqueta"}).json()
    _income(client, headers, account, ventas, "50000", project["id"])
    after = client.get("/api/accounting/trial-balance", headers=headers).json()

    # Marcar un ingreso con proyecto no cambia a qué cuentas va.
    codes_before = {row["code"] for row in before["rows"]}
    codes_after = {row["code"] for row in after["rows"]}
    assert codes_before == codes_after
    assert Decimal(str(after["total_debit"])) == Decimal(str(after["total_credit"]))


def test_a_loss_making_project_shows_negative_margin(client):
    headers, account, ventas, nomina = _setup(client)
    project = client.post("/api/projects", headers=headers, json={"name": "El que perdió"}).json()
    _income(client, headers, account, ventas, "30000", project["id"])
    _expense(client, headers, account, nomina, "48000", project["id"])

    row = client.get("/api/projects", headers=headers).json()["items"][0]
    assert Decimal(str(row["margin"])) == Decimal("-18000")
    assert Decimal(str(row["margin_pct"])) == Decimal("-60.0")


def test_projects_are_isolated_by_organization(client):
    headers_a, _account, _ventas, _nomina = _setup(client)
    client.post("/api/projects", headers=headers_a, json={"name": "Mío"})
    headers_b, _a, _v, _n = _setup(client, email="otra@example.com")
    assert client.get("/api/projects", headers=headers_b).json()["items"] == []


def test_operations_can_be_filtered_and_searched(client):
    headers, account, ventas, _nomina = _setup(client)
    project = client.post("/api/projects", headers=headers, json={"name": "Filtrable"}).json()
    _income(client, headers, account, ventas, "10000", project["id"])
    _income(client, headers, account, ventas, "20000")

    by_project = client.get(
        f"/api/income?project_id={project['id']}", headers=headers
    ).json()
    assert by_project["total"] == 1
    assert Decimal(str(by_project["total_amount"])) == Decimal("10000")

    # La suma del pie acompaña al filtro, no a la página.
    by_text = client.get("/api/income?q=Servicio", headers=headers).json()
    assert by_text["total"] == 2
    assert Decimal(str(by_text["total_amount"])) == Decimal("30000")

    nothing = client.get("/api/income?q=inexistente", headers=headers).json()
    assert nothing["total"] == 0
