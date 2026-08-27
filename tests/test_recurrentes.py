"""Recurrentes (F-03): lo que se paga igual cada mes, ARCA lo propone solo.

El borrador es una propuesta más de la bandeja: la aprobación humana sigue
siendo el único camino a la contabilidad, y la generación es idempotente por
(regla, mes) — el patrón de la depreciación.
"""

from datetime import date
from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client, email="dueno@example.com"):
    body = register(client, email=email, initial_cash="200000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    renta = next(
        c
        for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json()
        if c["name"] == "Renta"
    )
    servicios = next(
        c
        for c in client.get("/api/categories?kind=INCOME", headers=headers).json()
        if c["name"] == "Servicios"
    )
    return headers, account, renta, servicios


def _rule(client, headers, categoria, account=None, **overrides):
    payload = {
        "kind": "EXPENSE",
        "description": "Renta coworking",
        "amount": "18560",
        "tax_rate": "0.16",
        "category_id": categoria["id"],
        "day_of_month": 1,
    }
    if account:
        payload["financial_account_id"] = account["id"]
    payload.update(overrides)
    return client.post("/api/recurring", headers=headers, json=payload)


def _generate(client, headers, when: date | None = None):
    when = when or date.today()
    return client.post(
        "/api/recurring/generate",
        headers=headers,
        json={"year": when.year, "month": when.month},
    )


def test_rule_creates_and_lists_with_canonical_envelope(client):
    headers, account, renta, _servicios = _setup(client)
    created = _rule(client, headers, renta, account)
    assert created.status_code == 201, created.text

    body = client.get("/api/recurring", headers=headers).json()
    assert {"items", "total", "limit", "offset"} <= set(body.keys())
    assert body["total"] == 1
    assert body["items"][0]["description"] == "Renta coworking"
    assert body["items"][0]["status"] == "ACTIVE"


def test_generation_drops_a_draft_in_the_inbox(client):
    headers, account, renta, _servicios = _setup(client)
    _rule(client, headers, renta, account)

    result = _generate(client, headers).json()
    assert result["generated"] == 1

    inbox = client.get("/api/proposals?status=PROPOSED", headers=headers).json()
    assert inbox["total"] == 1
    draft = inbox["items"][0]
    assert draft["kind"] == "EXPENSE"
    assert draft["agent_name"] == "ARCA · Recurrentes"
    assert Decimal(str(draft["payload"]["amount"])) == Decimal("18560")


def test_generation_is_idempotent_per_month(client):
    headers, account, renta, _servicios = _setup(client)
    _rule(client, headers, renta, account)

    first = _generate(client, headers).json()
    second = _generate(client, headers).json()
    assert first["generated"] == 1
    assert second["generated"] == 0

    inbox = client.get("/api/proposals?status=PROPOSED", headers=headers).json()
    assert inbox["total"] == 1


def test_a_rejected_draft_is_not_regenerated(client):
    """Rechazar el borrador de un mes es una decisión: regenerar no la deshace."""
    headers, account, renta, _servicios = _setup(client)
    _rule(client, headers, renta, account)
    _generate(client, headers)

    draft = client.get("/api/proposals?status=PROPOSED", headers=headers).json()["items"][0]
    client.post(
        f"/api/proposals/{draft['id']}/reject",
        headers=headers,
        json={"reason": "Este mes no se paga"},
    )

    again = _generate(client, headers).json()
    assert again["generated"] == 0


def test_paused_rules_do_not_generate(client):
    headers, account, renta, _servicios = _setup(client)
    rule = _rule(client, headers, renta, account).json()
    client.patch(f"/api/recurring/{rule['id']}", headers=headers, json={"status": "PAUSED"})

    result = _generate(client, headers).json()
    assert result["generated"] == 0


def test_future_months_are_rejected(client):
    headers, account, renta, _servicios = _setup(client)
    _rule(client, headers, renta, account)
    today = date.today()
    index = today.year * 12 + today.month  # mes siguiente
    year, month = divmod(index, 12)
    response = client.post(
        "/api/recurring/generate", headers=headers, json={"year": year, "month": month + 1}
    )
    assert response.status_code == 400
    assert "todavía" in response.json()["detail"]


def test_pending_counts_rules_not_yet_generated(client):
    headers, account, renta, servicios = _setup(client)
    _rule(client, headers, renta, account)
    _rule(
        client,
        headers,
        servicios,
        account,
        kind="INCOME",
        description="Iguala mensual",
        amount="34800",
        day_of_month=5,
    )

    today = date.today()
    pending = client.get(
        f"/api/recurring/pending?year={today.year}&month={today.month}", headers=headers
    ).json()
    assert pending["pending"] == 2

    _generate(client, headers)
    pending = client.get(
        f"/api/recurring/pending?year={today.year}&month={today.month}", headers=headers
    ).json()
    assert pending["pending"] == 0


def test_approving_the_draft_creates_the_real_operation(client):
    """El ciclo completo: regla → borrador → aprobación humana → contabilidad."""
    headers, account, renta, _servicios = _setup(client)
    _rule(client, headers, renta, account)
    _generate(client, headers)

    draft = client.get("/api/proposals?status=PROPOSED", headers=headers).json()["items"][0]
    approved = client.post(f"/api/proposals/{draft['id']}/approve", headers=headers)
    assert approved.status_code == 200, approved.text

    expenses = client.get("/api/expenses", headers=headers).json()
    assert expenses["total"] == 1
    expense = expenses["items"][0]
    assert Decimal(str(expense["amount"])) == Decimal("18560")
    assert Decimal(str(expense["tax_amount"])) == Decimal("2560")
    # Con cuenta en la regla, el borrador se aprueba ya pagado desde esa cuenta.
    assert expense["status"] == "PAID"
    assert expense["financial_account_id"] == account["id"]

    balance = client.get("/api/accounting/trial-balance", headers=headers).json()
    assert Decimal(str(balance["total_debit"])) == Decimal(str(balance["total_credit"]))


def test_rule_without_account_generates_a_pending_draft(client):
    headers, _account, renta, _servicios = _setup(client)
    _rule(client, headers, renta, account=None)
    _generate(client, headers)

    draft = client.get("/api/proposals?status=PROPOSED", headers=headers).json()["items"][0]
    assert draft["payload"]["status"] == "PENDING"

    client.post(f"/api/proposals/{draft['id']}/approve", headers=headers)
    expense = client.get("/api/expenses", headers=headers).json()["items"][0]
    # Sin cuenta no hay movimiento de dinero: queda por pagar.
    assert expense["status"] == "PENDING"


def test_delete_only_before_first_generation(client):
    headers, account, renta, _servicios = _setup(client)
    fresh = _rule(client, headers, renta, account).json()
    assert client.delete(f"/api/recurring/{fresh['id']}", headers=headers).status_code == 204

    used = _rule(client, headers, renta, account, description="Otra renta").json()
    _generate(client, headers)
    response = client.delete(f"/api/recurring/{used['id']}", headers=headers)
    # Ya generó historia: no se borra, se pausa.
    assert response.status_code == 400
    assert "pausa" in response.json()["detail"].lower()


def test_recurring_rules_are_isolated_by_organization(client):
    headers_a, account_a, renta_a, _s = _setup(client)
    rule = _rule(client, headers_a, renta_a, account_a).json()

    headers_b, _account_b, _renta_b, _s2 = _setup(client, email="otra@example.com")
    assert client.get("/api/recurring", headers=headers_b).json()["items"] == []
    assert (
        client.patch(
            f"/api/recurring/{rule['id']}", headers=headers_b, json={"status": "PAUSED"}
        ).status_code
        == 404
    )
    # Generar en B no toca las reglas de A.
    assert _generate(client, headers_b).json()["generated"] == 0


def test_day_of_month_stays_within_safe_range(client):
    headers, account, renta, _servicios = _setup(client)
    response = _rule(client, headers, renta, account, day_of_month=31)
    # 1–28: la regla de la casa para no pelear con febrero.
    assert response.status_code == 422
