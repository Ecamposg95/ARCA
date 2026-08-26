"""Catálogo de agentes: los reportes ricos que Cortex consume (C-1)."""

from tests.helpers import auth_headers, register


def test_agent_catalog_exposes_rich_reports(client):
    """C-1 de Cortex pidió estos tres: sin ellos, el brief del CFO se arma a mano."""
    body = register(client, email="catalogo@example.com", initial_cash="50000")
    headers = auth_headers(body)
    key = client.post(
        "/api/agent-keys", headers=headers, json={"name": "Cortex", "scopes": "READ"}
    ).json()
    agent = {"Authorization": f"Bearer {key['token']}"}

    tools = {t["name"] for t in client.get("/api/agent/tools", headers=agent).json()["tools"]}
    assert {"aging_report", "cash_projection", "net_worth"} <= tools

    aging = client.post(
        "/api/agent/invoke", headers=agent, json={"tool": "aging_report", "arguments": {}}
    )
    assert aging.status_code == 200
    assert "average_days" in aging.json()["result"]

    projection = client.post(
        "/api/agent/invoke",
        headers=agent,
        json={"tool": "cash_projection", "arguments": {"days": 30}},
    )
    assert projection.status_code == 200
    assert "projected_cash" in projection.json()["result"]

    worth = client.post(
        "/api/agent/invoke", headers=agent, json={"tool": "net_worth", "arguments": {}}
    )
    assert worth.status_code == 200
    assert "net_worth" in worth.json()["result"]
