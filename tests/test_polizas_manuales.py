"""Pólizas manuales: el contador captura lo que los módulos no saben hacer."""

from datetime import date, timedelta
from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client, email="contador@example.com"):
    body = register(client, email=email, initial_cash="50000")
    headers = auth_headers(body)
    accounts = client.get("/api/accounting/accounts", headers=headers).json()
    by_code = {account["code"]: account for account in accounts}
    return headers, by_code


def _entry(client, headers, lines, when=None, description="Provisión de nómina", reference=None):
    return client.post(
        "/api/accounting/journal-entries",
        headers=headers,
        json={
            "date": (when or date.today()).isoformat(),
            "description": description,
            "reference": reference,
            "lines": lines,
        },
    )


def _line(account, debit="0", credit="0", description=None):
    return {"account_id": account["id"], "debit": debit, "credit": credit, "description": description}


def test_balanced_entry_is_posted_as_diario(client):
    headers, acc = _setup(client)
    response = _entry(
        client,
        headers,
        [
            _line(acc["5200"], debit="1000", description="Sueldos"),
            _line(acc["2400"], credit="100"),
            _line(acc["3100"], credit="900"),
        ],
        reference="NOM-10",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["folio"].startswith("Dr-")
    assert body["kind"] == "DIARIO"
    assert body["source_type"] == "manual"
    assert body["source_id"] == body["id"]
    assert body["reference"] == "NOM-10"
    assert body["reversed"] is False
    assert body["reversal_of"] is None
    assert len(body["lines"]) == 3

    diary = client.get("/api/accounting/journal-entries", headers=headers).json()
    assert any(item["id"] == body["id"] for item in diary["items"])
    balance = client.get("/api/accounting/trial-balance", headers=headers).json()
    nomina = next(row for row in balance["rows"] if row["code"] == "5200")
    assert Decimal(str(nomina["debit"])) == Decimal("1000")


def test_same_account_on_both_sides_is_fine(client):
    headers, acc = _setup(client)
    response = _entry(
        client,
        headers,
        [_line(acc["5100"], debit="300"), _line(acc["5100"], credit="100"), _line(acc["3100"], credit="200")],
    )
    assert response.status_code == 201, response.text


def test_unbalanced_entry_is_rejected(client):
    headers, acc = _setup(client)
    response = _entry(client, headers, [_line(acc["5200"], debit="1000"), _line(acc["3100"], credit="900")])
    assert response.status_code == 400
    assert "balanceado" in response.json()["detail"]


def test_three_decimals_that_only_balance_before_rounding_are_rejected(client):
    headers, acc = _setup(client)
    response = _entry(
        client,
        headers,
        [_line(acc["5200"], debit="10.005"), _line(acc["3100"], credit="10.004"), _line(acc["3200"], credit="0.001")],
    )
    assert response.status_code == 400


def test_single_line_and_empty_line_are_rejected(client):
    headers, acc = _setup(client)
    assert _entry(client, headers, [_line(acc["5200"], debit="10")]).status_code == 422
    response = _entry(client, headers, [_line(acc["5200"], debit="10", credit="10"), _line(acc["3100"])])
    assert response.status_code == 400
    assert "cargo o abono" in response.json()["detail"]


def test_major_account_is_rejected(client):
    headers, acc = _setup(client)
    response = _entry(client, headers, [_line(acc["5000"], debit="10"), _line(acc["3100"], credit="10")])
    assert response.status_code == 400
    assert "cuenta mayor" in response.json()["detail"]


def test_module_controlled_accounts_are_rejected(client):
    headers, acc = _setup(client)
    for code in ("1100", "1200", "2100", "2200"):
        response = _entry(client, headers, [_line(acc[code], debit="10"), _line(acc["3100"], credit="10")])
        assert response.status_code == 400, code
        assert "Movimientos" in response.json()["detail"]


def test_future_date_is_rejected(client):
    headers, acc = _setup(client)
    response = _entry(
        client,
        headers,
        [_line(acc["5200"], debit="10"), _line(acc["3100"], credit="10")],
        when=date.today() + timedelta(days=1),
    )
    assert response.status_code == 400
    assert "futura" in response.json()["detail"]


def test_closed_month_is_rejected(client):
    headers, acc = _setup(client)
    end = date.today().replace(day=1) - timedelta(days=1)
    assert (
        client.post("/api/periods/close", headers=headers, json={"year": end.year, "month": end.month}).status_code
        == 200
    )
    response = _entry(
        client, headers, [_line(acc["5200"], debit="10"), _line(acc["3100"], credit="10")], when=end
    )
    assert response.status_code == 400
    assert "cerrado" in response.json()["detail"]


def test_other_company_account_is_not_found(client):
    headers, acc = _setup(client)
    other_headers, other_acc = _setup(client, email="otra@example.com")
    response = _entry(client, headers, [_line(other_acc["5200"], debit="10"), _line(acc["3100"], credit="10")])
    assert response.status_code == 404


def test_instrument_balances_do_not_move(client):
    headers, acc = _setup(client)
    before = client.get("/api/accounts", headers=headers).json()[0]["current_balance"]
    assert _entry(client, headers, [_line(acc["5200"], debit="10"), _line(acc["3100"], credit="10")]).status_code == 201
    after = client.get("/api/accounts", headers=headers).json()[0]["current_balance"]
    assert before == after


def _posted(client, headers, acc, when=None):
    response = _entry(client, headers, [_line(acc["5200"], debit="1000"), _line(acc["3100"], credit="1000")], when=when)
    assert response.status_code == 201, response.text
    return response.json()


def _reverse(client, headers, entry_id, when=None, description=None):
    return client.post(
        f"/api/accounting/journal-entries/{entry_id}/reverse",
        headers=headers,
        json={"date": (when or date.today()).isoformat(), "description": description},
    )


def test_reverse_mirrors_the_lines_once(client):
    headers, acc = _setup(client)
    original = _posted(client, headers, acc)

    response = _reverse(client, headers, original["id"])
    assert response.status_code == 201, response.text
    reversal = response.json()
    assert reversal["reference"] == f"reversal:{original['id']}"
    assert reversal["reversal_of"] == original["id"]
    assert reversal["description"].startswith(f"Reverso de {original['folio']}")
    by_account = {line["account_id"]: line for line in reversal["lines"]}
    assert by_account[acc["5200"]["id"]]["credit"] == "1000.00"
    assert by_account[acc["3100"]["id"]]["debit"] == "1000.00"

    listed = client.get("/api/accounting/journal-entries", headers=headers).json()["items"]
    assert next(item for item in listed if item["id"] == original["id"])["reversed"] is True

    again = _reverse(client, headers, original["id"])
    assert again.status_code == 400
    assert "ya fue revertida" in again.json()["detail"]

    nested = _reverse(client, headers, reversal["id"])
    assert nested.status_code == 400
    assert "no se revierte" in nested.json()["detail"]


def test_reverse_keeps_custom_description_and_rejects_earlier_dates(client):
    headers, acc = _setup(client)
    original = _posted(client, headers, acc)
    earlier = _reverse(client, headers, original["id"], when=date.today() - timedelta(days=1))
    assert earlier.status_code == 400
    assert "anterior" in earlier.json()["detail"]
    custom = _reverse(client, headers, original["id"], description="Se duplicó la provisión")
    assert custom.status_code == 201
    assert custom.json()["description"] == "Se duplicó la provisión"


def test_reverse_into_closed_month_leaves_original_untouched(client):
    headers, acc = _setup(client)
    end = date.today().replace(day=1) - timedelta(days=1)
    original = _posted(client, headers, acc, when=end)
    assert client.post("/api/periods/close", headers=headers, json={"year": end.year, "month": end.month}).status_code == 200
    response = _reverse(client, headers, original["id"], when=end)
    assert response.status_code == 400
    assert "cerrado" in response.json()["detail"]
    listed = client.get("/api/accounting/journal-entries", headers=headers).json()["items"]
    assert next(item for item in listed if item["id"] == original["id"])["reversed"] is False


def test_operation_entries_are_reversed_from_their_module(client):
    headers, acc = _setup(client)
    account = client.get("/api/accounts", headers=headers).json()[0]
    ventas = next(
        c for c in client.get("/api/categories?kind=INCOME", headers=headers).json() if c["name"] == "Ventas"
    )
    income = client.post(
        "/api/income",
        headers=headers,
        json={
            "date": date.today().isoformat(),
            "description": "Venta",
            "amount": "5000",
            "category_id": ventas["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    assert income.status_code == 201, income.text
    entry = client.get(
        "/api/accounting/journal-entries",
        headers=headers,
        params={"source_type": "income", "source_id": income.json()["id"]},
    ).json()["items"][0]
    response = _reverse(client, headers, entry["id"])
    assert response.status_code == 400
    assert "operación" in response.json()["detail"]


def test_other_company_cannot_reverse(client):
    headers, acc = _setup(client)
    original = _posted(client, headers, acc)
    other_headers, _ = _setup(client, email="otra@example.com")
    assert _reverse(client, other_headers, original["id"]).status_code == 404
