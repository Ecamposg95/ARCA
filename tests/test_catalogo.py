"""Catálogo editable: cuentas de detalle bajo una mayor, dos niveles, sin borrar nada."""

from datetime import date
from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client, email="contador@example.com"):
    body = register(client, email=email, initial_cash="50000")
    headers = auth_headers(body)
    accounts = client.get("/api/accounting/accounts", headers=headers).json()
    return headers, {account["code"]: account for account in accounts}


def _create(client, headers, parent, code="5210", name="Cuotas patronales", **extra):
    return client.post(
        "/api/accounting/accounts",
        headers=headers,
        json={"parent_id": parent["id"], "code": code, "name": name, **extra},
    )


def _manual(client, headers, debit_account, credit_account, amount="100"):
    return client.post(
        "/api/accounting/journal-entries",
        headers=headers,
        json={
            "date": date.today().isoformat(),
            "description": "Ajuste",
            "lines": [
                {"account_id": debit_account["id"], "debit": amount, "credit": "0"},
                {"account_id": credit_account["id"], "debit": "0", "credit": amount},
            ],
        },
    )


def test_create_detail_account_inherits_type_and_sat_code(client):
    headers, acc = _setup(client)
    response = _create(client, headers, acc["5000"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["type"] == "EXPENSE"
    assert body["parent_id"] == acc["5000"]["id"]
    assert body["active"] is True
    assert body["has_movements"] is False
    assert body["manual_allowed"] is True
    assert body["sat_code"] == acc["5000"]["sat_code"]
    listed = client.get("/api/accounting/accounts", headers=headers).json()
    assert any(item["code"] == "5210" for item in listed)


def test_manual_allowed_flags_controlled_and_major_accounts(client):
    headers, acc = _setup(client)
    for code in ("1100", "1400", "2300", "5000"):
        assert acc[code]["manual_allowed"] is False, code
    assert acc["5200"]["manual_allowed"] is True
    new = _create(client, headers, acc["5000"]).json()
    off = client.patch(f"/api/accounting/accounts/{new['id']}", headers=headers, json={"active": False})
    assert off.json()["manual_allowed"] is False


def test_create_with_explicit_sat_and_contpaqi_codes(client):
    headers, acc = _setup(client)
    response = _create(client, headers, acc["5000"], sat_code="601.01", contpaqi_code="5210-000-000")
    assert response.status_code == 201, response.text
    assert response.json()["sat_code"] == "601.01"
    assert response.json()["contpaqi_code"] == "5210000000"
    bad = _create(client, headers, acc["5000"], code="5211", sat_code="999.99")
    assert bad.status_code == 400


def test_code_rules(client):
    headers, acc = _setup(client)
    assert _create(client, headers, acc["5000"], code="5200").status_code == 400  # duplicado
    assert _create(client, headers, acc["5000"], code="52A0").status_code == 400  # letras
    assert _create(client, headers, acc["5000"], code="520").status_code == 422  # corto (schema)
    assert _create(client, headers, acc["5000"], code="4210").status_code == 400  # dígito del padre
    assert _create(client, headers, acc["5000"], code=" 05210 ").status_code == 400  # ceros a la izquierda
    assert _create(client, headers, acc["5000"], code="5210000000").status_code == 201  # 10 dígitos


def test_parent_must_be_a_major_account_of_this_company(client):
    headers, acc = _setup(client)
    assert _create(client, headers, acc["5200"]).status_code == 400
    other_headers, other_acc = _setup(client, email="otra@example.com")
    assert _create(client, headers, other_acc["5000"]).status_code == 404


def test_rename_any_account(client):
    headers, acc = _setup(client)
    response = client.patch(
        f"/api/accounting/accounts/{acc['5400']['id']}", headers=headers, json={"name": "Sistemas y licencias"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Sistemas y licencias"
    blank = client.patch(f"/api/accounting/accounts/{acc['5400']['id']}", headers=headers, json={"name": "   "})
    assert blank.status_code == 400


def test_other_company_cannot_rename_or_deactivate(client):
    headers, acc = _setup(client)
    new = _create(client, headers, acc["5000"]).json()
    other_headers, _ = _setup(client, email="otra@example.com")
    for payload in ({"name": "x"}, {"active": False}):
        response = client.patch(f"/api/accounting/accounts/{new['id']}", headers=other_headers, json=payload)
        assert response.status_code == 404, payload
        assert response.json()["detail"] == "Esa cuenta no existe."
    listed = client.get("/api/accounting/accounts", headers=headers).json()
    mine = next(item for item in listed if item["id"] == new["id"])
    assert mine["name"] == "Cuotas patronales"
    assert mine["active"] is True


def test_deactivate_rules(client):
    headers, acc = _setup(client)
    seeded = client.patch(f"/api/accounting/accounts/{acc['5400']['id']}", headers=headers, json={"active": False})
    assert seeded.status_code == 400
    assert "sembró" in seeded.json()["detail"]

    new = _create(client, headers, acc["5000"]).json()
    off = client.patch(f"/api/accounting/accounts/{new['id']}", headers=headers, json={"active": False})
    assert off.status_code == 200
    assert off.json()["active"] is False
    rejected = _manual(client, headers, new, acc["3100"])
    assert rejected.status_code == 400
    assert "inactiva" in rejected.json()["detail"]

    on = client.patch(f"/api/accounting/accounts/{new['id']}", headers=headers, json={"active": True})
    assert on.status_code == 200
    assert _manual(client, headers, new, acc["3100"]).status_code == 201

    with_moves = client.patch(f"/api/accounting/accounts/{new['id']}", headers=headers, json={"active": False})
    assert with_moves.status_code == 400
    assert "movimientos" in with_moves.json()["detail"]
    listed = client.get("/api/accounting/accounts", headers=headers).json()
    assert next(item for item in listed if item["id"] == new["id"])["has_movements"] is True


def test_new_account_reaches_balance_sat_and_contpaqi(client):
    headers, acc = _setup(client)
    new = _create(client, headers, acc["5000"], contpaqi_code="5210000").json()
    assert _manual(client, headers, new, acc["3100"]).status_code == 201
    today = date.today()

    balance = client.get("/api/accounting/trial-balance", headers=headers).json()
    assert any(row["code"] == "5210" and Decimal(str(row["debit"])) == Decimal("100") for row in balance["rows"])

    assert client.patch("/api/organizations/current", headers=headers, json={"tax_id": "DCV150604MN2"}).status_code == 200
    catalog = client.get(
        "/api/accounting/sat/catalogo", headers=headers, params={"year": today.year, "month": today.month}
    )
    assert catalog.status_code == 200, catalog.text
    assert 'NumCta="5210"' in catalog.text

    export = client.get("/api/accounting/contpaqi", headers=headers, params={"year": today.year, "month": today.month})
    assert export.status_code == 200, export.text
    assert "5210000" in export.text
