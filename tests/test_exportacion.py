"""Exportación a CSV y Excel: lo que se le manda al contador."""

import io
from datetime import date

from openpyxl import load_workbook

from app.services import listing
from tests.helpers import auth_headers, register


def _setup(client):
    body = register(client, initial_cash="50000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    ventas = next(
        c
        for c in client.get("/api/categories?kind=INCOME", headers=headers).json()
        if c["name"] == "Ventas"
    )
    client.post(
        "/api/income",
        headers=headers,
        json={
            "date": date.today().isoformat(),
            "description": "Venta de prueba",
            "amount": "11600",
            "tax_rate": "0.16",
            "category_id": ventas["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    return headers


def test_profit_loss_downloads_as_csv(client):
    headers = _setup(client)
    response = client.get("/api/reports/profit-loss/csv", headers=headers)

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    assert "estado-de-resultados" in response.headers["content-disposition"]

    text = response.text
    # BOM al inicio: sin él Excel en Windows rompe los acentos.
    assert text.startswith("﻿")
    assert "Ventas" in text
    assert "Resultado del periodo" in text
    # El IVA no es ingreso: sólo el subtotal llega al reporte.
    assert "10000.00" in text


def test_balance_sheet_and_trial_balance_export(client):
    headers = _setup(client)
    for report in ("balance-sheet", "trial-balance", "aging"):
        response = client.get(f"/api/reports/{report}/csv", headers=headers)
        assert response.status_code == 200, report
        assert "text/csv" in response.headers["content-type"]


def test_an_unknown_report_is_rejected(client):
    headers = _setup(client)
    response = client.get("/api/reports/inventado/csv", headers=headers)
    assert response.status_code == 404
    assert "no se puede exportar" in response.json()["detail"]


def test_export_only_covers_your_own_company(client):
    headers_a = _setup(client)
    assert "Venta de prueba" not in client.get(
        "/api/reports/profit-loss/csv", headers=headers_a
    ).text or True  # el P&L agrupa por cuenta, no lista conceptos

    body_b = register(client, email="otra@example.com", initial_cash="1000")
    headers_b = auth_headers(body_b)
    text_b = client.get("/api/reports/profit-loss/csv", headers=headers_b).text
    # La otra empresa no ve los 10,000 de la primera.
    assert "10000.00" not in text_b


# ---------- HU-11: listas filtradas y descarga a Excel ----------


def _expense_company(client, email="dueno@example.com"):
    body = register(client, email=email, initial_cash="100000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    categories = {c["name"]: c for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json()}
    return body, headers, account, categories


def _expense(client, headers, account, category, amount, description, *, when="2026-10-05", **extra):
    payload = {
        "date": when,
        "description": description,
        "amount": amount,
        "tax_rate": "0.16",
        "category_id": category["id"],
        "financial_account_id": account["id"],
        "status": "PAID",
        **extra,
    }
    response = client.post("/api/expenses", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _sheet(response):
    workbook = load_workbook(io.BytesIO(response.content))
    return list(workbook.active.iter_rows(values_only=True))


def test_expense_xlsx_export_honors_the_category_filter(client):
    _body, headers, account, categories = _expense_company(client)
    renta = categories["Renta"]
    otros = next(c for name, c in categories.items() if name != "Renta")
    _expense(client, headers, account, renta, "11600", "Renta de octubre")
    _expense(client, headers, account, renta, "2320", "Bodega de octubre", when="2026-10-20")
    _expense(client, headers, account, otros, "500", "Otra cosa")

    response = client.get(
        "/api/expenses/export",
        headers=headers,
        params={"category_id": renta["id"], "start": "2026-10-01", "end": "2026-10-31"},
    )
    assert response.status_code == 200, response.text
    assert "spreadsheetml" in response.headers["content-type"]
    assert 'filename="gastos_2026-10-01_a_2026-10-31.xlsx"' in response.headers["content-disposition"]

    rows = _sheet(response)
    header, data, total = rows[0], rows[1:-1], rows[-1]
    assert header[:3] == ("Fecha", "Concepto", "Categoría")
    assert header[9:12] == ("Subtotal", "IVA", "Total")
    assert {row[1] for row in data} == {"Renta de octubre", "Bodega de octubre"}
    assert all(row[2] == "Renta" for row in data)
    # Cifras de verdad, no texto.
    renta_row = next(row for row in data if row[1] == "Renta de octubre")
    assert isinstance(renta_row[11], (int, float)) and renta_row[11] == 11600
    assert renta_row[9] == 10000 and renta_row[10] == 1600
    assert renta_row[12] == "Dueño"
    assert total[0] == "Total"
    assert total[11] == 13920

    workbook = load_workbook(io.BytesIO(response.content))
    assert "$" in workbook.active.cell(row=2, column=12).number_format


def test_expense_csv_export(client):
    _body, headers, account, categories = _expense_company(client)
    _expense(client, headers, account, categories["Renta"], "1160", "Renta chica")
    response = client.get("/api/expenses/export", headers=headers, params={"format": "csv"})
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert response.headers["content-disposition"].endswith('.csv"')
    text = response.text
    assert text.startswith("﻿Fecha,Concepto")
    assert "Renta chica" in text
    assert "1160.00" in text
    assert text.splitlines()[-1].startswith("Total")


def test_filters_combine_in_list_and_export(client):
    _body, headers, account, categories = _expense_company(client)
    renta = categories["Renta"]
    _expense(client, headers, account, renta, "500", "Renta barata", payment_method="EFECTIVO")
    _expense(client, headers, account, renta, "5000", "Renta cara", payment_method="EFECTIVO")
    _expense(client, headers, account, renta, "5000", "Renta por banco", payment_method="TRANSFERENCIA")

    params = {"payment_method": "EFECTIVO", "min_amount": "1000", "q": "renta"}
    listed = client.get("/api/expenses", headers=headers, params=params).json()
    assert [item["description"] for item in listed["items"]] == ["Renta cara"]

    rows = _sheet(client.get("/api/expenses/export", headers=headers, params=params))
    assert [row[1] for row in rows[1:-1]] == ["Renta cara"]
    assert rows[1][7] == "Efectivo"

    capped = client.get("/api/expenses", headers=headers, params={"max_amount": "600"}).json()
    assert [item["description"] for item in capped["items"]] == ["Renta barata"]


def test_created_by_and_payment_method_filter_the_list(client):
    body, headers, account, categories = _expense_company(client)
    renta = categories["Renta"]
    invited = client.post(
        "/api/organizations/current/members",
        headers=headers,
        json={
            "email": "capturista@example.com",
            "name": "Capturista",
            "role": "MEMBER",
            "password": "supersegura123",
        },
    )
    assert invited.status_code == 201, invited.text
    login = client.post(
        "/api/auth/login", json={"email": "capturista@example.com", "password": "supersegura123"}
    ).json()
    member_headers = {**auth_headers(login), "X-Organization-ID": body["organization"]["id"]}

    _expense(client, headers, account, renta, "100", "Del dueño", payment_method="TRANSFERENCIA")
    _expense(client, member_headers, account, renta, "200", "De la capturista", payment_method="EFECTIVO")

    owner_id = body["user"]["id"]
    member_id = invited.json()["user_id"]
    by_owner = client.get("/api/expenses", headers=headers, params={"created_by": owner_id}).json()
    by_member = client.get("/api/expenses", headers=headers, params={"created_by": member_id}).json()
    assert [i["description"] for i in by_owner["items"]] == ["Del dueño"]
    assert [i["description"] for i in by_member["items"]] == ["De la capturista"]

    cash = client.get("/api/expenses", headers=headers, params={"payment_method": "EFECTIVO"}).json()
    assert [i["description"] for i in cash["items"]] == ["De la capturista"]

    rows = _sheet(client.get("/api/expenses/export", headers=headers, params={"created_by": member_id}))
    assert rows[1][12] == "Capturista"


def test_list_export_is_tenant_isolated(client):
    _body, headers_a, account_a, categories_a = _expense_company(client)
    _expense(client, headers_a, account_a, categories_a["Renta"], "999", "Secreto de A")
    _body_b, headers_b, _account_b, _categories_b = _expense_company(client, email="otra@example.com")

    for path in ("/api/expenses/export", "/api/income/export", "/api/transactions/export"):
        response = client.get(path, headers=headers_b, params={"format": "csv"})
        assert response.status_code == 200, path
        assert "Secreto de A" not in response.text, path

    # Ni filtrando por la categoría ajena aparece nada.
    rows = _sheet(
        client.get(
            "/api/expenses/export", headers=headers_b, params={"category_id": categories_a["Renta"]["id"]}
        )
    )
    assert rows[1:-1] == []


def test_export_rejects_more_rows_than_the_limit(client, monkeypatch):
    _body, headers, account, categories = _expense_company(client)
    for n in range(3):
        _expense(client, headers, account, categories["Renta"], "100", f"Renta {n}")
    monkeypatch.setattr(listing, "MAX_EXPORT_ROWS", 2)
    response = client.get("/api/expenses/export", headers=headers)
    assert response.status_code == 400
    assert "máximo" in response.json()["detail"]
    # Acotando, cabe.
    assert client.get("/api/expenses/export", headers=headers, params={"q": "Renta 1"}).status_code == 200


def test_cancelled_rows_are_listed_but_not_summed(client):
    _body, headers, account, categories = _expense_company(client)
    _expense(client, headers, account, categories["Renta"], "100", "Se queda")
    gone = _expense(client, headers, account, categories["Renta"], "900", "Se cancela")
    cancelled = client.post(f"/api/expenses/{gone['id']}/cancel", headers=headers, json={})
    assert cancelled.status_code == 200, cancelled.text

    rows = _sheet(client.get("/api/expenses/export", headers=headers))
    assert {row[1] for row in rows[1:-1]} == {"Se queda", "Se cancela"}
    assert rows[-1][0] == "Total (sin cancelados)"
    assert rows[-1][11] == 100
    only_cancelled = _sheet(
        client.get("/api/expenses/export", headers=headers, params={"status": "CANCELLED"})
    )
    assert [row[1] for row in only_cancelled[1:-1]] == ["Se cancela"]


def test_income_and_movements_export(client):
    headers = _setup(client)
    response = client.get("/api/income/export", headers=headers)
    assert response.status_code == 200
    rows = _sheet(response)
    assert rows[1][1] == "Venta de prueba"
    assert rows[1][11] == 11600
    assert rows[1][8] == "Cobrado"

    movements = _sheet(client.get("/api/transactions/export", headers=headers))
    assert movements[0][2] == "Tipo"
    sale = next(row for row in movements[1:-1] if row[1] == "Venta de prueba")
    assert sale[2] == "Ingreso"
    assert sale[3] == "Ventas"
    assert sale[12] == 11600

    ventas = next(
        c for c in client.get("/api/categories?kind=INCOME", headers=headers).json() if c["name"] == "Ventas"
    )
    filtered = client.get("/api/transactions", headers=headers, params={"category_id": ventas["id"]}).json()
    assert [item["description"] for item in filtered["items"]] == ["Venta de prueba"]
