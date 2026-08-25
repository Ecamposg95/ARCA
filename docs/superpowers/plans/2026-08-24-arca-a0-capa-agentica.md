# ARCA A0 — Fundación Agéntica Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Llaves de agente por organización + catálogo de herramientas financieras + bandeja de propuestas con aprobación humana, sin LLM hospedado.

**Architecture:** Nuevo dominio `app/agents/` (tools + registry) y `app/domains/{agent_keys,proposals}/`; auth de agente paralela a la humana en `app/security/agent.py` (org fija por llave). La aprobación ejecuta los services Create existentes — cero lógica financiera nueva.

**Tech Stack:** el existente. Sin dependencias nuevas (sha256 de stdlib).

**Spec:** `docs/superpowers/specs/2026-08-24-capa-agentica-design.md` (aprobada).

## Global Constraints

- Las de siempre (tenant NOT NULL, Decimal, errores en español, paginación canónica, commits en español).
- Los handlers de tools SOLO llaman services/queries existentes; jamás mutan estado financiero.
- `payload` de propuestas se re-valida contra el schema Create al aprobar (el schema es la fuente de verdad, no el JSON guardado).
- El token de llave se muestra una sola vez; en BD solo sha256 + prefijo.

### Task 1: Modelos + migración `20260824_05_agentes.py`
`app/models/agent.py` (AgentKey, AgentProposal, AgentActionLog per spec) + registro en `app/models/__init__.py`. Verificar `alembic upgrade head` + un solo head. Commit.

### Task 2: Auth de agente + gestión de llaves
`app/security/agent.py`: `generate_key() -> (token, prefix, hash)`, `get_agent_context` (Bearer ak_… → AgentContext), `require_scope(scope)`. `app/domains/agent_keys/router.py`: GET/POST/DELETE `/api/agent-keys` (OWNER/ADMIN). Tests: crear llave devuelve token una vez; llave inválida/revocada 401; listado nunca expone token. Commit.

### Task 3: Catálogo de herramientas + invoke
`app/agents/{__init__,tools}.py`: `ToolSpec`, registro `TOOLS` con las 14 de lectura + 4 `propose_*` (params modelados con los schemas Create reutilizados + summary/evidence). `app/domains/agent_api/router.py`: `GET /api/agent/tools`, `POST /api/agent/invoke` con log a AgentActionLog (éxito y error, duración). Tests: descubrimiento lista tools con schema; invoke lee datos SOLO de la org de la llave (isolation con 2 orgs); scope READ → 403 en propose; toda invocación queda logueada. Commit.

### Task 4: Bandeja de propuestas
`app/domains/proposals/{schemas,service,router}.py`: list/approve/reject per spec; executor `_EXECUTORS = {"INCOME": (IncomeCreate, create_income), ...}`; eventos proposal.*. Tests: propose no crea operación; approve crea Income pagado real con asiento balanceado y result_id; payload inválido al aprobar → 400 y sigue PROPOSED; reject no toca finanzas; tenant isolation en approve. Commit.

### Task 5: Frontend
`features/settings/SettingsPage.tsx`: sección "Agentes" (crear llave → modal token única vez, lista, revocar). `features/proposals/ProposalsPage.tsx` + ruta `/propuestas` + nav con badge (count de PROPOSED vía query). Tipos en `types/api.ts`. Build limpio + smoke local con curl (llave → invoke → propuesta → aprobar). Commit.

### Task 6: Cierre
ADR-005 (capa agéntica propuesta→aprobación), MVP_STATUS, AGENTS.md (sección de la capa agéntica), suite completa + ruff, merge a main, push (auto-deploy), validación en producción end-to-end con una llave real. Commit.

## Self-review
Spec §Modelos→T1, §Auth→T2, §Catálogo→T3, §Bandeja→T4, §UI→T5, tests críticos 1-6 repartidos en T2-T4. Sin placeholders; nombres consistentes (`get_agent_context`, `require_scope`, `TOOLS`, `_EXECUTORS`).
