"""El test más importante de ARCA: Org A jamás ve datos de Org B, ni con UUIDs conocidos."""

from tests.helpers import auth_headers, register


def _two_orgs(client):
    body_a = register(client, email="a@example.com", business="Negocio A", initial_cash="1000")
    body_b = register(client, email="b@example.com", business="Negocio B", initial_cash="2000")
    return auth_headers(body_a), auth_headers(body_b)


def test_cannot_read_foreign_financial_account(client):
    headers_a, headers_b = _two_orgs(client)
    account_b = client.get("/api/accounts", headers=headers_b).json()[0]
    response = client.get(f"/api/accounts/{account_b['id']}", headers=headers_a)
    assert response.status_code == 404


def test_cannot_pay_foreign_income(client):
    headers_a, headers_b = _two_orgs(client)
    account_b = client.get("/api/accounts", headers=headers_b).json()[0]
    ventas_b = client.get("/api/categories?kind=INCOME", headers=headers_b).json()[0]
    income_b = client.post(
        "/api/income",
        headers=headers_b,
        json={
            "date": "2026-08-10",
            "description": "Venta B",
            "amount": "500",
            "category_id": ventas_b["id"],
        },
    ).json()
    response = client.post(
        f"/api/income/{income_b['id']}/pay",
        headers=headers_a,
        json={"financial_account_id": account_b["id"]},
    )
    assert response.status_code == 404


def test_cannot_use_foreign_category(client):
    headers_a, headers_b = _two_orgs(client)
    ventas_b = client.get("/api/categories?kind=INCOME", headers=headers_b).json()[0]
    response = client.post(
        "/api/income",
        headers=headers_a,
        json={
            "date": "2026-08-10",
            "description": "cruce",
            "amount": "100",
            "category_id": ventas_b["id"],
        },
    )
    assert response.status_code == 400


def test_cannot_transfer_to_foreign_account(client):
    headers_a, headers_b = _two_orgs(client)
    account_a = client.get("/api/accounts", headers=headers_a).json()[0]
    account_b = client.get("/api/accounts", headers=headers_b).json()[0]
    response = client.post(
        "/api/transactions/transfer",
        headers=headers_a,
        json={
            "from_account_id": account_a["id"],
            "to_account_id": account_b["id"],
            "amount": "100",
            "date": "2026-08-06",
        },
    )
    assert response.status_code == 400


def test_lists_are_scoped(client):
    headers_a, headers_b = _two_orgs(client)
    client.post(
        "/api/customers",
        headers=headers_b,
        json={"name": "Cliente Secreto B"},
    )
    body = client.get("/api/customers", headers=headers_a).json()
    assert body["total"] == 0
    assert body["items"] == []
