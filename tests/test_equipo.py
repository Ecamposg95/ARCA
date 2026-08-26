"""Equipo: cinco roles que por fin se pueden usar desde la aplicación."""

from tests.helpers import auth_headers, register


def _owner(client, email="dueno@example.com"):
    body = register(client, email=email)
    return auth_headers(body)


def _invite(client, headers, email="contador@example.com", role="ACCOUNTANT"):
    return client.post(
        "/api/organizations/current/members",
        headers=headers,
        json={"email": email, "name": "Contador", "role": role, "password": "supersegura123"},
    )


def test_the_owner_is_listed_from_the_start(client):
    headers = _owner(client)
    body = client.get("/api/organizations/current/members", headers=headers).json()
    assert body["total"] == 1
    assert body["items"][0]["role"] == "OWNER"
    assert body["items"][0]["is_you"] is True


def test_inviting_creates_the_account_and_the_membership(client):
    headers = _owner(client)
    response = _invite(client, headers)
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "ACCOUNTANT"

    listed = client.get("/api/organizations/current/members", headers=headers).json()
    assert listed["total"] == 2


def test_the_invited_person_can_log_in_and_sees_the_company(client):
    headers = _owner(client)
    _invite(client, headers)

    login = client.post(
        "/api/auth/login",
        json={"email": "contador@example.com", "password": "supersegura123"},
    )
    assert login.status_code == 200
    assert login.json()["organization"] is not None


def test_a_viewer_cannot_register_operations(client):
    headers = _owner(client)
    _invite(client, headers, email="mirona@example.com", role="VIEWER")
    login = client.post(
        "/api/auth/login", json={"email": "mirona@example.com", "password": "supersegura123"}
    ).json()
    viewer_headers = auth_headers(login)

    ventas = next(
        c
        for c in client.get("/api/categories?kind=INCOME", headers=viewer_headers).json()
        if c["name"] == "Ventas"
    )
    response = client.post(
        "/api/income",
        headers=viewer_headers,
        json={
            "date": "2026-08-01",
            "description": "Intento",
            "amount": "100",
            "category_id": ventas["id"],
        },
    )
    # Sólo mira: el rol existía en el modelo y ahora se puede asignar de verdad.
    assert response.status_code == 403


def test_cannot_invite_a_second_owner(client):
    headers = _owner(client)
    response = _invite(client, headers, email="otro@example.com", role="OWNER")
    assert response.status_code == 400
    assert "dueño" in response.json()["detail"]


def test_cannot_invite_the_same_person_twice(client):
    headers = _owner(client)
    _invite(client, headers)
    again = _invite(client, headers)
    assert again.status_code == 400
    assert "ya está" in again.json()["detail"]


def test_role_can_be_changed_and_membership_removed(client):
    headers = _owner(client)
    member = _invite(client, headers).json()

    updated = client.patch(
        f"/api/organizations/current/members/{member['id']}",
        headers=headers,
        json={"role": "VIEWER"},
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "VIEWER"

    removed = client.delete(
        f"/api/organizations/current/members/{member['id']}", headers=headers
    )
    assert removed.status_code == 204
    assert client.get("/api/organizations/current/members", headers=headers).json()["total"] == 1


def test_the_owner_cannot_be_removed(client):
    headers = _owner(client)
    owner = client.get("/api/organizations/current/members", headers=headers).json()["items"][0]
    response = client.delete(f"/api/organizations/current/members/{owner['id']}", headers=headers)
    assert response.status_code == 400


def test_a_member_cannot_invite_people(client):
    headers = _owner(client)
    _invite(client, headers, email="equipo@example.com", role="MEMBER")
    login = client.post(
        "/api/auth/login", json={"email": "equipo@example.com", "password": "supersegura123"}
    ).json()
    member_headers = auth_headers(login)

    response = _invite(client, member_headers, email="tercero@example.com")
    assert response.status_code == 403
