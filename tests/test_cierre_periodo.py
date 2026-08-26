"""Cierre de periodo: un mes ya declarado no se toca sin querer."""

from datetime import date, timedelta

from tests.helpers import auth_headers, register


def _closed_month() -> tuple[int, int]:
    """El último mes que ya terminó."""
    end = date.today().replace(day=1) - timedelta(days=1)
    return end.year, end.month


def _setup(client, email="dueno@example.com"):
    body = register(client, email=email, initial_cash="100000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    ventas = next(
        c
        for c in client.get("/api/categories?kind=INCOME", headers=headers).json()
        if c["name"] == "Ventas"
    )
    return headers, account, ventas


def _income(client, headers, account, ventas, when: date):
    return client.post(
        "/api/income",
        headers=headers,
        json={
            "date": when.isoformat(),
            "description": "Venta",
            "amount": "5000",
            "category_id": ventas["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )


def test_closing_blocks_new_entries_in_that_month(client):
    headers, account, ventas = _setup(client)
    year, month = _closed_month()

    assert (
        client.post("/api/periods/close", headers=headers, json={"year": year, "month": month}).status_code
        == 200
    )

    response = _income(client, headers, account, ventas, date(year, month, 15))
    assert response.status_code == 400
    assert "cerrado" in response.json()["detail"]


def test_other_months_keep_working(client):
    headers, account, ventas = _setup(client)
    year, month = _closed_month()
    client.post("/api/periods/close", headers=headers, json={"year": year, "month": month})

    # El mes en curso no se ve afectado por el cierre del anterior.
    response = _income(client, headers, account, ventas, date.today())
    assert response.status_code == 201


def test_a_month_that_has_not_ended_cannot_be_closed(client):
    headers, _account, _ventas = _setup(client)
    today = date.today()
    response = client.post(
        "/api/periods/close", headers=headers, json={"year": today.year, "month": today.month}
    )
    assert response.status_code == 400
    assert "todavía no termina" in response.json()["detail"]


def test_reopening_requires_a_reason_and_lets_you_correct(client):
    headers, account, ventas = _setup(client)
    year, month = _closed_month()
    client.post("/api/periods/close", headers=headers, json={"year": year, "month": month})

    sin_motivo = client.post(
        "/api/periods/reopen", headers=headers, json={"year": year, "month": month}
    )
    assert sin_motivo.status_code == 422  # el motivo es obligatorio

    reabierto = client.post(
        "/api/periods/reopen",
        headers=headers,
        json={"year": year, "month": month, "reason": "Faltó una factura del cliente"},
    )
    assert reabierto.status_code == 200

    # Ya se puede corregir.
    assert _income(client, headers, account, ventas, date(year, month, 15)).status_code == 201


def test_closing_twice_is_rejected(client):
    headers, _account, _ventas = _setup(client)
    year, month = _closed_month()
    client.post("/api/periods/close", headers=headers, json={"year": year, "month": month})
    again = client.post("/api/periods/close", headers=headers, json={"year": year, "month": month})
    assert again.status_code == 400
    assert "ya está cerrado" in again.json()["detail"]


def test_the_list_shows_state_and_movement(client):
    headers, account, ventas = _setup(client)
    year, month = _closed_month()
    _income(client, headers, account, ventas, date(year, month, 10))
    client.post("/api/periods/close", headers=headers, json={"year": year, "month": month})

    items = client.get("/api/periods", headers=headers).json()["items"]
    row = next(r for r in items if r["year"] == year and r["month"] == month)
    assert row["closed"] is True
    assert row["entries"] >= 1
    # El mes en curso aparece pero no se puede cerrar todavía.
    current = items[0]
    assert current["can_close"] is False


def test_depreciation_respects_a_closed_period(client):
    headers, account, _ventas = _setup(client)
    year, month = _closed_month()
    bought = (date(year, month, 1) - timedelta(days=40)).replace(day=1)
    client.post(
        "/api/fixed-assets",
        headers=headers,
        json={
            "name": "Laptop",
            "acquisition_date": bought.isoformat(),
            "cost": "36000",
            "useful_life_months": 36,
            "financial_account_id": account["id"],
        },
    )
    client.post("/api/periods/close", headers=headers, json={"year": year, "month": month})

    response = client.post(
        "/api/fixed-assets/depreciate", headers=headers, json={"year": year, "month": month}
    )
    # El candado vive en el motor, así que protege también a los procesos automáticos.
    assert response.status_code == 400
    assert "cerrado" in response.json()["detail"]


def test_periods_are_isolated_by_organization(client):
    headers_a, _account, _ventas = _setup(client)
    year, month = _closed_month()
    client.post("/api/periods/close", headers=headers_a, json={"year": year, "month": month})

    headers_b, account_b, ventas_b = _setup(client, email="otra@example.com")
    # La otra empresa no heredó el candado.
    assert _income(client, headers_b, account_b, ventas_b, date(year, month, 15)).status_code == 201
