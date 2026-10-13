"""Apertura: los saldos con los que la empresa llega a ARCA, cuadrados contra capital."""

from datetime import date, timedelta
from decimal import Decimal

from tests.helpers import auth_headers, register

TODAY = date.today()
OPENING_DATE = date(TODAY.year - 1, 12, 31)


def _setup(client, email="contador@example.com"):
    body = register(client, email=email, initial_cash="50000")
    headers = auth_headers(body)
    accounts = client.get("/api/accounting/accounts", headers=headers).json()
    return headers, {account["code"]: account for account in accounts}


def _open(client, headers, lines, when=OPENING_DATE, balancing_code=None, description=None):
    payload = {"date": when.isoformat(), "description": description, "lines": lines}
    if balancing_code is not None:
        payload["balancing_code"] = balancing_code
    return client.post("/api/accounting/opening-balance", headers=headers, json=payload)


def _line(account, amount):
    return {"account_id": account["id"], "amount": amount}


def _by_code(entry, acc):
    """{código: (cargo, abono)} de las líneas de una póliza."""
    code_of = {account["id"]: code for code, account in acc.items()}
    return {
        code_of[line["account_id"]]: (Decimal(line["debit"]), Decimal(line["credit"])) for line in entry["lines"]
    }


def test_opening_posts_each_account_in_its_nature_and_balances_against_3200(client):
    headers, acc = _setup(client)
    response = _open(
        client,
        headers,
        [_line(acc["1191"], "1600.00"), _line(acc["2410"], "400.00"), _line(acc["3100"], "500.00")],
    )
    assert response.status_code == 201, response.text
    entry = response.json()
    assert entry["folio"].startswith(f"Dr-{OPENING_DATE.year}-12-")
    assert entry["kind"] == "DIARIO"
    assert entry["source_type"] == "opening"
    assert entry["date"] == OPENING_DATE.isoformat()
    assert entry["description"] == f"Saldos iniciales al 31/12/{OPENING_DATE.year}"
    assert _by_code(entry, acc) == {
        "1191": (Decimal("1600.00"), Decimal("0.00")),
        "2410": (Decimal("0.00"), Decimal("400.00")),
        "3100": (Decimal("0.00"), Decimal("500.00")),
        "3200": (Decimal("0.00"), Decimal("700.00")),
    }

    trial = client.get("/api/accounting/trial-balance", headers=headers).json()
    assert Decimal(str(trial["total_debit"])) == Decimal(str(trial["total_credit"]))
    sheet = client.get("/api/reports/balance-sheet", headers=headers).json()
    assert sheet["balanced"] is True
    assert Decimal(str(sheet["total_assets"])) == Decimal("51600")


def test_a_negative_residual_is_charged_to_3200(client):
    headers, acc = _setup(client)
    response = _open(client, headers, [_line(acc["1191"], "300"), _line(acc["2410"], "1000")])
    assert response.status_code == 201, response.text
    assert _by_code(response.json(), acc)["3200"] == (Decimal("700.00"), Decimal("0.00"))


def test_the_residual_can_go_to_capital(client):
    headers, acc = _setup(client)
    response = _open(
        client, headers, [_line(acc["1191"], "1000"), _line(acc["3200"], "250")], balancing_code="3100"
    )
    assert response.status_code == 201, response.text
    lines = _by_code(response.json(), acc)
    assert lines["3100"] == (Decimal("0.00"), Decimal("750.00"))
    assert lines["3200"] == (Decimal("0.00"), Decimal("250.00"))


def test_zero_lines_are_ignored_and_a_balanced_capture_needs_no_balancing_line(client):
    headers, acc = _setup(client)
    response = _open(
        client,
        headers,
        [_line(acc["1191"], "800"), _line(acc["2410"], "800"), _line(acc["1300"], "0")],
    )
    assert response.status_code == 201, response.text
    assert set(_by_code(response.json(), acc)) == {"1191", "2410"}


def test_an_opening_with_every_amount_in_zero_is_rejected(client):
    headers, acc = _setup(client)
    response = _open(client, headers, [_line(acc["1191"], "0"), _line(acc["2410"], "0.00")])
    assert response.status_code == 400
    assert "al menos una cuenta" in response.json()["detail"]
    assert client.get("/api/accounting/opening-balance", headers=headers).json()["entry"] is None


def test_rejections(client):
    headers, acc = _setup(client)
    cases = [
        ([_line(acc["4100"], "100")], None, "sólo lleva cuentas de balance"),
        ([_line(acc["1100"], "100")], None, "abre desde su módulo"),
        ([_line(acc["2300"], "100")], None, "Patrimonio"),
        ([_line(acc["1000"], "100")], None, "cuenta mayor"),
        ([_line(acc["1191"], "100"), _line(acc["3200"], "100")], None, "es la de cuadre"),
        ([_line(acc["1191"], "100"), _line(acc["3100"], "100")], "3100", "es la de cuadre"),
        ([_line(acc["1191"], "100"), _line(acc["1191"], "50")], None, "aparece dos veces"),
    ]
    for lines, balancing_code, message in cases:
        response = _open(client, headers, lines, balancing_code=balancing_code)
        assert response.status_code == 400, (message, response.text)
        assert message in response.json()["detail"]


def test_bad_payloads_are_rejected_by_the_schema(client):
    headers, acc = _setup(client)
    assert _open(client, headers, [_line(acc["1191"], "-1")]).status_code == 422
    assert _open(client, headers, [_line(acc["1191"], "10.005")]).status_code == 422
    assert _open(client, headers, []).status_code == 422
    assert _open(client, headers, [_line(acc["1191"], "10")], balancing_code="3300").status_code == 422


def test_future_date_is_rejected(client):
    headers, acc = _setup(client)
    response = _open(client, headers, [_line(acc["1191"], "100")], when=TODAY + timedelta(days=1))
    assert response.status_code == 400
    assert "futura" in response.json()["detail"]


def test_closed_month_is_rejected(client):
    headers, acc = _setup(client)
    end = TODAY.replace(day=1) - timedelta(days=1)
    assert (
        client.post("/api/periods/close", headers=headers, json={"year": end.year, "month": end.month}).status_code
        == 200
    )
    response = _open(client, headers, [_line(acc["1191"], "100")], when=end)
    assert response.status_code == 400
    assert "cerrado" in response.json()["detail"]


def test_only_one_live_opening(client):
    headers, acc = _setup(client)
    first = _open(client, headers, [_line(acc["1191"], "100")])
    assert first.status_code == 201
    second = _open(client, headers, [_line(acc["1191"], "200")])
    assert second.status_code == 400
    assert second.json()["detail"] == (
        f"Ya existe una póliza de apertura ({first.json()['folio']}). Reviértela desde el diario para capturar otra."
    )


def test_other_company_account_is_not_found(client):
    headers, _acc = _setup(client)
    _other_headers, other_acc = _setup(client, email="otra@example.com")
    assert _open(client, headers, [_line(other_acc["1191"], "100")]).status_code == 404


def test_reversing_the_opening_frees_the_slot(client):
    headers, acc = _setup(client)
    first = _open(client, headers, [_line(acc["1191"], "100")]).json()
    current = client.get("/api/accounting/opening-balance", headers=headers).json()
    assert current["entry"]["id"] == first["id"]
    assert current["balancing_codes"] == ["3200", "3100"]

    reversal = client.post(
        f"/api/accounting/journal-entries/{first['id']}/reverse",
        headers=headers,
        json={"date": TODAY.isoformat(), "description": None},
    )
    assert reversal.status_code == 201, reversal.text
    assert reversal.json()["reversal_of"] == first["id"]
    assert client.get("/api/accounting/opening-balance", headers=headers).json()["entry"] is None

    again = _open(client, headers, [_line(acc["1191"], "150")])
    assert again.status_code == 201, again.text
    assert client.get("/api/accounting/opening-balance", headers=headers).json()["entry"]["id"] == again.json()["id"]
    # El reverso de una apertura no se revierte.
    twice = client.post(
        f"/api/accounting/journal-entries/{reversal.json()['id']}/reverse",
        headers=headers,
        json={"date": TODAY.isoformat()},
    )
    assert twice.status_code == 400


def test_openings_are_isolated_by_company(client):
    headers_a, acc_a = _setup(client)
    headers_b, _acc_b = _setup(client, email="otra@example.com")
    assert _open(client, headers_a, [_line(acc_a["1191"], "100")]).status_code == 201
    assert client.get("/api/accounting/opening-balance", headers=headers_b).json()["entry"] is None


def test_an_opening_dated_inside_a_closed_year_is_rejected(client):
    headers, acc = _setup(client)
    assert (
        client.post(f"/api/periods/years/{OPENING_DATE.year}/close", headers=headers, json={}).status_code == 200
    )
    response = _open(client, headers, [_line(acc["1191"], "100")], when=OPENING_DATE)
    assert response.status_code == 400
    assert "ejercicio" in response.json()["detail"]
