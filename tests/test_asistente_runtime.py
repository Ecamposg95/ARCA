"""Loop del asistente con cliente falso (spec 2026-11-02 §Runtime y §Pruebas).

Sin red: el cliente se inyecta y devuelve respuestas guionadas.
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.agent import AgentActionLog, AgentProposal
from app.models.assistant import AiUsage, AssistantAction, AssistantConversation
from app.models.organization import Organization, OrganizationMember
from app.models.user import User
from app.services.ai import runtime as R
from tests.helpers import auth_headers, register

HOY = date(2026, 11, 2)


def _text(t):
    return SimpleNamespace(type="text", text=t)


def _thinking(t="pensando", signature="sig123"):
    return SimpleNamespace(type="thinking", thinking=t, signature=signature)


def _tool_use(name, args, id="toolu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=args, id=id)


def _turn(content, stop_reason="tool_use", **usage):
    base = dict(input_tokens=1000, output_tokens=500, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    base.update(usage)
    return SimpleNamespace(content=content, stop_reason=stop_reason, usage=SimpleNamespace(**base))


class FakeAnthropic:
    def __init__(self, turns):
        self._turns, self.requests = list(turns), []

    @property
    def messages(self):
        return self

    def create(self, **kw):
        self.requests.append({**kw, "messages": [dict(m) for m in kw["messages"]]})
        if not self._turns:
            raise AssertionError("más turnos de los guionados")
        return self._turns.pop(0)


@pytest.fixture()
def world(client, db):
    """Empresa real sembrada por el registro, con sus objetos ORM a la mano."""
    body = register(client, initial_cash="10000")
    headers = auth_headers(body)
    org = db.get(Organization, body["organization"]["id"])
    user = db.get(User, body["user"]["id"])
    membership = db.query(OrganizationMember).filter_by(organization_id=org.id, user_id=user.id).one()
    account = client.get("/api/accounts", headers=headers).json()[0]
    categories = client.get("/api/categories?kind=EXPENSE", headers=headers).json()
    conv = AssistantConversation(organization_id=org.id, user_id=user.id)
    db.add(conv)
    db.commit()
    return SimpleNamespace(org=org, user=user, membership=membership, conv=conv, headers=headers,
                           account=account, category=categories[0], body=body)


def _run(db, w, text, fake, **kw):
    return R.run_turn(db, user=w.user, membership=w.membership, organization=w.org, conversation=w.conv,
                      user_text=text, client=fake, today=HOY, **kw)


def test_turno_de_solo_texto_y_forma_de_la_peticion(db, world):
    fake = FakeAnthropic([_turn([_thinking(), _text("Tienes **$10,000.00** disponibles.")], stop_reason="end_turn")])
    res = _run(db, world, "¿cuánto tengo?", fake)

    assert res.final.text == "Tienes **$10,000.00** disponibles."
    assert res.final.stop_reason == "end_turn" and res.final.role == "assistant"
    assert [m.role for m in world.conv.messages] == ["user", "assistant"]
    assert world.conv.title == "¿cuánto tengo?"
    # El bloque thinking se guarda tal cual, no sólo el texto.
    assert [b["type"] for b in res.final.blocks] == ["thinking", "text"]

    req = fake.requests[0]
    assert req["model"] == "claude-opus-5-5" and req["max_tokens"] == 16000
    assert req["thinking"] == {"type": "adaptive"} and req["output_config"] == {"effort": "medium"}
    assert "temperature" not in req and "top_p" not in req
    assert req["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "Hoy es" not in req["system"][0]["text"]            # el system es estable
    assert all(t["strict"] is True for t in req["tools"])
    assert all(t["input_schema"]["additionalProperties"] is False for t in req["tools"])
    assert req["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in req["tools"][0]
    first = req["messages"][0]
    assert first["role"] == "user"
    assert first["content"][0]["text"].startswith("Hoy es lunes 2026-11-02. Empresa: Mi Changarro. Usuario: Dueño (OWNER).")
    assert first["content"][1]["text"] == "¿cuánto tengo?"


def test_cada_llamada_registra_ai_usage_con_el_costo_de_la_tabla(db, world):
    fake = FakeAnthropic([
        _turn([_tool_use("list_accounts", {})], input_tokens=1000, output_tokens=500, cache_read_input_tokens=8000),
        _turn([_text("ok")], stop_reason="end_turn", input_tokens=100, output_tokens=10),
    ])
    res = _run(db, world, "saldos", fake)
    rows = db.query(AiUsage).filter_by(organization_id=world.org.id).order_by(AiUsage.created_at).all()
    assert len(rows) == 2
    assert rows[0].cost_usd == Decimal("0.015600")   # 1000*4 + 500*20 + 8000*0.20 / 1e6
    assert rows[1].cost_usd == Decimal("0.000600")
    assert rows[0].model == "claude-opus-5-5" and rows[0].user_id == world.user.id
    assert res.assistant_messages[0].cache_read_tokens == 8000
    assert res.final.cost_usd == Decimal("0.000600")


def test_dos_lecturas_en_paralelo_van_en_un_solo_tool_result(db, world):
    fake = FakeAnthropic([
        _turn([_text("Déjame ver."), _tool_use("list_accounts", {}, "tu_a"), _tool_use("list_payables", {"status": None}, "tu_b")]),
        _turn([_text("Listo.")], stop_reason="end_turn"),
    ])
    res = _run(db, world, "¿qué debo y cuánto tengo?", fake)

    assert res.final.text == "Listo."
    roles = [m.role for m in world.conv.messages]
    assert roles == ["user", "assistant", "user", "assistant"]
    tool_row = world.conv.messages[2]
    assert tool_row.text is None
    assert [b["type"] for b in tool_row.blocks] == ["tool_result", "tool_result"]
    assert [b["tool_use_id"] for b in tool_row.blocks] == ["tu_a", "tu_b"]
    assert not any(b.get("is_error") for b in tool_row.blocks)
    # Chips de pasos en el mensaje que llamó las herramientas.
    assert res.assistant_messages[0].steps == [
        {"name": "list_accounts", "ok": True, "summary": "Consulté saldos"},
        {"name": "list_payables", "ok": True, "summary": "Busqué por pagar"},
    ]
    # La segunda petición reenvía todo: user, assistant(tool_use), user(tool_result).
    msgs = fake.requests[1]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[2]["content"][0]["type"] == "tool_result"
    # Auditoría sin llave, como el usuario.
    logs = db.query(AgentActionLog).filter_by(organization_id=world.org.id).all()
    assert {log.tool for log in logs} == {"list_accounts", "list_payables"}
    assert all(log.agent_key_id is None and log.user_id == world.user.id and log.success for log in logs)


def test_propose_expense_crea_accion_y_propuesta_y_corta_el_turno(db, world):
    args = {
        "date": "2026-11-02", "description": "Papelería", "amount": "1200.00", "tax_rate": None,
        "category_id": world.category["id"], "financial_account_id": world.account["id"], "status": "PAID",
        "vendor_id": None, "project_id": None, "retention_isr": None, "retention_iva": None,
        "payment_method": None, "reference": None, "notes": None,
        "summary": "Gasto de papelería $1,200.00 de caja", "evidence": None,
    }
    fake = FakeAnthropic([_turn([_text("Voy a proponer el gasto."), _tool_use("propose_expense", args, "tu_p")])])
    res = _run(db, world, "registra un gasto de 1200 de papelería", fake)

    assert len(fake.requests) == 1                      # cortó el turno
    assert res.final.stop_reason == "proposal" and res.final.text == "Voy a proponer el gasto."
    action = db.query(AssistantAction).filter_by(conversation_id=world.conv.id).one()
    assert action.status == "PENDING" and action.tool_name == "propose_expense"
    assert action.summary == "Gasto de papelería $1,200.00 de caja" and action.message_id == res.final.id
    proposal = db.get(AgentProposal, action.proposal_id)
    assert proposal.kind == "EXPENSE" and proposal.status == "PROPOSED" and proposal.agent_key_id is None
    assert proposal.origin == f"assistant:{world.conv.id}:tu_p"
    assert proposal.payload["amount"] == "1200.00" and "summary" not in proposal.payload
    # El modelo recibió el tool_result de la propuesta y nada se escribió al libro.
    tool_row = world.conv.messages[-1]
    assert tool_row.blocks[0]["content"] == "Propuesta creada, pendiente de aprobación: Gasto de papelería $1,200.00 de caja"
    assert world.org.id and db.query(AgentProposal).count() == 1
    from app.models.expense import Expense

    assert db.query(Expense).filter_by(organization_id=world.org.id).count() == 0


def test_dos_propuestas_en_un_turno_solo_pasa_la_primera(db, world):
    args = {"date": "2026-11-02", "description": "A", "amount": "10", "category_id": world.category["id"],
            "summary": "A"}
    fake = FakeAnthropic([_turn([_tool_use("propose_expense", args, "t1"), _tool_use("propose_expense", {**args, "summary": "B"}, "t2")])])
    _run(db, world, "dos gastos", fake)
    assert db.query(AgentProposal).count() == 1
    results = world.conv.messages[-1].blocks
    assert results[1]["is_error"] is True and "una propuesta por turno" in results[1]["content"]


def test_argumentos_invalidos_vuelven_como_error_y_el_loop_sigue(db, world):
    fake = FakeAnthropic([
        _turn([_tool_use("aging_report", {"kind": "cualquiera"}, "t1")]),
        _turn([_tool_use("herramienta_inexistente", {}, "t2")]),
        _turn([_text("Corregido.")], stop_reason="end_turn"),
    ])
    res = _run(db, world, "cartera", fake)
    assert res.final.text == "Corregido."
    first = fake.requests[1]["messages"][-1]["content"][0]
    assert first["is_error"] is True and "Argumentos inválidos" in first["content"]
    second = fake.requests[2]["messages"][-1]["content"][0]
    assert second["is_error"] is True and "no existe" in second["content"]
    logs = db.query(AgentActionLog).filter_by(organization_id=world.org.id).all()
    assert [log.success for log in logs] == [False, False]


def test_max_tokens_y_refusal_producen_los_textos_definidos(db, world):
    fake = FakeAnthropic([_turn([_text("bla"), _tool_use("list_accounts", {}, "t")], stop_reason="max_tokens")])
    res = _run(db, world, "a", fake)
    assert res.final.text == R.TEXT_MAX_TOKENS and res.final.stop_reason == "max_tokens"
    assert db.query(AgentActionLog).count() == 0        # el tool_use truncado NO se ejecuta
    # El siguiente turno reenvía ese tool_use cerrado con un tool_result de cancelación:
    # sin él, el API rechaza el historial con 400.
    fake_next = FakeAnthropic([_turn([_text("sigo")], stop_reason="end_turn")])
    _run(db, world, "otra", fake_next)
    msgs = fake_next.requests[0]["messages"]
    cierre = msgs[2]["content"]
    assert msgs[1]["content"][1]["type"] == "tool_use" and msgs[2]["role"] == "user"
    assert cierre[0]["type"] == "tool_result" and cierre[0]["tool_use_id"] == "t" and cierre[0]["is_error"] is True
    assert msgs[3]["content"][1]["text"] == "otra"

    fake = FakeAnthropic([_turn([], stop_reason="refusal")])
    res = _run(db, world, "b", fake)
    assert res.final.text == R.TEXT_REFUSAL and res.final.stop_reason == "refusal"


def test_tope_de_iteraciones(db, world):
    fake = FakeAnthropic([_turn([_tool_use("list_accounts", {}, f"t{i}")]) for i in range(3)])
    res = _run(db, world, "loop", fake, max_iterations=3)
    assert res.final.text == R.TEXT_ITERATIONS and res.final.stop_reason == "max_iterations"


def test_presupuesto_agotado_no_llama_al_cliente(db, world):
    world.org.ai_budget_usd = Decimal("0.005")
    db.commit()
    fake = FakeAnthropic([_turn([_text("nunca")], stop_reason="end_turn")])
    res = _run(db, world, "hola", fake)
    assert fake.requests == []
    assert res.final.stop_reason == "budget"
    assert res.final.text.startswith("Se agotó el presupuesto del asistente de este mes (0.00 de 0.01 USD)")


def test_historial_se_reenvia_integro_con_thinking(db, world):
    fake = FakeAnthropic([_turn([_thinking("t1", "s1"), _text("Primera.")], stop_reason="end_turn")])
    _run(db, world, "uno", fake)
    fake2 = FakeAnthropic([_turn([_text("Segunda.")], stop_reason="end_turn")])
    _run(db, world, "dos", fake2)
    msgs = fake2.requests[0]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[1]["content"] == [{"type": "thinking", "thinking": "t1", "signature": "s1"}, {"type": "text", "text": "Primera."}]
    assert msgs[2]["content"][1]["text"] == "dos"


def test_las_herramientas_no_cruzan_de_empresa(db, world, client):
    other = register(client, email="b@example.com", business="Org B")
    client.post("/api/customers", headers=auth_headers(other), json={"name": "Cliente Secreto B"})
    fake = FakeAnthropic([
        _turn([_tool_use("list_customers", {"q": None}, "t")]),
        _turn([_text("fin")], stop_reason="end_turn"),
    ])
    _run(db, world, "clientes", fake)
    content = fake.requests[1]["messages"][-1]["content"][0]["content"]
    assert "Secreto" not in content


def test_viewer_no_puede_proponer(db, world):
    world.membership.role = "VIEWER"
    db.commit()
    fake = FakeAnthropic([_turn([_text("x")], stop_reason="end_turn")])
    _run(db, world, "hola", fake)
    names = {t["name"] for t in fake.requests[0]["tools"]}
    assert "list_accounts" in names and "propose_expense" not in names
    outcome = R.execute_tool(db, organization_id=world.org.id, user=world.user, role="VIEWER",
                             name="propose_expense", raw_input={}, origin="x")
    assert not outcome.ok and "autorización" in outcome.content


def test_titulo_se_deriva_del_primer_mensaje():
    assert R.derive_title("  ¿Qué   vence\nesta semana?  ") == "¿Qué vence esta semana?"
    assert R.derive_title("x" * 100).endswith("…") and len(R.derive_title("x" * 100)) == 80
