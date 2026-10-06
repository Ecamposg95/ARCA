"""Código agrupador: cada cuenta de ARCA sabe cómo la clasifica el SAT."""

from tests.helpers import auth_headers, register


def _accounts(client, headers) -> dict[str, dict]:
    return {a["code"]: a for a in client.get("/api/accounting/accounts", headers=headers).json()}


def _patch(client, headers, account_id, **body):
    return client.patch(f"/api/accounting/accounts/{account_id}", headers=headers, json=body)


def test_a_new_company_is_born_with_every_account_classified(client):
    headers = auth_headers(register(client))
    accounts = _accounts(client, headers)
    assert all(account["sat_code"] for account in accounts.values()), [
        a["code"] for a in accounts.values() if not a["sat_code"]
    ]
    assert accounts["1100"]["sat_code"] == "102.01"
    assert accounts["1490"]["sat_code"] == "171.08"
    assert accounts["4000"]["sat_code"] == "400"


def test_the_official_list_is_served_for_the_selector(client):
    headers = auth_headers(register(client))
    codes = client.get("/api/accounting/sat/codes", headers=headers).json()
    assert len(codes) == 1080
    assert {"code": "102.01", "name": "Bancos nacionales"} in codes


def test_the_code_can_be_changed_to_another_official_one(client):
    headers = auth_headers(register(client))
    renta = _accounts(client, headers)["5300"]
    response = _patch(client, headers, renta["id"], sat_code=" 601.45 ")
    assert response.status_code == 200, response.text
    assert response.json()["sat_code"] == "601.45"


def test_an_unofficial_code_is_rejected(client):
    headers = auth_headers(register(client))
    renta = _accounts(client, headers)["5300"]
    response = _patch(client, headers, renta["id"], sat_code="999.99")
    assert response.status_code == 400
    assert "SAT" in response.json()["detail"]
    assert _accounts(client, headers)["5300"]["sat_code"] == "601.46"


def test_an_empty_code_clears_it(client):
    headers = auth_headers(register(client))
    renta = _accounts(client, headers)["5300"]
    assert _patch(client, headers, renta["id"], sat_code="").json()["sat_code"] is None


def test_each_field_is_updated_only_when_sent(client):
    headers = auth_headers(register(client))
    renta = _accounts(client, headers)["5300"]
    _patch(client, headers, renta["id"], contpaqi_code="601-01")

    after_sat = _patch(client, headers, renta["id"], sat_code="601.45").json()
    assert (after_sat["contpaqi_code"], after_sat["sat_code"]) == ("60101", "601.45")

    after_empty = _patch(client, headers, renta["id"]).json()
    assert (after_empty["contpaqi_code"], after_empty["sat_code"]) == ("60101", "601.45")
