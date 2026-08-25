"""Servidor MCP de ARCA: expone las finanzas de una empresa a cualquier agente.

No conoce ninguna herramienta de memoria. Al arrancar le pregunta a ARCA qué
sabe hacer (`GET /api/agent/tools`) y publica exactamente eso. Cuando ARCA gana
un módulo, el agente lo ve sin tocar este archivo.

La llave de agente fija la organización y los permisos: un agente lee lo que su
llave permite y, para escribir, sólo puede PROPONER. La aprobación es humana y
ocurre en la bandeja de Propuestas.

Uso con Claude Code:

    claude mcp add arca \\
        --env ARCA_URL=https://arca-production-d769.up.railway.app \\
        --env ARCA_API_KEY=ak_... \\
        -- python tools/arca_mcp.py

Requiere `mcp>=2,<3` (ver requirements-dev.txt).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

ARCA_URL = os.environ.get("ARCA_URL", "http://localhost:8000").rstrip("/")
ARCA_API_KEY = os.environ.get("ARCA_API_KEY", "")

server: Server = Server("arca")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=f"{ARCA_URL}/api",
        headers={"Authorization": f"Bearer {ARCA_API_KEY}"},
        timeout=30,
    )


async def list_tools(_ctx, _params: PaginatedRequestParams | None) -> ListToolsResult:
    """El catálogo lo dicta ARCA, no este archivo."""
    async with _client() as http:
        response = await http.get("/agent/tools")
        response.raise_for_status()
        payload = response.json()

    return ListToolsResult(
        tools=[
            Tool(
                name=tool["name"],
                description=tool["description"],
                input_schema=tool["parameters"],
            )
            for tool in payload["tools"]
        ]
    )


async def call_tool(_ctx, params: CallToolRequestParams) -> CallToolResult:
    async with _client() as http:
        response = await http.post(
            "/agent/invoke",
            json={"tool": params.name, "arguments": params.arguments or {}},
        )

    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        # El mensaje de ARCA ya viene en lenguaje humano; se pasa tal cual.
        return CallToolResult(
            content=[TextContent(type="text", text=f"ARCA rechazó la operación: {detail}")],
            is_error=True,
        )

    result = response.json().get("result")
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    )


server.add_request_handler("tools/list", PaginatedRequestParams, list_tools)
server.add_request_handler("tools/call", CallToolRequestParams, call_tool)


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    if not ARCA_API_KEY:
        print("Falta ARCA_API_KEY (Configuración → Agentes en ARCA).", file=sys.stderr)
        sys.exit(1)
    asyncio.run(main())
