"""Apertura: los saldos con los que la empresa llega a ONE Finance, cuadrados contra capital."""

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
    assert current["balancing_codes"] == ["3200", "3100", "3901"]

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


def test_reversing_an_opening_is_dated_at_the_opening(client):
    headers, acc = _setup(client)
    first = _open(client, headers, [_line(acc["1191"], "100")]).json()

    reversal = client.post(
        f"/api/accounting/journal-entries/{first['id']}/reverse",
        headers=headers,
        json={"date": TODAY.isoformat()},
    )
    assert reversal.status_code == 201, reversal.text
    assert reversal.json()["date"] == OPENING_DATE.isoformat()

    assert _open(client, headers, [_line(acc["1191"], "150")]).status_code == 201
    as_of = date(TODAY.year, 1, 31)
    trial = client.get("/api/accounting/trial-balance", headers=headers, params={"as_of": as_of.isoformat()}).json()
    balances = {row["code"]: Decimal(str(row["balance"])) for row in trial["rows"]}
    assert balances["1191"] == Decimal("150.00")
    sheet = client.get("/api/reports/balance-sheet", headers=headers, params={"as_of": as_of.isoformat()}).json()
    assert sheet["balanced"] is True


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


# --- Apertura provisional y ajustable a la fecha de corte ---

CUTOFF = TODAY.replace(day=1)  # siempre hoy o antes: una póliza no lleva fecha futura


def _company(client, email="lafe@example.com", cutoff=CUTOFF):
    headers = auth_headers(register(client, email=email, business="La Fe"))
    if cutoff is not None:
        response = client.patch("/api/opening", headers=headers, json={"opening_date": cutoff.isoformat()})
        assert response.status_code == 200, response.text
    return headers


def _money_account(client, headers, name="Santander PyME", kind="BANK", opening="0"):
    response = client.post(
        "/api/accounts", headers=headers, json={"name": name, "type": kind, "opening_balance": opening}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _adjust(client, headers, account_id, target, reason="Estado de cuenta oct", **extra):
    payload = {"target_opening_balance": target, "reason": reason, **extra}
    return client.post(f"/api/accounts/{account_id}/opening-adjustment", headers=headers, json=payload)


def _entries(client, headers, source_type):
    response = client.get(f"/api/accounting/journal-entries?source_type={source_type}&limit=200", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _all_entries(client, headers):
    return client.get("/api/accounting/journal-entries?limit=200", headers=headers).json()["total"]


def _codes(client, headers):
    return {a["id"]: a["code"] for a in client.get("/api/accounting/accounts", headers=headers).json()}


def _lines_by_code(client, headers, entry):
    code_of = _codes(client, headers)
    return {
        code_of[line["account_id"]]: (Decimal(line["debit"]), Decimal(line["credit"])) for line in entry["lines"]
    }


def _movements(client, headers, account_id):
    return client.get(f"/api/transactions?account_id={account_id}", headers=headers).json()["items"]


def _bridge(client, headers):
    return Decimal(client.get("/api/opening", headers=headers).json()["bridge_balance"])


def _assert_balanced(client, headers):
    trial = client.get("/api/accounting/trial-balance", headers=headers).json()
    assert Decimal(str(trial["total_debit"])) == Decimal(str(trial["total_credit"]))


def _member(client, owner, email, role):
    response = client.post(
        "/api/organizations/current/members",
        headers=owner,
        json={"email": email, "name": role, "role": role, "password": "supersegura123"},
    )
    assert response.status_code == 201, response.text
    login = client.post("/api/auth/login", json={"email": email, "password": "supersegura123"})
    return auth_headers(login.json())


def test_new_companies_get_the_bridge_account_3901(client):
    headers = _company(client, cutoff=None)
    accounts = {a["code"]: a for a in client.get("/api/accounting/accounts", headers=headers).json()}
    bridge = accounts["3901"]
    assert bridge["name"] == "Saldos de apertura por identificar"
    assert bridge["type"] == "EQUITY"
    assert bridge["sat_code"] == "306.01"


def test_setting_the_cutoff_defaults_to_provisional(client):
    headers = _company(client)
    summary = client.get("/api/opening", headers=headers).json()
    assert summary["opening_date"] == CUTOFF.isoformat()
    assert summary["opening_status"] == "PROVISIONAL"
    assert Decimal(summary["bridge_balance"]) == 0

    confirmed = client.patch("/api/opening", headers=headers, json={"opening_status": "CONFIRMED"})
    assert confirmed.status_code == 200
    assert confirmed.json()["opening_status"] == "CONFIRMED"

    future = (TODAY + timedelta(days=3)).isoformat()
    assert client.patch("/api/opening", headers=headers, json={"opening_date": future}).status_code == 400


def test_bank_adjustment_is_dated_at_cutoff_and_moves_current_balance_by_the_difference(client):
    headers = _company(client)
    bank = _money_account(client, headers, opening="1000")
    # Una operación registrada después del corte queda como está.
    categories = client.get("/api/categories?kind=INCOME", headers=headers).json()
    category_id = (categories["items"] if isinstance(categories, dict) else categories)[0]["id"]
    sale = client.post(
        "/api/income",
        headers=headers,
        json={
            "date": TODAY.isoformat(),
            "description": "Venta",
            "amount": "500",
            "category_id": category_id,
            "financial_account_id": bank["id"],
            "status": "PAID",
        },
    )
    assert sale.status_code == 201, sale.text

    response = _adjust(client, headers, bank["id"], "1500.00", status="CONFIRMED", note="Estado de cuenta oct-2026")
    assert response.status_code == 200, response.text
    body = response.json()
    assert Decimal(body["opening_balance"]) == Decimal("1500.00")
    assert Decimal(body["current_balance"]) == Decimal("2000.00")  # 1000 + 500 de la venta + 500 de ajuste
    assert body["opening_status"] == "CONFIRMED"
    assert body["opening_note"] == "Estado de cuenta oct-2026"

    adjustment = next(m for m in _movements(client, headers, bank["id"]) if m["source_type"] == "opening_adjustment")
    assert adjustment["transaction_type"] == "ADJUSTMENT_IN"
    assert adjustment["date"] == CUTOFF.isoformat()
    assert Decimal(adjustment["amount"]) == Decimal("500.00")

    [entry] = _entries(client, headers, "opening_adjustment")
    assert entry["date"] == CUTOFF.isoformat()
    assert _lines_by_code(client, headers, entry) == {
        "1100": (Decimal("500.00"), Decimal("0.00")),
        "3901": (Decimal("0.00"), Decimal("500.00")),
    }
    assert _bridge(client, headers) == Decimal("500.00")
    _assert_balanced(client, headers)


def test_two_adjustments_end_on_the_last_target(client):
    headers = _company(client)
    bank = _money_account(client, headers)
    assert _adjust(client, headers, bank["id"], "800").status_code == 200
    body = _adjust(client, headers, bank["id"], "300", reason="Estado de cuenta corregido").json()
    assert Decimal(body["opening_balance"]) == Decimal("300.00")
    assert Decimal(body["current_balance"]) == Decimal("300.00")
    kinds = sorted((m["transaction_type"], m["amount"]) for m in _movements(client, headers, bank["id"]))
    assert kinds == [("ADJUSTMENT", "500.00"), ("ADJUSTMENT_IN", "800.00")]
    assert _bridge(client, headers) == Decimal("300.00")
    _assert_balanced(client, headers)

    # La misma cifra otra vez: sin diferencia no se asienta nada.
    assert _adjust(client, headers, bank["id"], "300", reason="Estado de cuenta corregido").status_code == 200
    assert len(_entries(client, headers, "opening_adjustment")) == 2


def test_card_adjustment_respects_the_liability_nature(client):
    headers = _company(client)
    card = _money_account(client, headers, name="AMEX", kind="CREDIT_CARD")
    body = _adjust(client, headers, card["id"], "2500").json()
    assert Decimal(body["current_balance"]) == Decimal("2500.00")  # lo que se debe
    [entry] = _entries(client, headers, "opening_adjustment")
    assert _lines_by_code(client, headers, entry) == {
        "3901": (Decimal("2500.00"), Decimal("0.00")),
        "2200": (Decimal("0.00"), Decimal("2500.00")),
    }
    [movement] = _movements(client, headers, card["id"])
    assert movement["transaction_type"] == "ADJUSTMENT"  # más deuda

    # Bajar la deuda: Cargo 2200 / Abono 3901, movimiento de entrada.
    body = _adjust(client, headers, card["id"], "1000", reason="Estado de cuenta AMEX").json()
    assert Decimal(body["current_balance"]) == Decimal("1000.00")
    assert _bridge(client, headers) == Decimal("-1000.00")
    _assert_balanced(client, headers)


def test_the_reason_is_required(client):
    headers = _company(client)
    bank = _money_account(client, headers)
    assert _adjust(client, headers, bank["id"], "100", reason="").status_code == 422
    assert _adjust(client, headers, bank["id"], "100", reason="ok").status_code == 422
    assert _adjust(client, headers, bank["id"], "-5").status_code == 422
    assert client.put("/api/accounting/opening-balance", headers=headers, json={"lines": []}).status_code == 422


def test_without_a_cutoff_the_adjustment_is_rejected(client):
    headers = _company(client, cutoff=None)
    bank = _money_account(client, headers)
    response = _adjust(client, headers, bank["id"], "100")
    assert response.status_code == 400
    assert "fecha de corte" in response.json()["detail"]
    put = client.put("/api/accounting/opening-balance", headers=headers, json={"reason": "Sin corte aún", "lines": []})
    assert put.status_code == 400
    assert "fecha de corte" in put.json()["detail"]


def test_a_closed_cutoff_month_is_rejected(client):
    previous = (TODAY.replace(day=1) - timedelta(days=1)).replace(day=1)
    headers = _company(client, cutoff=previous)
    bank = _money_account(client, headers)
    closed = client.post("/api/periods/close", headers=headers, json={"year": previous.year, "month": previous.month})
    assert closed.status_code == 200, closed.text
    response = _adjust(client, headers, bank["id"], "100")
    assert response.status_code == 400
    assert "cerrado" in response.json()["detail"] and "Reábrelo" in response.json()["detail"]
    assert Decimal(client.get(f"/api/accounts/{bank['id']}", headers=headers).json()["current_balance"]) == 0

    # Tampoco se fija un corte dentro de un mes cerrado.
    other = _company(client, email="otra@example.com", cutoff=None)
    client.post("/api/periods/close", headers=other, json={"year": previous.year, "month": previous.month})
    response = client.patch("/api/opening", headers=other, json={"opening_date": previous.isoformat()})
    assert response.status_code == 400
    assert "cerrado" in response.json()["detail"]


def test_put_reverses_and_recreates_the_non_module_opening(client):
    headers = _company(client)
    acc = {a["code"]: a for a in client.get("/api/accounting/accounts", headers=headers).json()}
    first = client.put(
        "/api/accounting/opening-balance",
        headers=headers,
        json={"reason": "Depósito en garantía", "lines": [_line(acc["1300"], "4000")]},
    )
    assert first.status_code == 200, first.text
    first_entry = first.json()["entry"]
    assert first_entry["date"] == CUTOFF.isoformat()
    assert _by_code(first_entry, acc)["3901"] == (Decimal("0.00"), Decimal("4000.00"))

    lines = [_line(acc["1300"], "4500"), _line(acc["2410"], "300")]
    second = client.put(
        "/api/accounting/opening-balance", headers=headers, json={"reason": "Contrato de arrendamiento", "lines": lines}
    )
    assert second.status_code == 200, second.text
    entry = second.json()["entry"]
    assert entry["id"] != first_entry["id"]
    assert _by_code(entry, acc) == {
        "1300": (Decimal("4500.00"), Decimal("0.00")),
        "2410": (Decimal("0.00"), Decimal("300.00")),
        "3901": (Decimal("0.00"), Decimal("4200.00")),
    }
    assert client.get("/api/accounting/opening-balance", headers=headers).json()["entry"]["id"] == entry["id"]
    reversals = [e for e in _entries(client, headers, "opening") if (e["reference"] or "").startswith("reversal:")]
    assert [r["reference"] for r in reversals] == [f"reversal:{first_entry['id']}"]
    assert reversals[0]["date"] == CUTOFF.isoformat()

    summary = client.get("/api/opening", headers=headers).json()
    assert {row["code"]: row["amount"] for row in summary["others"]} == {"1300": "4500.00", "2410": "300.00"}
    assert summary["other_balancing_code"] == "3901"
    assert Decimal(summary["bridge_balance"]) == Decimal("4200.00")
    _assert_balanced(client, headers)

    # Sin cambios: no se revierte nada.
    again = client.put(
        "/api/accounting/opening-balance", headers=headers, json={"reason": "Contrato de arrendamiento", "lines": lines}
    )
    assert again.json()["entry"]["id"] == entry["id"]

    # Todo en cero: sólo el reverso.
    cleared = client.put("/api/accounting/opening-balance", headers=headers, json={"reason": "Ya no aplica", "lines": []})
    assert cleared.status_code == 200 and cleared.json()["entry"] is None
    assert client.get("/api/accounting/opening-balance", headers=headers).json()["entry"] is None
    assert _bridge(client, headers) == 0
    _assert_balanced(client, headers)


def test_post_opening_uses_the_cutoff_date_and_never_captures_the_bridge(client):
    headers = _company(client)
    acc = {a["code"]: a for a in client.get("/api/accounting/accounts", headers=headers).json()}
    other_day = CUTOFF - timedelta(days=1)
    assert _open(client, headers, [_line(acc["1300"], "10")], when=other_day).status_code == 400
    assert _open(client, headers, [_line(acc["3901"], "10")], when=CUTOFF).status_code == 400
    created = _open(client, headers, [_line(acc["1300"], "10")], when=CUTOFF, balancing_code="3901")
    assert created.status_code == 201, created.text


def test_change_log_keeps_old_and_new(client):
    headers = _company(client)
    bank = _money_account(client, headers)
    _adjust(client, headers, bank["id"], "700", status="PROVISIONAL", note="Pendiente")
    _adjust(
        client, headers, bank["id"], "900", reason="Llegó el estado de cuenta", status="CONFIRMED", note="Edo. cta. oct-2026"
    )
    latest = client.get(f"/api/accounts/{bank['id']}/history", headers=headers).json()["items"][0]
    assert latest["reason"] == "Llegó el estado de cuenta"
    changes = {c["field"]: (c["old"], c["new"]) for c in latest["changes"]}
    assert changes["opening_balance"] == ("700.00", "900.00")
    assert changes["opening_status"] == ("PROVISIONAL", "CONFIRMED")
    assert changes["opening_note"] == ("Pendiente", "Edo. cta. oct-2026")

    acc = {a["code"]: a for a in client.get("/api/accounting/accounts", headers=headers).json()}
    client.put(
        "/api/accounting/opening-balance",
        headers=headers,
        json={"reason": "Anticipo a proveedor", "lines": [_line(acc["1300"], "50")]},
    )
    org_id = client.get("/api/opening", headers=headers).json()["organization_id"]
    events = client.get(f"/api/opening/{org_id}/history", headers=headers).json()["items"]
    assert events[0]["reason"] == "Anticipo a proveedor"
    [line_change] = [c for c in events[0]["changes"] if c["field"].startswith("line:1300")]
    assert (line_change["old"], line_change["new"], line_change["kind"]) == (None, "50.00", "money")
    assert any(c["field"] == "opening_date" for event in events for c in event["changes"])


def test_opening_is_isolated_by_company(client):
    headers_a = _company(client, email="a@example.com")
    bank_a = _money_account(client, headers_a)
    headers_b = _company(client, email="b@example.com")
    assert _adjust(client, headers_b, bank_a["id"], "100").status_code == 404
    assert _adjust(client, headers_a, bank_a["id"], "100").status_code == 200
    summary_b = client.get("/api/opening", headers=headers_b).json()
    assert Decimal(summary_b["bridge_balance"]) == 0
    assert all(row["id"] != bank_a["id"] for row in summary_b["accounts"])
    acc_a = {a["code"]: a for a in client.get("/api/accounting/accounts", headers=headers_a).json()}
    stolen = client.put(
        "/api/accounting/opening-balance",
        headers=headers_b,
        json={"reason": "Cuenta ajena", "lines": [_line(acc_a["1300"], "10")]},
    )
    assert stolen.status_code == 404


def test_members_and_viewers_cannot_touch_the_opening(client):
    headers = _company(client)
    bank = _money_account(client, headers)
    for email, role in (("aux@example.com", "MEMBER"), ("mira@example.com", "VIEWER")):
        other = _member(client, headers, email, role)
        assert _adjust(client, other, bank["id"], "100").status_code == 403
        assert client.get("/api/opening", headers=other).status_code == 403
        assert client.patch("/api/opening", headers=other, json={"opening_status": "CONFIRMED"}).status_code == 403
        put = client.put("/api/accounting/opening-balance", headers=other, json={"reason": "No debería", "lines": []})
        assert put.status_code == 403
    # El contador ajusta; la fecha de corte la fija quien administra.
    accountant = _member(client, headers, "conta@example.com", "ACCOUNTANT")
    assert _adjust(client, accountant, bank["id"], "100").status_code == 200
    assert client.patch("/api/opening", headers=accountant, json={"opening_status": "CONFIRMED"}).status_code == 403


def test_the_cutoff_cannot_move_once_there_are_openings(client):
    headers = _company(client)
    bank = _money_account(client, headers)
    _adjust(client, headers, bank["id"], "100")
    earlier = (CUTOFF - timedelta(days=1)).isoformat()
    assert client.patch("/api/opening", headers=headers, json={"opening_date": earlier}).status_code == 400


def test_cash_flow_counts_the_adjusted_opening_once(client):
    headers = _company(client)
    bank = _money_account(client, headers, opening="1000")
    _adjust(client, headers, bank["id"], "1500")
    report = client.get(
        f"/api/reports/cash-flow?start={CUTOFF.isoformat()}&end={TODAY.isoformat()}", headers=headers
    ).json()
    assert Decimal(str(report["opening_cash"])) == Decimal("1500.00")
    assert Decimal(str(report["inflows"])) == 0
    assert Decimal(str(report["closing_cash"])) == Decimal("1500.00")


def test_lafe_apertura_seed_is_idempotent(client, db):
    from scripts import lafe_apertura

    headers = auth_headers(register(client, email="liza@lafe.mx", business="Laboratorios La Fe"))
    _money_account(client, headers, name="Caja central", kind="CASH")
    _money_account(client, headers, name="Caja Morelos", kind="CASH")

    dry = lafe_apertura.main(["--org", "Laboratorios La Fe", "--dry-run"], db=db)
    assert dry[-1].startswith("Simulación")
    assert client.get("/api/opening", headers=headers).json()["opening_date"] is None

    lafe_apertura.main(["--org", "Laboratorios La Fe"], db=db)
    summary = client.get("/api/opening", headers=headers).json()
    entries_after_first = _all_entries(client, headers)
    second = lafe_apertura.main(["--org", "laboratorios la fe"], db=db)
    assert not any(line.lstrip().startswith(("+", "~")) for line in second)
    assert client.get("/api/opening", headers=headers).json() == summary
    assert _all_entries(client, headers) == entries_after_first

    assert summary["opening_date"] == "2026-11-01"
    assert summary["opening_status"] == "PROVISIONAL"
    rows = {row["name"]: row for row in summary["accounts"]}
    central = rows["Caja central"]
    assert (central["opening_balance"], central["opening_status"], central["opening_note"]) == (
        "27407.00",
        "CONFIRMED",
        "Control de efectivo al 31-oct-2026",
    )
    assert central["current_balance"] == "27407.00"
    for name in ("Santander PyME (Ale)", "Bancomer PyME (Liza)", "Santander Teresita (nómina)"):
        assert rows[name]["type"] == "BANK"
        assert (rows[name]["opening_balance"], rows[name]["opening_status"]) == ("0.00", "PROVISIONAL")
        assert rows[name]["opening_note"] == "Pendiente: estado de cuenta al 31-oct"
    assert rows["NetPay"]["type"] == "PROCESSOR"
    assert (rows["NetPay"]["opening_balance"], rows["NetPay"]["opening_status"]) == ("0.00", "PROVISIONAL")
    assert rows["NetPay"]["opening_note"] == "Pendiente: reporte de liquidación"
    assert (rows["Caja Morelos"]["opening_balance"], rows["Caja Morelos"]["opening_status"]) == ("0.00", "PROVISIONAL")
    assert Decimal(summary["bridge_balance"]) == Decimal("27407.00")
    [entry] = _entries(client, headers, "opening_adjustment")
    assert entry["date"] == "2026-11-01"
    _assert_balanced(client, headers)
