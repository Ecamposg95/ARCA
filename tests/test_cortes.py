"""Corte de caja: esperado desde los movimientos, diferencia explicada que
deja la caja en lo contado, entrega como traspaso y confirmación de quien
recibe. Nada se borra: recontar y cancelar revierten."""

from datetime import date, timedelta
from decimal import Decimal

from tests.helpers import auth_headers, register
from tests.test_liquidaciones import _member_headers
from tests.test_transito import _account, _balances


def _setup(client, email="dueno@example.com"):
    body = register(client, email=email, initial_cash="1000")
    headers = auth_headers(body)
    caja = client.get("/api/accounts", headers=headers).json()[0]
    central = client.post(
        "/api/accounts", headers=headers, json={"name": "Caja central", "type": "CASH", "opening_balance": "0"}
    ).json()
    cats = {c["kind"] + ":" + c["name"]: c for c in client.get("/api/categories", headers=headers).json()}
    return headers, caja, central, cats


def _sale(client, headers, caja, cats, amount, when=None):
    response = client.post(
        "/api/income",
        headers=headers,
        json={
            "date": (when or date.today()).isoformat(),
            "description": "Venta en efectivo",
            "amount": amount,
            "category_id": cats["INCOME:Ventas"]["id"],
            "financial_account_id": caja["id"],
            "status": "PAID",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _spend(client, headers, caja, cats, amount, when=None):
    response = client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": (when or date.today()).isoformat(),
            "description": "Hielo",
            "amount": amount,
            "category_id": cats["EXPENSE:Otros"]["id"],
            "financial_account_id": caja["id"],
            "status": "PAID",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _cut(client, headers, caja, when=None):
    return client.post(
        "/api/cash-cuts",
        headers=headers,
        json={"financial_account_id": caja["id"], "date": (when or date.today()).isoformat()},
    )


def _count(client, headers, cut_id, counted, explanation=None):
    payload = {"counted_amount": counted}
    if explanation:
        payload["explanation"] = explanation
    return client.post(f"/api/cash-cuts/{cut_id}/count", headers=headers, json=payload)


def _deliver(client, headers, cut_id, amount, to_account_id):
    return client.post(
        f"/api/cash-cuts/{cut_id}/deliver",
        headers=headers,
        json={"delivered_amount": amount, "delivered_to_account_id": to_account_id},
    )


# --- Abrir el corte -----------------------------------------------------------------


def test_cut_expected_comes_from_the_days_movements(client):
    headers, caja, central, cats = _setup(client)
    yesterday = date.today() - timedelta(days=1)
    _sale(client, headers, caja, cats, "500", when=yesterday)  # ayer: no es del día
    _sale(client, headers, caja, cats, "800")
    _sale(client, headers, caja, cats, "200")
    _spend(client, headers, caja, cats, "150")

    response = _cut(client, headers, caja)
    assert response.status_code == 201, response.text
    cut = response.json()
    assert cut["status"] == "OPEN"
    assert cut["account_name"] == caja["name"]
    assert cut["opening_balance"] == "1500.00"  # 1000 inicial + 500 de ayer
    assert cut["inflows"] == "1000.00"
    assert cut["outflows"] == "150.00"
    assert cut["expected_closing"] == "2350.00"
    assert cut["counted_amount"] is None


def test_one_cut_per_cash_account_and_day(client):
    headers, caja, central, cats = _setup(client)
    assert _cut(client, headers, caja).status_code == 201
    response = _cut(client, headers, caja)
    assert response.status_code == 409
    assert "ya tiene corte" in response.json()["detail"]
    # Otro día u otra caja sí.
    assert _cut(client, headers, caja, when=date.today() - timedelta(days=1)).status_code == 201
    assert _cut(client, headers, central).status_code == 201


def test_cut_only_for_cash_accounts(client):
    headers, caja, central, cats = _setup(client)
    banco = client.post("/api/accounts", headers=headers, json={"name": "BBVA", "type": "BANK"}).json()
    response = _cut(client, headers, banco)
    assert response.status_code == 400
    assert "efectivo" in response.json()["detail"]
    assert _cut(client, headers, caja, when=date.today() + timedelta(days=1)).status_code == 400


def test_today_lists_every_cash_account_with_its_cut(client):
    headers, caja, central, cats = _setup(client)
    rows = client.get("/api/cash-cuts/today", headers=headers).json()
    assert [row["account_name"] for row in rows] == [caja["name"], "Caja central"]
    assert rows[0]["cut"] is None
    assert rows[0]["current_balance"] == "1000.00"

    cut = _cut(client, headers, caja).json()
    rows = client.get("/api/cash-cuts/today", headers=headers).json()
    assert rows[0]["cut"]["id"] == cut["id"]
    assert rows[0]["cut"]["status"] == "OPEN"


# --- Contar -------------------------------------------------------------------------


def test_difference_requires_an_explanation(client):
    headers, caja, central, cats = _setup(client)
    cut = _cut(client, headers, caja).json()
    response = _count(client, headers, cut["id"], "950")
    assert response.status_code == 400
    assert response.json()["detail"] == "Explica la diferencia."
    # Sin diferencia no hace falta explicar.
    response = _count(client, headers, cut["id"], "1000")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "COUNTED"
    assert response.json()["difference"] == "0.00"
    assert response.json()["adjustment_transaction_id"] is None


def test_shortage_adjustment_leaves_the_cash_at_the_counted_amount(client):
    headers, caja, central, cats = _setup(client)
    _sale(client, headers, caja, cats, "500")
    before = _balances(client, headers)
    cut = _cut(client, headers, caja).json()
    assert cut["expected_closing"] == "1500.00"

    response = _count(client, headers, cut["id"], "1450", explanation="Faltó un billete de 50")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["difference"] == "-50.00"
    assert body["adjustment_transaction_id"] is not None
    assert _account(client, headers, caja["id"])["current_balance"] == "1450.00"

    # El faltante es un gasto en resultados; el libro cuadra.
    after = _balances(client, headers)
    assert after["5700"] - before.get("5700", Decimal("0")) == Decimal("50")
    assert after["1100"] - before["1100"] == Decimal("-50")
    categories = client.get("/api/categories?kind=EXPENSE", headers=headers).json()
    assert any(c["name"] == "Diferencias de caja" for c in categories)


def test_surplus_adjustment_is_income(client):
    headers, caja, central, cats = _setup(client)
    before = _balances(client, headers)
    cut = _cut(client, headers, caja).json()
    response = _count(client, headers, cut["id"], "1020", explanation="Propina en la caja")
    assert response.status_code == 200, response.text
    assert response.json()["difference"] == "20.00"
    assert _account(client, headers, caja["id"])["current_balance"] == "1020.00"
    after = _balances(client, headers)
    assert after["4100"] - before.get("4100", Decimal("0")) == Decimal("20")


def test_recount_reverses_the_previous_adjustment(client):
    headers, caja, central, cats = _setup(client)
    cut = _cut(client, headers, caja).json()
    first = _count(client, headers, cut["id"], "950", explanation="Faltante").json()
    assert _account(client, headers, caja["id"])["current_balance"] == "950.00"

    second = _count(client, headers, cut["id"], "990", explanation="Apareció un billete").json()
    assert second["difference"] == "-10.00"
    assert second["adjustment_transaction_id"] != first["adjustment_transaction_id"]
    # La caja queda en lo contado la segunda vez, no acumula ajustes.
    assert _account(client, headers, caja["id"])["current_balance"] == "990.00"
    # El esperado no persigue al contado: sigue siendo lo del día.
    assert second["expected_closing"] == "1000.00"
    assert second["inflows"] == "0.00" and second["outflows"] == "0.00"

    # Y volver a cuadrar deja la caja como estaba.
    third = _count(client, headers, cut["id"], "1000").json()
    assert third["difference"] == "0.00" and third["adjustment_transaction_id"] is None
    assert _account(client, headers, caja["id"])["current_balance"] == "1000.00"
    trial = client.get("/api/accounting/trial-balance", headers=headers).json()
    assert Decimal(str(trial["total_debit"])) == Decimal(str(trial["total_credit"]))


def test_count_refreshes_expected_with_sales_after_opening(client):
    headers, caja, central, cats = _setup(client)
    cut = _cut(client, headers, caja).json()
    _sale(client, headers, caja, cats, "300")
    body = _count(client, headers, cut["id"], "1300").json()
    assert body["expected_closing"] == "1300.00"
    assert body["difference"] == "0.00"


# --- Entregar y confirmar -----------------------------------------------------------


def test_delivery_is_a_transfer_capped_at_the_counted_amount(client):
    headers, caja, central, cats = _setup(client)
    cut = _cut(client, headers, caja).json()
    assert _deliver(client, headers, cut["id"], "100", central["id"]).status_code == 400  # sin contar
    _count(client, headers, cut["id"], "1000")

    response = _deliver(client, headers, cut["id"], "1500", central["id"])
    assert response.status_code == 400
    assert "contado" in response.json()["detail"]

    response = _deliver(client, headers, cut["id"], "900", central["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "DELIVERED"
    assert body["delivered_amount"] == "900.00"
    assert body["delivered_to_account_name"] == "Caja central"
    assert body["delivered_by_name"] == "Dueño"
    assert body["transfer_group_id"]
    assert _account(client, headers, caja["id"])["current_balance"] == "100.00"
    assert _account(client, headers, central["id"])["current_balance"] == "900.00"
    # Un corte entregado no se recuenta.
    assert _count(client, headers, cut["id"], "50", explanation="x").status_code == 400


def test_delivery_destination_must_be_cash_or_bank(client):
    headers, caja, central, cats = _setup(client)
    tarjeta = client.post("/api/accounts", headers=headers, json={"name": "AMEX", "type": "CREDIT_CARD"}).json()
    cut = _cut(client, headers, caja).json()
    _count(client, headers, cut["id"], "1000")
    assert _deliver(client, headers, cut["id"], "100", tarjeta["id"]).status_code == 400
    assert _deliver(client, headers, cut["id"], "100", caja["id"]).status_code == 400


def test_receipt_is_confirmed_by_someone_else_or_an_admin(client):
    headers, caja, central, cats = _setup(client)
    cajero = _member_headers(client, headers, email="cajero@example.com", role="MEMBER")
    abraham = _member_headers(client, headers, email="abraham@example.com", role="MEMBER")

    cut = _cut(client, cajero, caja).json()
    _count(client, cajero, cut["id"], "1000")
    assert client.post(f"/api/cash-cuts/{cut['id']}/confirm-receipt", headers=cajero).status_code == 400
    _deliver(client, cajero, cut["id"], "1000", central["id"])

    # El cajero no confirma lo que él mismo entregó.
    response = client.post(f"/api/cash-cuts/{cut['id']}/confirm-receipt", headers=cajero)
    assert response.status_code == 403
    response = client.post(f"/api/cash-cuts/{cut['id']}/confirm-receipt", headers=abraham)
    assert response.status_code == 200, response.text
    assert response.json()["received_by_name"] == "Cajero"
    assert response.json()["received_at"] is not None
    assert client.post(f"/api/cash-cuts/{cut['id']}/confirm-receipt", headers=headers).status_code == 400

    # El dueño sí puede confirmar su propia entrega.
    other = _cut(client, headers, central).json()
    _count(client, headers, other["id"], "1000")
    _deliver(client, headers, other["id"], "1000", caja["id"])
    assert client.post(f"/api/cash-cuts/{other['id']}/confirm-receipt", headers=headers).status_code == 200


# --- Cancelar, filtros, permisos ----------------------------------------------------


def test_cancelling_a_delivered_cut_reverses_delivery_and_adjustment(client):
    headers, caja, central, cats = _setup(client)
    before = _balances(client, headers)
    cut = _cut(client, headers, caja).json()
    _count(client, headers, cut["id"], "980", explanation="Faltante")
    _deliver(client, headers, cut["id"], "980", central["id"])
    assert _account(client, headers, caja["id"])["current_balance"] == "0.00"

    response = client.delete(f"/api/cash-cuts/{cut['id']}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLED"
    assert _account(client, headers, caja["id"])["current_balance"] == "1000.00"
    assert _account(client, headers, central["id"])["current_balance"] == "0.00"
    after = _balances(client, headers)
    assert {k: v for k, v in after.items() if v} == {k: v for k, v in before.items() if v}
    assert client.delete(f"/api/cash-cuts/{cut['id']}", headers=headers).status_code == 400
    # El día queda libre para un corte nuevo, con el esperado limpio.
    again = _cut(client, headers, caja).json()
    assert again["expected_closing"] == "1000.00"
    assert again["inflows"] == "0.00" and again["outflows"] == "0.00"


def test_list_filters_by_account_status_and_unit(client):
    headers, caja, central, cats = _setup(client)
    unit = client.post("/api/business-units", headers=headers, json={"name": "Morelos"}).json()
    client.patch(f"/api/accounts/{caja['id']}", headers=headers, json={"business_unit_id": unit["id"]})
    cut = _cut(client, headers, caja).json()
    assert cut["business_unit_name"] == "Morelos"
    _cut(client, headers, central)

    page = client.get("/api/cash-cuts", headers=headers).json()
    assert page["total"] == 2
    assert client.get(f"/api/cash-cuts?account_id={caja['id']}", headers=headers).json()["total"] == 1
    assert client.get(f"/api/cash-cuts?business_unit_id={unit['id']}", headers=headers).json()["total"] == 1
    _count(client, headers, cut["id"], "1000")
    assert client.get("/api/cash-cuts?status=COUNTED", headers=headers).json()["total"] == 1
    assert client.get(f"/api/cash-cuts/{cut['id']}", headers=headers).json()["status"] == "COUNTED"


def test_cuts_respect_tenant_and_roles(client):
    headers, caja, central, cats = _setup(client)
    cut = _cut(client, headers, caja).json()
    other = auth_headers(register(client, email="otra@example.com", initial_cash="0"))
    assert client.get(f"/api/cash-cuts/{cut['id']}", headers=other).status_code == 404
    assert _count(client, other, cut["id"], "1000").status_code == 404
    assert _cut(client, other, caja).status_code == 404
    assert client.get("/api/cash-cuts", headers=other).json()["total"] == 0
    assert all(row["cut"] is None for row in client.get("/api/cash-cuts/today", headers=other).json())

    cajero = _member_headers(client, headers, email="cajero@example.com", role="MEMBER")
    assert client.delete(f"/api/cash-cuts/{cut['id']}", headers=cajero).status_code == 403
    assert _count(client, cajero, cut["id"], "1000").status_code == 200


def test_closed_month_blocks_count_and_delivery(client):
    headers, caja, central, cats = _setup(client)
    end = date.today().replace(day=1) - timedelta(days=1)
    when = end.replace(day=15)
    cut = _cut(client, headers, caja, when=when).json()
    close = client.post("/api/periods/close", headers=headers, json={"year": end.year, "month": end.month})
    assert close.status_code in (200, 201), close.text

    response = _count(client, headers, cut["id"], "900", explanation="Faltante")
    assert response.status_code == 400
    assert "cerrado" in response.json()["detail"].lower()
    # Sin diferencia no hay póliza, así que sí se puede contar...
    assert _count(client, headers, cut["id"], "1000").status_code == 200
    # ...pero la entrega es un traspaso y el candado la detiene.
    response = _deliver(client, headers, cut["id"], "1000", central["id"])
    assert response.status_code == 400
    assert "cerrado" in response.json()["detail"].lower()
