"""Endpoints del asistente (spec 2026-11-02 §API y §Pruebas): sin llave, cliente
falso inyectado por dependencia, aprobación real, aislamiento y presupuesto."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domains.assistant.router import get_ai_client
from app.main import app as fastapi_app
from app.models.agent import AgentProposal
from app.models.assistant import AssistantConversation
from tests.helpers import auth_headers, register
from tests.test_asistente_runtime import FakeAnthropic, _text, _tool_use, _turn


@pytest.fixture(autouse=True)
def _sin_llave(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture()
def fake():
    """Un cliente falso por prueba; cada prueba le guiona sus turnos."""
    holder = FakeAnthropic([])
    fastapi_app.dependency_overrides[get_ai_client] = lambda: holder
    yield holder
    fastapi_app.dependency_overrides.pop(get_ai_client, None)


def _setup(client, email="dueno@example.com", business="Mi Changarro"):
    body = register(client, email=email, business=business, initial_cash="10000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    category = client.get("/api/categories?kind=EXPENSE", headers=headers).json()[0]
    return headers, account, category, body


def _new_conversation(client, headers) -> str:
    response = client.post("/api/assistant/conversations", headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_sin_llave_status_no_disponible_y_mensajes_503(client):
    headers, *_ = _setup(client)
    status = client.get("/api/assistant/status", headers=headers).json()
    assert status == {
        "available": False, "reason": "sin_llave", "model": "claude-opus-5-5", "model_name": "Claude Opus 5.5",
        "budget_usd": "20", "spent_usd": "0.000000", "remaining_usd": "20.000000",
    }
    conv_id = _new_conversation(client, headers)
    response = client.post(f"/api/assistant/conversations/{conv_id}/messages", headers=headers, json={"text": "hola"})
    assert response.status_code == 503
    assert response.json()["detail"] == "El asistente se activa cuando se conecte la llave de Claude."
    # Nada se persistió.
    detail = client.get(f"/api/assistant/conversations/{conv_id}", headers=headers).json()
    assert detail["messages"] == [] and detail["busy"] is False


def test_con_llave_el_status_es_disponible(client, fake, monkeypatch):
    headers, *_ = _setup(client)
    # El status mira la llave, no el cliente inyectado: sin llave sigue "sin_llave".
    assert client.get("/api/assistant/status", headers=headers).json()["reason"] == "sin_llave"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-prueba")
    status = client.get("/api/assistant/status", headers=headers).json()
    assert status["available"] is True and status["reason"] is None
    client.patch("/api/organizations/current", headers=headers, json={"ai_enabled": False})
    assert client.get("/api/assistant/status", headers=headers).json()["reason"] == "deshabilitado"


def test_turno_de_texto_por_api_y_listado(client, fake):
    headers, *_ = _setup(client)
    conv_id = _new_conversation(client, headers)
    fake._turns = [_turn([_text("Hola, ¿qué revisamos?")], stop_reason="end_turn")]
    response = client.post(f"/api/assistant/conversations/{conv_id}/messages", headers=headers, json={"text": "hola"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["role"] == "assistant" and body["text"] == "Hola, ¿qué revisamos?"
    assert body["steps"] == [] and body["actions"] == [] and body["cost_usd"] == "0.014000"

    listing = client.get("/api/assistant/conversations", headers=headers).json()
    assert listing["total"] == 1 and listing["items"][0]["title"] == "hola"
    assert set(listing) == {"items", "total", "limit", "offset"}

    detail = client.get(f"/api/assistant/conversations/{conv_id}", headers=headers).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][0]["text"] == "hola" and detail["busy"] is False


def test_tool_results_no_se_muestran_pero_los_pasos_si(client, fake):
    headers, *_ = _setup(client)
    conv_id = _new_conversation(client, headers)
    fake._turns = [
        _turn([_tool_use("list_accounts", {}, "t1")]),
        _turn([_text("Tienes $10,000.00 en Caja.")], stop_reason="end_turn"),
    ]
    client.post(f"/api/assistant/conversations/{conv_id}/messages", headers=headers, json={"text": "saldos"})
    detail = client.get(f"/api/assistant/conversations/{conv_id}", headers=headers).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "assistant"]
    assert detail["messages"][1]["steps"] == [{"name": "list_accounts", "ok": True, "summary": "Consulté saldos"}]


def test_propuesta_desde_el_chat_se_aprueba_y_el_gasto_existe(client, fake, db):
    headers, account, category, _ = _setup(client)
    conv_id = _new_conversation(client, headers)
    args = {"date": "2026-11-02", "description": "Papelería", "amount": "1200.00", "category_id": category["id"],
            "financial_account_id": account["id"], "status": "PAID", "summary": "Gasto de papelería $1,200.00"}
    fake._turns = [_turn([_text("Propongo el gasto."), _tool_use("propose_expense", args, "tp")])]
    body = client.post(f"/api/assistant/conversations/{conv_id}/messages", headers=headers, json={"text": "registra"}).json()
    assert body["stop_reason"] == "proposal" and len(body["actions"]) == 1
    action = body["actions"][0]
    assert action["status"] == "PENDING" and action["proposal_kind"] == "EXPENSE" and action["summary"] == "Gasto de papelería $1,200.00"
    # Aparece en la bandeja común, sin nombre de llave.
    proposals = client.get("/api/proposals?status=PROPOSED", headers=headers).json()
    assert proposals["total"] == 1

    approved = client.post(f"/api/assistant/actions/{action['id']}/approve", headers=headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED" and approved.json()["resolved_at"] is not None
    expenses = client.get("/api/expenses", headers=headers).json()
    assert expenses["total"] == 1 and expenses["items"][0]["amount"] == "1200.00"
    balance = client.get(f"/api/accounts/{account['id']}", headers=headers).json()["current_balance"]
    assert balance == "8800.00"
    assert db.get(AgentProposal, action["proposal_id"]).status == "APPROVED"
    # Segunda vez: 409.
    assert client.post(f"/api/assistant/actions/{action['id']}/approve", headers=headers).status_code == 409

    # El siguiente turno le cuenta al modelo que se ejecutó, con folio.
    fake._turns = [_turn([_text("Listo.")], stop_reason="end_turn")]
    client.post(f"/api/assistant/conversations/{conv_id}/messages", headers=headers, json={"text": "gracias"})
    context = fake.requests[-1]["messages"][-1]["content"][0]["text"]
    assert "fue aprobada y ejecutada (folio Eg-2026-11-0001)" in context


def test_rechazar_desde_el_chat(client, fake):
    headers, account, category, _ = _setup(client)
    conv_id = _new_conversation(client, headers)
    args = {"date": "2026-11-02", "description": "X", "amount": "10", "category_id": category["id"], "summary": "X"}
    fake._turns = [_turn([_tool_use("propose_expense", args, "tp")])]
    body = client.post(f"/api/assistant/conversations/{conv_id}/messages", headers=headers, json={"text": "r"}).json()
    rejected = client.post(f"/api/assistant/actions/{body['actions'][0]['id']}/reject", headers=headers)
    assert rejected.status_code == 200 and rejected.json()["status"] == "REJECTED"
    assert client.get("/api/proposals?status=REJECTED", headers=headers).json()["total"] == 1
    assert client.get("/api/expenses", headers=headers).json()["total"] == 0


def test_otra_empresa_y_otro_usuario_no_ven_la_conversacion(client, fake):
    headers_a, *_ = _setup(client, email="a@example.com", business="Org A")
    headers_b, *_ = _setup(client, email="b@example.com", business="Org B")
    conv_id = _new_conversation(client, headers_a)
    fake._turns = [_turn([_tool_use("propose_expense", {"date": "2026-11-02", "description": "X", "amount": "10",
                                                        "category_id": client.get("/api/categories?kind=EXPENSE", headers=headers_a).json()[0]["id"],
                                                        "summary": "X"}, "tp")])]
    body = client.post(f"/api/assistant/conversations/{conv_id}/messages", headers=headers_a, json={"text": "r"}).json()
    action_id = body["actions"][0]["id"]

    assert client.get(f"/api/assistant/conversations/{conv_id}", headers=headers_b).status_code == 404
    assert client.get("/api/assistant/conversations", headers=headers_b).json()["total"] == 0
    assert client.post(f"/api/assistant/conversations/{conv_id}/messages", headers=headers_b, json={"text": "x"}).status_code == 404
    assert client.post(f"/api/assistant/actions/{action_id}/approve", headers=headers_b).status_code == 404
    assert client.delete(f"/api/assistant/conversations/{conv_id}", headers=headers_b).status_code == 404
    assert client.get("/api/proposals?status=PROPOSED", headers=headers_b).json()["total"] == 0


def test_presupuesto_agotado_responde_402_sin_llamar(client, fake, monkeypatch):
    headers, *_ = _setup(client)
    patched = client.patch("/api/organizations/current", headers=headers, json={"ai_budget_usd": "0.01"})
    assert patched.status_code == 200 and patched.json()["ai_budget_usd"] == "0.01"
    conv_id = _new_conversation(client, headers)
    fake._turns = [_turn([_text("nunca")], stop_reason="end_turn")]
    response = client.post(f"/api/assistant/conversations/{conv_id}/messages", headers=headers, json={"text": "hola"})
    assert response.status_code == 402
    assert response.json()["detail"].startswith("Se agotó el presupuesto del asistente de este mes (0.00 de 0.01 USD)")
    assert fake.requests == []
    # Con llave presente el status explica el motivo real.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-prueba")
    status = client.get("/api/assistant/status", headers=headers).json()
    assert status["available"] is False and status["reason"] == "sin_presupuesto"
    assert client.get(f"/api/assistant/conversations/{conv_id}", headers=headers).json()["messages"] == []


def test_conversacion_ocupada_responde_409(client, fake, db):
    headers, *_ = _setup(client)
    conv_id = _new_conversation(client, headers)
    conv = db.get(AssistantConversation, conv_id)
    conv.busy_since = datetime.now(timezone.utc)
    db.commit()
    response = client.post(f"/api/assistant/conversations/{conv_id}/messages", headers=headers, json={"text": "hola"})
    assert response.status_code == 409 and fake.requests == []
    assert client.delete(f"/api/assistant/conversations/{conv_id}", headers=headers).status_code == 409
    # Un candado viejo (proceso caído) se libera solo.
    conv.busy_since = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.commit()
    fake._turns = [_turn([_text("ok")], stop_reason="end_turn")]
    assert client.post(f"/api/assistant/conversations/{conv_id}/messages", headers=headers, json={"text": "hola"}).status_code == 200
    assert client.delete(f"/api/assistant/conversations/{conv_id}", headers=headers).status_code == 204
    assert client.get(f"/api/assistant/conversations/{conv_id}", headers=headers).status_code == 404


def test_uso_del_mes_por_usuario_y_dia(client, fake):
    headers, *_ = _setup(client)
    conv_id = _new_conversation(client, headers)
    fake._turns = [_turn([_tool_use("list_accounts", {}, "t")]), _turn([_text("ok")], stop_reason="end_turn")]
    client.post(f"/api/assistant/conversations/{conv_id}/messages", headers=headers, json={"text": "hola"})
    usage = client.get("/api/assistant/usage", headers=headers).json()
    assert usage["calls"] == 2 and Decimal(usage["total_usd"]) == Decimal("0.028000")
    assert usage["by_user"][0]["label"] == "Dueño" and usage["by_user"][0]["calls"] == 2
    assert len(usage["by_day"]) == 1 and usage["budget_usd"] == "20"
    assert client.get("/api/assistant/usage?month=2020-01", headers=headers).json()["calls"] == 0
    assert client.get("/api/assistant/usage?month=enero", headers=headers).status_code == 422


def test_presupuesto_solo_lo_cambia_el_dueno(client):
    headers, *_ = _setup(client)
    invited = client.post("/api/organizations/current/members", headers=headers,
                          json={"email": "admin@example.com", "name": "Admin", "role": "ADMIN", "password": "supersegura123"})
    assert invited.status_code == 201, invited.text
    login = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "supersegura123"}).json()
    admin_headers = {"Authorization": f"Bearer {login['access_token']}", "X-Organization-ID": headers["X-Organization-ID"]}
    assert client.patch("/api/organizations/current", headers=admin_headers, json={"name": "Otro nombre"}).status_code == 200
    assert client.patch("/api/organizations/current", headers=admin_headers, json={"ai_budget_usd": "5"}).status_code == 403
    assert client.get("/api/assistant/usage", headers=admin_headers).status_code == 200
    toggled = client.patch("/api/organizations/current", headers=headers, json={"ai_enabled": False})
    assert toggled.json()["ai_enabled"] is False
