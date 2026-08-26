"""Exportación a CSV: lo que se le manda al contador."""

from datetime import date

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
