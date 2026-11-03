"""HU-09: historial de cambios con valores anteriores."""

from app.models.change_log import ChangeLog
from tests.helpers import auth_headers, register


def _setup(client, email="dueno@example.com", business="Laboratorios La Fe"):
    body = register(client, email=email, business=business, initial_cash="10000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    categories = client.get("/api/categories?kind=EXPENSE", headers=headers).json()
    renta = next(c for c in categories if c["name"] == "Renta")
    return headers, account, renta, categories


def _expense(client, headers, renta, account=None, amount="1200", status="PENDING"):
    payload = {
        "date": "2026-11-02",
        "description": "Renta de noviembre",
        "amount": amount,
        "category_id": renta["id"],
        "status": status,
    }
    if account:
        payload["financial_account_id"] = account["id"]
    response = client.post("/api/expenses", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _history(client, headers, entity_id, entity_type="expense"):
    response = client.get(
        "/api/history", headers=headers, params={"entity_type": entity_type, "entity_id": entity_id}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_create_is_recorded_with_key_fields(client):
    headers, account, renta, _ = _setup(client)
    expense = _expense(client, headers, renta, account)

    page = _history(client, headers, expense["id"])
    assert page["total"] == 1
    event = page["items"][0]
    assert event["action"] == "CREATE"
    assert event["user_name"] == "Dueño"
    assert event["source"] == "web"
    fields = {change["field"]: change for change in event["changes"]}
    assert fields["amount"]["new"] == "1200.00"
    assert fields["category_id"]["new_display"] == "Renta"
    assert fields["financial_account_id"]["new_display"] == account["name"]


def test_edit_records_old_and_new_amount_only_for_changed_fields(client):
    headers, account, renta, categories = _setup(client)
    expense = _expense(client, headers, renta, account)
    other = next(c for c in categories if c["id"] != renta["id"])

    response = client.patch(
        f"/api/expenses/{expense['id']}",
        headers=headers,
        json={"amount": "1350", "category_id": other["id"], "description": "Renta de noviembre"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["amount"] == "1350.00"

    event = _history(client, headers, expense["id"])["items"][0]
    assert event["action"] == "UPDATE"
    fields = {change["field"]: change for change in event["changes"]}
    # Sólo lo que cambió: la descripción se mandó igual y no aparece.
    assert set(fields) == {"amount", "category_id"}
    assert fields["amount"]["old"] == "1200.00"
    assert fields["amount"]["new"] == "1350.00"
    assert fields["amount"]["label"] == "Monto"
    assert fields["category_id"]["old_display"] == "Renta"
    assert fields["category_id"]["new_display"] == other["name"]


def test_edit_without_changes_leaves_no_trace(client):
    headers, account, renta, _ = _setup(client)
    expense = _expense(client, headers, renta, account)
    client.patch(f"/api/expenses/{expense['id']}", headers=headers, json={"amount": "1200.00"})
    assert _history(client, headers, expense["id"])["total"] == 1  # sólo el CREATE


def test_paid_expense_only_accepts_project_edit(client):
    headers, account, renta, _ = _setup(client)
    expense = _expense(client, headers, renta, account, status="PAID")
    response = client.patch(f"/api/expenses/{expense['id']}", headers=headers, json={"amount": "999"})
    assert response.status_code == 400
    assert "cancélalo" in response.json()["detail"]


def test_decimal_is_stored_as_string(client, db):
    headers, account, renta, _ = _setup(client)
    expense = _expense(client, headers, renta, account, amount="1200.50")
    client.patch(f"/api/expenses/{expense['id']}", headers=headers, json={"amount": "1350.25"})
    row = (
        db.query(ChangeLog)
        .filter(ChangeLog.entity_id == expense["id"], ChangeLog.action == "UPDATE")
        .one()
    )
    assert row.changes["amount"] == {"old": "1200.50", "new": "1350.25"}
    assert isinstance(row.changes["amount"]["old"], str)


def test_cancel_records_reason(client):
    headers, account, renta, _ = _setup(client)
    expense = _expense(client, headers, renta, account)
    response = client.post(
        f"/api/expenses/{expense['id']}/cancel", headers=headers, json={"reason": "Se capturó dos veces"}
    )
    assert response.status_code == 200, response.text

    event = _history(client, headers, expense["id"])["items"][0]
    assert event["action"] == "CANCEL"
    assert event["reason"] == "Se capturó dos veces"
    status = next(change for change in event["changes"] if change["field"] == "status")
    assert (status["old"], status["new"]) == ("PENDING", "CANCELLED")


def test_pay_records_pay(client):
    headers, account, renta, _ = _setup(client)
    expense = _expense(client, headers, renta)
    response = client.post(
        f"/api/expenses/{expense['id']}/pay",
        headers=headers,
        json={"financial_account_id": account["id"]},
    )
    assert response.status_code == 200, response.text

    events = _history(client, headers, expense["id"])["items"]
    assert [event["action"] for event in events] == ["PAY", "CREATE"]  # lo más nuevo primero
    fields = {change["field"]: change for change in events[0]["changes"]}
    assert (fields["status"]["old"], fields["status"]["new"]) == ("PENDING", "PAID")
    assert fields["financial_account_id"]["new_display"] == account["name"]


def test_payable_payment_and_receivable_cancel_are_recorded(client):
    headers, account, renta, _ = _setup(client)
    vendor = client.post("/api/vendors", headers=headers, json={"name": "Inmobiliaria"}).json()
    payable = client.post(
        "/api/payables",
        headers=headers,
        json={
            "vendor_id": vendor["id"],
            "description": "Renta",
            "amount": "4000",
            "due_date": "2026-11-30",
            "category_id": renta["id"],
        },
    ).json()
    client.post(
        f"/api/payables/{payable['id']}/pay",
        headers=headers,
        json={"amount": "1500", "financial_account_id": account["id"]},
    )
    events = client.get(f"/api/payables/{payable['id']}/history", headers=headers).json()["items"]
    assert [event["action"] for event in events] == ["PAY", "CREATE"]
    fields = {change["field"]: change for change in events[0]["changes"]}
    assert (fields["amount_paid"]["old"], fields["amount_paid"]["new"]) == ("0.00", "1500.00")
    assert fields["payment_account_id"]["new_display"] == account["name"]

    customer = client.post("/api/customers", headers=headers, json={"name": "Farmacia Sol"}).json()
    ventas = client.get("/api/categories?kind=INCOME", headers=headers).json()[0]
    receivable = client.post(
        "/api/receivables",
        headers=headers,
        json={
            "customer_id": customer["id"],
            "description": "Pedido 12",
            "amount": "800",
            "due_date": "2026-11-30",
            "category_id": ventas["id"],
        },
    ).json()
    client.post(f"/api/receivables/{receivable['id']}/cancel", headers=headers, json={"reason": "Pedido devuelto"})
    events = client.get(f"/api/receivables/{receivable['id']}/history", headers=headers).json()["items"]
    assert [event["action"] for event in events] == ["CANCEL", "CREATE"]
    assert events[0]["reason"] == "Pedido devuelto"


def test_income_edit_and_account_edit_are_recorded(client):
    headers, account, _renta, _ = _setup(client)
    ventas = client.get("/api/categories?kind=INCOME", headers=headers).json()[0]
    income = client.post(
        "/api/income",
        headers=headers,
        json={"date": "2026-11-02", "description": "Venta", "amount": "500", "category_id": ventas["id"]},
    ).json()
    client.patch(f"/api/income/{income['id']}", headers=headers, json={"date": "2026-11-01"})
    event = client.get(f"/api/income/{income['id']}/history", headers=headers).json()["items"][0]
    assert event["changes"] == [
        {
            "field": "date",
            "label": "Fecha",
            "kind": "date",
            "old": "2026-11-02",
            "new": "2026-11-01",
            "old_display": None,
            "new_display": None,
        }
    ]

    client.patch(f"/api/accounts/{account['id']}", headers=headers, json={"name": "Caja chica"})
    event = client.get(f"/api/accounts/{account['id']}/history", headers=headers).json()["items"][0]
    assert event["action"] == "UPDATE"
    assert event["changes"][0]["old"] == account["name"]
    assert event["changes"][0]["new"] == "Caja chica"


def test_endpoint_filters_by_entity_and_paginates(client):
    headers, account, renta, _ = _setup(client)
    first = _expense(client, headers, renta, account)
    second = _expense(client, headers, renta, account)
    for amount in ("1300", "1400", "1500"):
        client.patch(f"/api/expenses/{first['id']}", headers=headers, json={"amount": amount})

    page = client.get(
        "/api/history",
        headers=headers,
        params={"entity_type": "expense", "entity_id": first["id"], "limit": 2, "offset": 0},
    ).json()
    assert page["total"] == 4
    assert page["limit"] == 2 and page["offset"] == 0
    assert len(page["items"]) == 2
    assert all(event["entity_id"] == first["id"] for event in page["items"])
    assert page["items"][0]["changes"][0]["new"] == "1500.00"  # lo más nuevo primero
    assert page["items"][0]["entity_label"] == "Renta de noviembre"

    rest = client.get(
        "/api/history",
        headers=headers,
        params={"entity_type": "expense", "entity_id": first["id"], "limit": 2, "offset": 2},
    ).json()
    assert [event["action"] for event in rest["items"]] == ["UPDATE", "CREATE"]

    everything = client.get("/api/history", headers=headers).json()
    ids = {event["entity_id"] for event in everything["items"]}
    assert {first["id"], second["id"]} <= ids

    by_date = client.get("/api/history", headers=headers, params={"from": "2000-01-01", "to": "2000-01-31"})
    assert by_date.json()["total"] == 0


def test_tenant_isolation(client):
    headers_a, account_a, renta_a, _ = _setup(client)
    expense = _expense(client, headers_a, renta_a, account_a)
    headers_b, *_ = _setup(client, email="otra@example.com", business="Otra empresa")

    assert _history(client, headers_b, expense["id"])["total"] == 0
    assert client.get("/api/history", headers=headers_b).json()["total"] == 0
    assert client.get(f"/api/expenses/{expense['id']}/history", headers=headers_b).json()["items"] == []
    assert _history(client, headers_a, expense["id"])["total"] == 1


def test_history_has_no_write_endpoints(client):
    headers, *_ = _setup(client)
    assert client.post("/api/history", headers=headers, json={}).status_code == 405
    assert client.delete("/api/history", headers=headers).status_code == 405
