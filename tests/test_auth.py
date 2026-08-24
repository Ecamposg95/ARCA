from tests.helpers import auth_headers, register


def test_register_creates_full_onboarding_chain(client):
    body = register(client, initial_cash="5000")
    assert body["user"]["email"] == "dueno@example.com"
    assert body["organization"]["currency"] == "MXN"
    headers = auth_headers(body)

    # Cuenta "Caja" creada con saldo inicial
    accounts = client.get("/api/accounts", headers=headers).json()
    assert len(accounts) == 1
    assert accounts[0]["name"] == "Caja"
    assert accounts[0]["current_balance"] == "5000.00"

    # Categorías sembradas
    categories = client.get("/api/categories", headers=headers).json()
    kinds = {c["kind"] for c in categories}
    assert kinds == {"INCOME", "EXPENSE"}
    assert any(c["name"] == "Ventas" for c in categories)


def test_register_duplicate_email_rejected(client):
    register(client)
    response = client.post(
        "/api/auth/register",
        json={
            "email": "dueno@example.com",
            "password": "supersegura123",
            "name": "Otro",
            "business_name": "Otro Negocio",
        },
    )
    assert response.status_code == 400
    assert "correo" in response.json()["detail"].lower()


def test_login_and_me(client):
    register(client)
    login = client.post(
        "/api/auth/login",
        json={"email": "dueno@example.com", "password": "supersegura123"},
    )
    assert login.status_code == 200
    body = login.json()
    me = client.get("/api/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["memberships"][0]["role"] == "OWNER"


def test_login_wrong_password(client):
    register(client)
    response = client.post(
        "/api/auth/login",
        json={"email": "dueno@example.com", "password": "incorrecta123"},
    )
    assert response.status_code == 401


def test_refresh_token_flow(client):
    body = register(client)
    refreshed = client.post("/api/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]
    # Un access token NO sirve como refresh
    bad = client.post("/api/auth/refresh", json={"refresh_token": body["access_token"]})
    assert bad.status_code == 401


def test_org_header_of_foreign_org_rejected(client):
    body_a = register(client, email="a@example.com", business="Negocio A")
    body_b = register(client, email="b@example.com", business="Negocio B")
    response = client.get(
        "/api/accounts",
        headers={
            "Authorization": f"Bearer {body_a['access_token']}",
            "X-Organization-ID": body_b["organization"]["id"],
        },
    )
    assert response.status_code == 403
