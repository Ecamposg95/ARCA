"""Helpers compartidos de tests."""

from __future__ import annotations


def register(client, email="dueno@example.com", business="Mi Changarro", initial_cash=None, **extra):
    payload = {
        "email": email,
        "password": "supersegura123",
        "name": "Dueño",
        "business_name": business,
    }
    if initial_cash is not None:
        payload["initial_cash"] = initial_cash
    payload.update(extra)
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def auth_headers(auth_body: dict) -> dict:
    return {
        "Authorization": f"Bearer {auth_body['access_token']}",
        "X-Organization-ID": auth_body["organization"]["id"],
    }
