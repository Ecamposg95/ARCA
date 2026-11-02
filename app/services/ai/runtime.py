"""El loop del asistente (spec 2026-11-02 §Runtime). Calcado del agente de Atlas Cortex.

Loop manual, no el tool runner del SDK: cada `tool_use` pasa por el catálogo
autorizado de `app/agents/tools.py`, se valida contra su schema, se audita en
`AgentActionLog` y sólo entonces vuelve al modelo. El asistente corre COMO el
usuario logueado (membresía y rol), sin llave `ak_`. Las `propose_*` crean
`AgentProposal`; nunca se escribe al libro desde aquí.

`client` es inyectable: las pruebas usan uno falso con respuestas guionadas.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.agents.tools import TOOLS, ToolSpec
from app.config import get_settings
from app.models.accounting import JournalEntry
from app.models.agent import AgentActionLog, AgentProposal
from app.models.assistant import AiUsage, AssistantAction, AssistantConversation, AssistantMessage
from app.models.organization import WRITE_ROLES, Organization, OrganizationMember
from app.models.user import User
from app.services.ai import budget as budget_service
from app.services.ai.prompt import context_block, step_label, system_prompt
from app.services.ai.toolset import tool_specs, validate_input
from app.services.ai.pricing import cost_usd, usage_tokens

logger = logging.getLogger("arca.assistant")

MAX_ITERATIONS = 12
HISTORY_ROWS = 40
RESULT_CAP = 12000

TEXT_MAX_TOKENS = "Me quedé sin espacio; pregunta de nuevo más acotado."
TEXT_REFUSAL = "No puedo ayudar con eso."
TEXT_ITERATIONS = "No logré terminar; intenta con una pregunta más corta."
TEXT_PROPOSED = "Te propuse una operación; revísala en la tarjeta de abajo y decide."
STOP_BUDGET = "budget"
STOP_PROPOSAL = "proposal"
STOP_ITERATIONS = "max_iterations"


@dataclass
class ToolOutcome:
    name: str
    ok: bool
    content: str
    proposal: AgentProposal | None = None
    summary: str | None = None

    def as_result(self, tool_use_id: str) -> dict:
        block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": self.content}
        if not self.ok:
            block["is_error"] = True
        return block


@dataclass
class TurnResult:
    user_message: AssistantMessage
    assistant_messages: list[AssistantMessage] = field(default_factory=list)

    @property
    def final(self) -> AssistantMessage:
        return self.assistant_messages[-1]


# --- Utilidades ----------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def block_to_dict(block: Any) -> dict:
    """Los bloques del SDK son modelos pydantic; los falsos, SimpleNamespace o dicts.
    El dict resultante se reenvía al API tal cual (thinking incluido) y se persiste."""
    if isinstance(block, dict):
        return block
    if hasattr(block, "model_dump"):
        return block.model_dump(exclude_none=True)
    return {k: v for k, v in vars(block).items() if v is not None}


def _text_of(blocks: list[dict]) -> str:
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()


def _trim(text: str, cap: int = RESULT_CAP) -> str:
    return text if len(text) <= cap else text[:cap] + "… [recortado]"


def available_tools(role: str) -> list[ToolSpec]:
    """Lectura para todos; proponer sólo para quien podría registrar la operación."""
    return [t for t in TOOLS.values() if t.scope == "READ" or role in WRITE_ROLES]


def derive_title(text: str) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= 80 else clean[:79].rstrip() + "…"


def _next_seq(conversation: AssistantConversation) -> int:
    return max((m.seq for m in conversation.messages), default=-1) + 1


def _row(conversation: AssistantConversation, role: str, blocks: list[dict], text: str | None, **extra) -> AssistantMessage:
    row = AssistantMessage(
        conversation_id=conversation.id,
        organization_id=conversation.organization_id,
        seq=_next_seq(conversation),
        role=role,
        blocks=blocks,
        text=text,
        created_at=_now(),
        **extra,
    )
    conversation.messages.append(row)
    return row


def is_tool_result_row(row: AssistantMessage) -> bool:
    return row.role == "user" and row.text is None


def history_for_api(conversation: AssistantConversation, limit: int = HISTORY_ROWS) -> list[dict]:
    """Últimos N renglones; la ventana retrocede hasta empezar en un mensaje de
    usuario con texto (nunca en un tool_result huérfano)."""
    rows = list(conversation.messages)
    start = max(len(rows) - limit, 0)
    while start > 0 and (rows[start].role != "user" or is_tool_result_row(rows[start])):
        start -= 1
    return [{"role": r.role, "content": r.blocks} for r in rows[start:]]


def resolution_notes(db: Session, conversation: AssistantConversation) -> list[str]:
    """Propuestas resueltas después del último mensaje del usuario: el modelo se entera."""
    user_rows = [r for r in conversation.messages if r.role == "user" and not is_tool_result_row(r)]
    since = user_rows[-1].created_at if user_rows else None
    query = db.query(AssistantAction).filter(
        AssistantAction.conversation_id == conversation.id, AssistantAction.resolved_at.isnot(None)
    )
    if since is not None:
        query = query.filter(AssistantAction.resolved_at >= since)
    notes = []
    for action in query.order_by(AssistantAction.resolved_at).all():
        if action.status == "APPROVED":
            folio = _folio_for(db, conversation.organization_id, action.proposal_id)
            suffix = f" (folio {folio})" if folio else ""
            notes.append(f"La propuesta «{action.summary}» fue aprobada y ejecutada{suffix}.")
        elif action.status == "REJECTED":
            notes.append(f"La propuesta «{action.summary}» fue rechazada por el usuario; no se registró.")
    return notes


def _folio_for(db: Session, org_id: str, proposal_id: str | None) -> str | None:
    if not proposal_id:
        return None
    proposal = db.get(AgentProposal, proposal_id)
    if proposal is None or not proposal.result_id:
        return None
    entry = (
        db.query(JournalEntry)
        .filter(JournalEntry.organization_id == org_id, JournalEntry.source_id == proposal.result_id)
        .order_by(JournalEntry.created_at)
        .first()
    )
    return entry.folio if entry else None


# --- Ejecución de herramientas -------------------------------------------


def execute_tool(
    db: Session,
    *,
    organization_id: str,
    user: User,
    role: str,
    name: str,
    raw_input: Any,
    origin: str,
) -> ToolOutcome:
    """Valida, despacha por el catálogo, audita. Un error nunca tumba el turno:
    vuelve al modelo como tool_result con is_error."""
    started = time.monotonic()
    tool = TOOLS.get(name)
    if tool is None:
        return _audited(db, organization_id, user, name, raw_input, ToolOutcome(name, False, f"Error: la herramienta '{name}' no existe."), started)
    if tool.scope == "PROPOSE" and role not in WRITE_ROLES:
        return _audited(db, organization_id, user, name, raw_input,
                        ToolOutcome(name, False, "Error de autorización: tu rol no permite proponer operaciones."), started)
    try:
        params = validate_input(tool, raw_input)
    except ValueError as exc:
        return _audited(db, organization_id, user, name, raw_input, ToolOutcome(name, False, f"Error: {exc}"), started)

    try:
        if tool.needs_agent_key:
            result = tool.handler(db, organization_id, params, None)
            proposal = db.get(AgentProposal, result["proposal_id"])
            proposal.origin = origin
            db.commit()
            outcome = ToolOutcome(
                name, True, f"Propuesta creada, pendiente de aprobación: {proposal.summary}",
                proposal=proposal, summary=proposal.summary,
            )
        else:
            result = tool.handler(db, organization_id, params)
            outcome = ToolOutcome(name, True, _trim(json.dumps(result, ensure_ascii=False, default=str)))
    except ValueError as exc:
        db.rollback()
        outcome = ToolOutcome(name, False, f"Error: {exc}")
    except Exception as exc:  # noqa: BLE001 - un bug de herramienta no mata el turno
        db.rollback()
        logger.exception("assistant tool %s failed", name)
        outcome = ToolOutcome(name, False, f"Error: {name} falló: {exc}")
    return _audited(db, organization_id, user, name, raw_input, outcome, started)


def _audited(db, organization_id, user, name, raw_input, outcome: ToolOutcome, started: float) -> ToolOutcome:
    db.add(
        AgentActionLog(
            organization_id=organization_id,
            agent_key_id=None,
            user_id=user.id,
            tool=name,
            arguments=raw_input if isinstance(raw_input, dict) else {"raw": str(raw_input)[:500]},
            success=outcome.ok,
            error=None if outcome.ok else outcome.content[:500],
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    )
    db.commit()
    return outcome


# --- El turno ------------------------------------------------------------


def _record_usage(db, *, organization_id, user_id, model, usage, row: AssistantMessage) -> Decimal:
    tokens = usage_tokens(usage) if usage is not None else usage_tokens({})
    cost = cost_usd(model, tokens)
    db.add(AiUsage(organization_id=organization_id, user_id=user_id, model=model, cost_usd=cost, **tokens))
    row.input_tokens, row.output_tokens = tokens["input_tokens"], tokens["output_tokens"]
    row.cache_read_tokens, row.cache_write_tokens = tokens["cache_read_tokens"], tokens["cache_write_tokens"]
    row.cost_usd = cost
    return cost


def _parsed_input(block: dict) -> Any:
    raw = block.get("input")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return raw
    return raw if raw is not None else {}


def run_turn(
    db: Session,
    *,
    user: User,
    membership: OrganizationMember,
    organization: Organization,
    conversation: AssistantConversation,
    user_text: str,
    client,
    today: date | None = None,
    max_iterations: int = MAX_ITERATIONS,
) -> TurnResult:
    """Un turno completo: persiste el mensaje del usuario, llama al modelo hasta
    que conteste, proponga o se agote algo, y deja cada paso en la BD."""
    settings = get_settings()
    model, effort, max_tokens = settings.ai_model, settings.ai_effort, settings.ai_max_tokens
    role = membership.role
    tools = available_tools(role)
    system = [{"type": "text", "text": system_prompt(tools, model), "cache_control": {"type": "ephemeral"}}]
    specs = tool_specs([t.name for t in tools])

    notes = resolution_notes(db, conversation)
    context = context_block(
        today=today or datetime.now(budget_service.MEXICO).date(),
        organization_name=organization.name,
        user_name=user.name,
        role=role,
        notes=notes,
    )
    if not conversation.title:
        conversation.title = derive_title(user_text)
    user_row = _row(
        conversation, "user",
        [{"type": "text", "text": context}, {"type": "text", "text": user_text}],
        user_text,
    )
    db.commit()
    result = TurnResult(user_message=user_row)
    history = history_for_api(conversation)

    for _ in range(max_iterations):
        status = budget_service.budget_status(db, organization)
        if status.exhausted:
            text = budget_service.budget_message(status.spent_usd, status.budget_usd)
            result.assistant_messages.append(
                _row(conversation, "assistant", [{"type": "text", "text": text}], text, stop_reason=STOP_BUDGET)
            )
            db.commit()
            return result

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            tools=specs,
            messages=history,
        )
        content = [block_to_dict(b) for b in response.content]
        stop_reason = getattr(response, "stop_reason", None)
        # El turno del asistente se guarda y reenvía íntegro (thinking incluido).
        row = _row(conversation, "assistant", content, _text_of(content), stop_reason=stop_reason, steps=[])
        _record_usage(db, organization_id=organization.id, user_id=user.id, model=model,
                      usage=getattr(response, "usage", None), row=row)
        history.append({"role": "assistant", "content": content})
        result.assistant_messages.append(row)

        tool_uses = [b for b in content if b.get("type") == "tool_use"]
        if stop_reason in ("refusal", "max_tokens"):
            # Un tool_use cortado trae argumentos truncados: jamás se ejecuta. Pero
            # el API exige que cada tool_use del historial tenga su tool_result, así
            # que se cierra con un resultado de cancelación (historial append-only).
            row.text = TEXT_REFUSAL if stop_reason == "refusal" else TEXT_MAX_TOKENS
            if tool_uses:
                cancelled = [
                    ToolOutcome(b.get("name", ""), False, "Cancelado: la respuesta se cortó y la herramienta no se ejecutó.")
                    .as_result(b.get("id", ""))
                    for b in tool_uses
                ]
                _row(conversation, "user", cancelled, None)
            db.commit()
            return result
        if not tool_uses:
            if not row.text:
                row.text = "No tengo nada que agregar."
            db.commit()
            return result

        tool_results, steps, proposed = [], [], False
        for block in tool_uses:
            name, tool_use_id = block.get("name", ""), block.get("id", "")
            raw_input = _parsed_input(block)
            is_proposal = TOOLS.get(name) is not None and TOOLS[name].scope == "PROPOSE"
            if is_proposal and proposed:
                outcome = ToolOutcome(name, False, "Error: sólo una propuesta por turno; la anterior está pendiente de aprobación.")
            else:
                outcome = execute_tool(
                    db, organization_id=organization.id, user=user, role=role, name=name, raw_input=raw_input,
                    origin=f"assistant:{conversation.id}:{tool_use_id}",
                )
            if outcome.proposal is not None:
                proposed = True
                row.actions.append(
                    AssistantAction(
                        conversation_id=conversation.id,
                        organization_id=organization.id,
                        tool_use_id=tool_use_id,
                        tool_name=name,
                        args=raw_input if isinstance(raw_input, dict) else {},
                        summary=outcome.summary or "",
                        proposal_id=outcome.proposal.id,
                    )
                )
            steps.append({"name": name, "ok": outcome.ok, "summary": step_label(name)})
            tool_results.append(outcome.as_result(tool_use_id))

        row.steps = steps
        # Todos los tool_result de la iteración en UN solo mensaje de usuario.
        _row(conversation, "user", tool_results, None)
        history.append({"role": "user", "content": tool_results})
        if proposed:
            row.text = row.text or TEXT_PROPOSED
            row.stop_reason = STOP_PROPOSAL
            db.commit()
            return result
        db.commit()

    result.assistant_messages.append(
        _row(conversation, "assistant", [{"type": "text", "text": TEXT_ITERATIONS}], TEXT_ITERATIONS,
             stop_reason=STOP_ITERATIONS)
    )
    db.commit()
    return result
