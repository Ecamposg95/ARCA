from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client, email="dueno@example.com", business="Mi Changarro"):
    body = register(client, email=email, business=business, initial_cash="10000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]
    categories = client.get("/api/categories?kind=INCOME", headers=headers).json()
    ventas = next(c for c in categories if c["name"] == "Ventas")
    return headers, account, ventas


def _create_key(client, headers, scopes="READ,PROPOSE"):
    response = client.post("/api/agent-keys", headers=headers, json={"name": "Agente Test", "scopes": scopes})
    assert response.status_code == 201, response.text
    return response.json()


def _agent_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_key_created_shows_token_once_and_never_again(client):
    headers, _account, _ventas = _setup(client)
    created = _create_key(client, headers)
    assert created["token"].startswith("ak_")
    listing = client.get("/api/agent-keys", headers=headers).json()
    assert len(listing) == 1
    assert "token" not in listing[0]
    assert listing[0]["key_prefix"] == created["token"][:12]


def test_invalid_and_revoked_keys_rejected(client):
    headers, _account, _ventas = _setup(client)
    response = client.get("/api/agent/tools", headers=_agent_headers("ak_" + "0" * 40))
    assert response.status_code == 401

    created = _create_key(client, headers)
    client.delete(f"/api/agent-keys/{created['id']}", headers=headers)
    response = client.get("/api/agent/tools", headers=_agent_headers(created["token"]))
    assert response.status_code == 401


def test_tools_discovery_filtered_by_scope(client):
    headers, _account, _ventas = _setup(client)
    read_key = _create_key(client, headers, scopes="READ")
    tools = client.get("/api/agent/tools", headers=_agent_headers(read_key["token"])).json()["tools"]
    names = {tool["name"] for tool in tools}
    assert "dashboard_summary" in names
    assert "propose_income" not in names


def test_read_scope_cannot_propose(client):
    headers, account, ventas = _setup(client)
    read_key = _create_key(client, headers, scopes="READ")
    response = client.post(
        "/api/agent/invoke",
        headers=_agent_headers(read_key["token"]),
        json={
            "tool": "propose_income",
            "arguments": {
                "date": "2026-08-24",
                "description": "Venta agente",
                "amount": "100",
                "category_id": ventas["id"],
                "summary": "venta detectada",
            },
        },
    )
    assert response.status_code == 403


def test_agent_reads_only_its_own_org(client):
    headers_a, _account_a, _ventas_a = _setup(client, email="a@example.com", business="Org A")
    headers_b, _account_b, _ventas_b = _setup(client, email="b@example.com", business="Org B")
    client.post("/api/customers", headers=headers_b, json={"name": "Cliente Secreto B"})

    key_a = _create_key(client, headers_a)
    result = client.post(
        "/api/agent/invoke",
        headers=_agent_headers(key_a["token"]),
        json={"tool": "list_customers", "arguments": {}},
    ).json()
    assert result["ok"] is True
    assert all("Secreto" not in row["name"] for row in result["result"])


def test_propose_creates_proposal_not_operation(client):
    headers, account, ventas = _setup(client)
    key = _create_key(client, headers)
    result = client.post(
        "/api/agent/invoke",
        headers=_agent_headers(key["token"]),
        json={
            "tool": "propose_income",
            "arguments": {
                "date": "2026-08-24",
                "description": "Venta detectada por agente",
                "amount": "1500",
                "category_id": ventas["id"],
                "financial_account_id": account["id"],
                "status": "PAID",
                "summary": "Venta de mostrador detectada en corte",
            },
        },
    ).json()
    assert result["ok"] is True

    # No se creó ingreso ni movió saldo
    incomes = client.get("/api/income", headers=headers).json()
    assert incomes["total"] == 0
    balance = client.get(f"/api/accounts/{account['id']}", headers=headers).json()["current_balance"]
    assert balance == "10000.00"
    proposals = client.get("/api/proposals?status=PROPOSED", headers=headers).json()
    assert proposals["total"] == 1
    assert proposals["items"][0]["agent_name"] == "Agente Test"


def test_approve_executes_real_operation_with_ledger(client):
    headers, account, ventas = _setup(client)
    key = _create_key(client, headers)
    proposal_id = client.post(
        "/api/agent/invoke",
        headers=_agent_headers(key["token"]),
        json={
            "tool": "propose_income",
            "arguments": {
                "date": "2026-08-24",
                "description": "Venta aprobada",
                "amount": "1500",
                "category_id": ventas["id"],
                "financial_account_id": account["id"],
                "status": "PAID",
                "summary": "Venta por aprobar",
            },
        },
    ).json()["result"]["proposal_id"]

    approved = client.post(f"/api/proposals/{proposal_id}/approve", headers=headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["result_id"]

    balance = client.get(f"/api/accounts/{account['id']}", headers=headers).json()["current_balance"]
    assert balance == "11500.00"
    trial = client.get("/api/accounting/trial-balance", headers=headers).json()
    assert Decimal(str(trial["total_debit"])) == Decimal(str(trial["total_credit"]))

    # No se puede aprobar dos veces
    again = client.post(f"/api/proposals/{proposal_id}/approve", headers=headers)
    assert again.status_code == 400


def test_reject_changes_nothing(client):
    headers, account, ventas = _setup(client)
    key = _create_key(client, headers)
    proposal_id = client.post(
        "/api/agent/invoke",
        headers=_agent_headers(key["token"]),
        json={
            "tool": "propose_expense",
            "arguments": {
                "date": "2026-08-24",
                "description": "Gasto dudoso",
                "amount": "999",
                "category_id": next(
                    c["id"]
                    for c in client.get("/api/categories?kind=EXPENSE", headers=headers).json()
                    if c["name"] == "Otros"
                ),
                "summary": "Cargo no identificado",
            },
        },
    ).json()["result"]["proposal_id"]

    rejected = client.post(
        f"/api/proposals/{proposal_id}/reject", headers=headers, json={"reason": "No lo reconozco"}
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    expenses = client.get("/api/expenses", headers=headers).json()
    assert expenses["total"] == 0
    balance = client.get(f"/api/accounts/{account['id']}", headers=headers).json()["current_balance"]
    assert balance == "10000.00"


def test_every_invocation_logged(client, db):
    from app.models.agent import AgentActionLog

    headers, _account, _ventas = _setup(client)
    key = _create_key(client, headers, scopes="READ")
    client.post(
        "/api/agent/invoke",
        headers=_agent_headers(key["token"]),
        json={"tool": "dashboard_summary", "arguments": {}},
    )
    client.post(
        "/api/agent/invoke",
        headers=_agent_headers(key["token"]),
        json={"tool": "propose_income", "arguments": {}},
    )
    logs = db.query(AgentActionLog).filter(AgentActionLog.agent_key_id == key["id"]).all()
    assert len(logs) == 2
    assert any(log.success for log in logs)
    assert any(not log.success for log in logs)


def test_key_management_requires_admin(client, db):
    from app.models.organization import OrganizationMember, ROLE_MEMBER
    from app.models.user import User
    from app.security.passwords import hash_password
    from app.security.tokens import create_access_token

    body = register(client)
    org_id = body["organization"]["id"]
    member = User(email="member@example.com", password_hash=hash_password("supersegura123"), name="Member")
    db.add(member)
    db.flush()
    db.add(OrganizationMember(organization_id=org_id, user_id=member.id, role=ROLE_MEMBER))
    db.commit()

    response = client.post(
        "/api/agent-keys",
        headers={
            "Authorization": f"Bearer {create_access_token(member.id)}",
            "X-Organization-ID": org_id,
        },
        json={"name": "no debería", "scopes": "READ"},
    )
    assert response.status_code == 403


def _propose(client, key_token, ventas, account, summary="Propuesta para polling"):
    result = client.post(
        "/api/agent/invoke",
        headers=_agent_headers(key_token),
        json={
            "tool": "propose_income",
            "arguments": {
                "date": "2026-08-24",
                "description": "Ingreso propuesto",
                "amount": "1000",
                "category_id": ventas["id"],
                "financial_account_id": account["id"],
                "status": "PAID",
                "summary": summary,
            },
        },
    ).json()
    assert result["ok"] is True
    return result["result"]["proposal_id"]


def test_agent_can_poll_its_proposal_status(client):
    """C-2: Cortex necesita saber si su propuesta fue aprobada, por la misma llave."""
    headers, account, ventas = _setup(client)
    key = _create_key(client, headers)
    proposal_id = _propose(client, key["token"], ventas, account)

    status = client.get(
        f"/api/agent/proposal-status/{proposal_id}", headers=_agent_headers(key["token"])
    )
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["id"] == proposal_id
    assert body["status"] == "PROPOSED"
    assert body["summary"] == "Propuesta para polling"
    assert body["resolved_at"] is None

    # Tras la aprobación humana, el agente ve el cambio y la fecha de resolución.
    client.post(f"/api/proposals/{proposal_id}/approve", headers=headers)
    body = client.get(
        f"/api/agent/proposal-status/{proposal_id}", headers=_agent_headers(key["token"])
    ).json()
    assert body["status"] == "APPROVED"
    assert body["resolved_at"] is not None


def test_proposal_status_is_tenant_isolated(client):
    headers_a, account_a, ventas_a = _setup(client)
    key_a = _create_key(client, headers_a)
    proposal_id = _propose(client, key_a["token"], ventas_a, account_a)

    # Otra organización con su propia llave no puede ver la propuesta ajena.
    headers_b, _account_b, _ventas_b = _setup(client, email="otra@example.com", business="Otra")
    key_b = _create_key(client, headers_b)
    response = client.get(
        f"/api/agent/proposal-status/{proposal_id}", headers=_agent_headers(key_b["token"])
    )
    assert response.status_code == 404


def test_read_only_key_can_poll_status(client):
    """Consultar el estado no es escribir: una llave READ puede hacer polling."""
    headers, account, ventas = _setup(client)
    proposer = _create_key(client, headers)
    proposal_id = _propose(client, proposer["token"], ventas, account)

    reader = _create_key(client, headers, scopes="READ")
    response = client.get(
        f"/api/agent/proposal-status/{proposal_id}", headers=_agent_headers(reader["token"])
    )
    assert response.status_code == 200
    assert response.json()["status"] == "PROPOSED"
