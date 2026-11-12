"""Marca por empresa: la empresa puede llevar la identidad de su negocio
(acento y logotipo) sobre ONE Finance. El backend sólo guarda la clave; los
colores y el logo viven en el front."""

from tests.helpers import auth_headers, register


def test_la_empresa_nace_sin_marca(client):
    headers = auth_headers(register(client))
    assert client.get("/api/organizations/current", headers=headers).json()["brand"] is None
    assert client.get("/api/me", headers=headers).json()["organizations"][0]["brand"] is None


def test_el_dueno_pone_y_quita_la_marca(client):
    headers = auth_headers(register(client))
    patched = client.patch("/api/organizations/current", headers=headers, json={"brand": "lafe"})
    assert patched.status_code == 200
    assert patched.json()["brand"] == "lafe"
    assert client.get("/api/me", headers=headers).json()["organizations"][0]["brand"] == "lafe"

    cleared = client.patch("/api/organizations/current", headers=headers, json={"brand": None})
    assert cleared.status_code == 200
    assert cleared.json()["brand"] is None


def test_marca_desconocida_se_rechaza(client):
    headers = auth_headers(register(client))
    response = client.patch("/api/organizations/current", headers=headers, json={"brand": "otra"})
    assert response.status_code == 422
    assert client.get("/api/organizations/current", headers=headers).json()["brand"] is None


def test_solo_el_dueno_cambia_la_marca(client):
    headers = auth_headers(register(client))
    invited = client.post(
        "/api/organizations/current/members",
        headers=headers,
        json={"email": "admin@marca.mx", "name": "Admin", "role": "ADMIN", "password": "supersegura123"},
    )
    assert invited.status_code in (200, 201), invited.text
    login = client.post("/api/auth/login", json={"email": "admin@marca.mx", "password": "supersegura123"})
    admin_headers = {
        "Authorization": f"Bearer {login.json()['access_token']}",
        "X-Organization-ID": headers["X-Organization-ID"],
    }
    response = client.patch("/api/organizations/current", headers=admin_headers, json={"brand": "lafe"})
    assert response.status_code == 403
