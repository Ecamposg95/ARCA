# ARCA — Capa Agéntica (diseño aprobado)

**Fecha:** 2026-08-24 · **Estado:** aprobado por Emmanuel (chat) · **Alcance de esta spec:** Fase A0 en detalle; A1–A3 como roadmap.

## Principio rector (task pack §37)

```text
Agente → Financial Tool API → Services → Ledger
```

- Ningún agente (interno o externo) toca la base de datos ni ejecuta operaciones directamente.
- El core determinista funciona idéntico con la capa agéntica apagada.
- **Propuesta → aprobación:** los agentes leen libremente (scope LECTURA) y para escribir crean PROPUESTAS que un humano aprueba; la aprobación ejecuta el service real con todas sus validaciones y asientos.
- **Sin LLM hospedado en A0:** los agentes externos traen su propia inteligencia y consumen herramientas. ARCA conecta su propio LLM hasta A1 (CFO).

## Roadmap

| Fase | Qué | LLM hospedado |
|---|---|---|
| **A0 Fundación** (esta spec) | Catálogo de herramientas, llaves de agente por organización, bandeja de propuestas, auditoría | No |
| A1 ARCA CFO | Chat en la app con tool-use de Claude sobre el mismo catálogo | Sí (ANTHROPIC_API_KEY) |
| A2 MCP server | El catálogo expuesto vía MCP autenticado con AgentKey (Claude Code, Atlas ONE). Puede adelantarse a A1: costo de inferencia cero | No |
| A3 Magic Inbox | Documento → extracción → propuesta con evidencia → misma bandeja | Sí |

## Fase A0 — Diseño

### Modelos (migración `20260824_05`)

**AgentKey** (tenant): `name`, `key_prefix` (primeros 12 chars, para mostrar), `key_hash` (sha256 del token completo), `scopes` (`"READ"` o `"READ,PROPOSE"`), `active` (bool), `last_used_at`, `created_by`. Token formato `ak_<40 hex>`; se muestra completo UNA sola vez al crearlo. Revocar = `active=False` (no se borra: auditoría).

**AgentProposal** (tenant): `agent_key_id` FK, `kind` (`INCOME|EXPENSE|RECEIVABLE|PAYABLE`), `payload` (JSON del schema Create correspondiente), `summary` (una línea humana escrita por el agente), `evidence` (texto libre, nullable — en A3 llevará referencia al documento), `status` (`PROPOSED|APPROVED|REJECTED`), `reviewed_by`, `reviewed_at`, `rejection_reason`, `result_id` (id de la entidad creada al aprobar).

**AgentActionLog** (tenant): `agent_key_id`, `tool`, `arguments` (JSON truncado, sin datos sensibles), `success` (bool), `error` (nullable), `duration_ms`. Toda invocación se registra, exitosa o no.

### Autenticación de agentes

`app/security/agent.py::get_agent_context` — lee `Authorization: Bearer ak_...`, busca por `key_hash`, valida `active`, devuelve `AgentContext(agent_key, organization_id, scopes)` y actualiza `last_used_at`. La organización queda FIJA por la llave: no hay header de org, no hay cross-tenant posible. `require_scope("PROPOSE")` para herramientas de escritura. Llave revocada o desconocida → 401.

Gestión (humanos, rol OWNER/ADMIN): `GET /api/agent-keys` (lista con prefijo, nunca el token), `POST /api/agent-keys {name, scopes}` → devuelve el token completo una vez, `DELETE /api/agent-keys/{id}` (revoca).

### Catálogo de herramientas — `app/agents/tools.py`

`ToolSpec(name, description, params_model: type[BaseModel], scope: "READ"|"PROPOSE", handler)`. Registro central `TOOLS: dict[str, ToolSpec]`. Los handlers reciben `(db, organization_id, params)` y SOLO llaman services/queries existentes; devuelven JSON serializable.

Lectura: `dashboard_summary`, `profit_loss(start,end)`, `balance_sheet(as_of)`, `cash_flow(start,end)`, `trial_balance`, `list_accounts`, `list_categories(kind?)`, `list_customers(q?)`, `list_vendors(q?)`, `list_incomes(status?,start?,end?)`, `list_expenses(status?,start?,end?)`, `list_receivables(status?)`, `list_payables(status?)`, `list_transactions(account_id?,start?,end?)`.

Propuesta: `propose_income`, `propose_expense`, `propose_receivable`, `propose_payable` — params = schema Create del dominio + `summary` (obligatorio) + `evidence?`. Crean `AgentProposal`; NO ejecutan nada.

Endpoints agente: `GET /api/agent/tools` (nombre, descripción, JSON Schema de params, scope — descubrimiento) y `POST /api/agent/invoke {tool, arguments}` → `{ok, result}` o `{detail}` 400. Errores de dominio llegan como mensajes humanos (mismo handler global).

### Bandeja de propuestas (humanos)

- `GET /api/proposals?status=` (paginado, default PROPOSED primero).
- `POST /api/proposals/{id}/approve` — valida el payload contra el schema Create del `kind` y ejecuta el service real (`create_income`, `create_expense`, `create_receivable`, `create_payable`) con `created_by` = usuario que aprueba; guarda `result_id`; si el payload ya no es válido (p.ej. cuenta eliminada) → 400 con mensaje y la propuesta sigue PROPOSED.
- `POST /api/proposals/{id}/reject {reason?}` — no toca nada más.
- Roles: aprobar/rechazar requiere WRITE_ROLES.
- Eventos: `proposal.created`, `proposal.approved`, `proposal.rejected`.

### UI

- **Configuración → Agentes:** crear llave (nombre + scope), modal que muestra el token una única vez con botón copiar, lista (nombre, prefijo, scopes, último uso) y revocar.
- **Propuestas** (nav, con badge de pendientes): tarjetas con summary, tipo, detalle del payload legible, evidencia, agente que la propuso y antigüedad; botones Aprobar / Rechazar (con razón). Empty state explicando qué son las propuestas.

### Tests críticos

1. Llave inválida/revocada → 401; llave de Org A jamás ve datos de Org B (aunque los tools no reciban org explícita).
2. Scope READ no puede invocar `propose_*` → 403.
3. `propose_income` crea propuesta y NO crea ingreso ni asientos.
4. Aprobar propuesta de ingreso pagado → Income real + movimiento + asiento balanceado; `result_id` enlazado.
5. Rechazar → nada cambia en finanzas.
6. Toda invocación (éxito y error) queda en AgentActionLog.

### Fuera de alcance A0

Rate limiting por llave (deuda anotada), expiración de propuestas, edición de propuestas antes de aprobar, scopes granulares por herramienta, MCP transport (A2), cualquier llamada a LLM.
