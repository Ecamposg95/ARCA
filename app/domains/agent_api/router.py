"""Superficie API para agentes: descubrimiento de herramientas e invocación.

Autenticación por llave de agente (organización fija). Toda invocación
queda en AgentActionLog, exitosa o no.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.agents.tools import TOOLS
from app.database import get_db
from app.models.agent import AgentActionLog, AgentProposal
from app.security.agent import AgentContext, get_agent_context

router = APIRouter(prefix="/agent", tags=["agent"])


class InvokeRequest(BaseModel):
    tool: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.get("/tools")
def list_tools(context: AgentContext = Depends(get_agent_context)):
    return {
        "organization_id": context.organization_id,
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "scope": tool.scope,
                "parameters": tool.params_model.model_json_schema(),
            }
            for tool in TOOLS.values()
            if tool.scope in context.scopes
        ],
    }


@router.get("/proposal-status/{proposal_id}")
def proposal_status(
    proposal_id: str,
    db: Session = Depends(get_db),
    context: AgentContext = Depends(get_agent_context),
):
    """Polling del agente sobre SU propuesta (C-2 de Cortex).

    Consultar el estado no es escribir, así que basta cualquier llave válida de
    la organización — pero sólo de la organización: una propuesta ajena es un
    404 indistinguible de "no existe".
    """
    proposal = (
        db.query(AgentProposal)
        .filter(
            AgentProposal.id == proposal_id,
            AgentProposal.organization_id == context.organization_id,
        )
        .first()
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="La propuesta no existe.")
    return {
        "id": proposal.id,
        "status": proposal.status,
        "summary": proposal.summary,
        "resolved_at": proposal.reviewed_at,
    }


@router.post("/invoke")
def invoke_tool(
    payload: InvokeRequest,
    db: Session = Depends(get_db),
    context: AgentContext = Depends(get_agent_context),
):
    tool = TOOLS.get(payload.tool)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"La herramienta '{payload.tool}' no existe.")
    if tool.scope not in context.scopes:
        _log(db, context, payload.tool, payload.arguments, False, "scope insuficiente", 0)
        raise HTTPException(status_code=403, detail=f"Esta llave no tiene el permiso {tool.scope}.")

    started = time.monotonic()
    try:
        params = tool.params_model.model_validate(payload.arguments)
    except ValidationError as exc:
        _log(db, context, payload.tool, payload.arguments, False, "argumentos inválidos", 0)
        raise HTTPException(
            status_code=400,
            detail="Argumentos inválidos: " + "; ".join(e["msg"] for e in exc.errors()[:5]),
        )

    try:
        if tool.needs_agent_key:
            result = tool.handler(db, context.organization_id, params, context.agent_key_id)
        else:
            result = tool.handler(db, context.organization_id, params)
        duration = int((time.monotonic() - started) * 1000)
        _log(db, context, payload.tool, payload.arguments, True, None, duration)
        return {"ok": True, "tool": payload.tool, "result": result}
    except ValueError as exc:
        duration = int((time.monotonic() - started) * 1000)
        _log(db, context, payload.tool, payload.arguments, False, str(exc)[:500], duration)
        raise HTTPException(status_code=400, detail=str(exc))


def _log(
    db: Session,
    context: AgentContext,
    tool: str,
    arguments: dict,
    success: bool,
    error: str | None,
    duration_ms: int,
) -> None:
    db.add(
        AgentActionLog(
            organization_id=context.organization_id,
            agent_key_id=context.agent_key_id,
            tool=tool,
            arguments=arguments,
            success=success,
            error=error,
            duration_ms=duration_ms,
        )
    )
    db.commit()
