"""Cuenta equivalente: cada cuenta de ARCA sabe cómo se llama en CONTPAQi."""

from tests.helpers import auth_headers, register


def _account(client, headers, code="1100") -> dict:
    return next(a for a in client.get("/api/accounting/accounts", headers=headers).json() if a["code"] == code)


def _patch(client, headers, account_id, value):
    return client.patch(
        f"/api/accounting/accounts/{account_id}", headers=headers, json={"contpaqi_code": value}
    )


def test_accounts_start_without_an_equivalent(client):
    headers = auth_headers(register(client))
    assert _account(client, headers)["contpaqi_code"] is None


def test_the_equivalent_is_stored_without_separators(client):
    headers = auth_headers(register(client))
    account = _account(client, headers)

    response = _patch(client, headers, account["id"], " 101-01-000 ")
    assert response.status_code == 200, response.text
    assert response.json()["contpaqi_code"] == "10101000"
    assert _account(client, headers)["contpaqi_code"] == "10101000"


def test_an_empty_value_clears_the_equivalent(client):
    headers = auth_headers(register(client))
    account = _account(client, headers)
    _patch(client, headers, account["id"], "10101000")

    assert _patch(client, headers, account["id"], "").json()["contpaqi_code"] is None


def test_invalid_codes_are_rejected(client):
    headers = auth_headers(register(client))
    account = _account(client, headers)

    assert _patch(client, headers, account["id"], "101/01*000").status_code == 400
    assert _patch(client, headers, account["id"], "1" * 31).status_code == 400
    assert _account(client, headers)["contpaqi_code"] is None


def test_another_company_cannot_touch_my_accounts(client):
    mine = auth_headers(register(client, email="yo@example.com", business="Mía"))
    theirs = auth_headers(register(client, email="otro@example.com", business="Ajena"))
    account = _account(client, mine)

    assert _patch(client, theirs, account["id"], "999").status_code == 404
    assert _account(client, mine)["contpaqi_code"] is None


def test_a_viewer_cannot_edit_the_catalog(client):
    owner = auth_headers(register(client))
    account = _account(client, owner)
    client.post(
        "/api/organizations/current/members",
        headers=owner,
        json={"email": "mira@example.com", "name": "Mira", "role": "VIEWER", "password": "supersegura123"},
    )
    viewer = auth_headers(
        client.post(
            "/api/auth/login", json={"email": "mira@example.com", "password": "supersegura123"}
        ).json()
    )
    assert _patch(client, viewer, account["id"], "999").status_code == 403
