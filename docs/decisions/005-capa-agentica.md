# ADR-005 — Capa agéntica: propuesta → aprobación

**Fecha:** 2026-08-24 · **Estado:** aceptada

## Contexto

ARCA debe integrarse con sistemas agénticos (CFO, MCP, Magic Inbox) sin violar el task pack §37: la IA nunca escribe directo a la BD y el core determinista no depende de ella. Se decidió (Emmanuel, 2026-08-24): infraestructura primero y LLM después; los agentes proponen y un humano aprueba.

## Decisión

- **Un solo catálogo de herramientas** (`app/agents/tools.py`): 14 de lectura + 4 `propose_*`. Los handlers solo llaman services existentes. CFO (A1), MCP (A2) e Inbox (A3) reutilizan este catálogo.
- **Identidad por llave** (`AgentKey`): token `ak_…` mostrado una vez, sha256 en BD, organización FIJA por llave (sin header de org → sin superficie cross-tenant), scopes `READ` / `READ,PROPOSE`, revocable.
- **Propuesta → aprobación** (`AgentProposal`): las herramientas de escritura crean propuestas; `approve` re-valida el payload contra el schema Create vigente y ejecuta el service real (movimientos y asientos incluidos) con el humano aprobador como `created_by`.
- **Auditoría total** (`AgentActionLog`): toda invocación registrada, exitosa o fallida.

## Consecuencias

- Un agente comprometido puede leer su organización y llenar la bandeja, pero no puede mover un peso.
- El costo de inferencia de A0 es cero: los agentes externos traen su LLM.
- Deuda aceptada: sin rate limiting por llave ni expiración de propuestas (anotado en MVP_STATUS).
