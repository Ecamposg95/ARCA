# AGENTS.md — Reglas para agentes que trabajan en ARCA

## Qué es ARCA

Financial Operating System de Atlas Tech. Un emprendedor registra operaciones en su lenguaje ("vendí", "gasté", "me deben") y ARCA produce por debajo finanzas y contabilidad formales. **North Star:** que el usuario entienda su negocio sin saber contabilidad, con un ledger de partida doble correcto y auditable debajo de cada cifra.

```text
OPERACIÓN → EVENTO FINANCIERO → MOVIMIENTO → CONTABILIDAD → ESTADOS FINANCIEROS
```

Spec completa: `docs/TASK_PACK.md`. Decisiones: `docs/superpowers/specs/` y `docs/decisions/`.

## Invariantes que NUNCA se rompen

1. **Nunca romper double-entry accounting.** Todo asiento pasa por `app/services/accounting/engine.py::post_journal_entry()` que exige `SUM(debit) == SUM(credit)`. Prohibido crear `JournalEntry`/`JournalEntryLine` por otra vía.
2. **Nunca crear entidades financieras sin `organization_id`** cuando pertenecen a un tenant. `TenantMixin` es NOT NULL a propósito.
3. **Nunca usar `float` para dinero.** `Decimal` en Python, `Numeric(14,2)` en BD, strings en JSON de entrada.
4. **Nunca permitir acceso cross-tenant.** Todo query de negocio filtra por `organization_id` obtenido de `get_current_org_id` (membresía validada), jamás del payload. Tests en `tests/test_tenant_isolation.py` lo vigilan.
5. **Nunca poner lógica contable crítica solo en frontend.** El backend es la autoridad; la UI solo consume.
6. **Un instrumento tiene naturaleza y respeta su cuenta contable.** Efectivo y
   bancos son activo (1100); una tarjeta de crédito es **pasivo** (2200): gastar
   con ella crea deuda, no reduce efectivo, y su saldo jamás se suma al
   disponible. Pagar la tarjeta es un traspaso que baja la deuda, **no** un
   gasto nuevo: el gasto ya se registró al usarla.
7. **Nunca mutar `FinancialAccount.current_balance` directamente.** Solo `app/services/transactions.py::record_transaction()` (patrón lock → refresh → re-check).
8. **Nunca borrar físicamente registros contables o financieros contabilizados.** Patrón `CANCELLED` + campos `cancelled_*`; los reversos serán pólizas de reversa.
9. **Las reglas contables viven en `app/services/accounting/rules.py`.** Una función por evento de negocio. Nada de armar asientos en routers.
10. **Reportes SIEMPRE derivados del ledger**, nunca almacenados a mano.
11. **Toda póliza lleva folio inmutable** (`Ig-/Eg-/Dr-AAAA-MM-NNNN`) que asigna
    `app/services/accounting/folios.py` bajo lock del contador. Nunca reasignar,
    reutilizar ni reciclar folios: son el índice de los libros del negocio.
12. **Nunca asentar una póliza con fecha futura.** La depreciación de un mes se
    corre al cierre; asentarla antes esconde el gasto hasta que llegue ese día y
    deja el patrimonio inflado. Misma regla para cualquier proceso periódico.
13. **Lo que se compra para usar años no es gasto del mes.** El costo vive en
    1400 y llega a resultados vía depreciación contra 1490. Y el pago de un
    crédito no es gasto: sólo el interés (5900) lo es; el resto baja 2300.
14. **Los procesos periódicos son idempotentes.** Depreciar dos veces el mismo
    mes debe no hacer nada, no duplicar. La clave de idempotencia va en
    `source_id` (`{entidad}:{AAAA-MM}`), no en una bandera aparte.
15. **Un proyecto es una etiqueta, no una cuenta.** `project_id` nunca cambia a
    qué cuentas va una operación; existe una prueba de que el ledger no se
    entera. La rentabilidad se mide sobre subtotales: el IVA no es tuyo.
16. **Un mes cerrado no acepta pólizas.** El candado se valida dentro de
    `post_journal_entry()`, nunca en los routers: es el único punto por el que
    pasa toda la contabilidad. Reabrir exige un motivo y queda registrado.
17. **Deshacer es revertir, nunca borrar ni editar.** Se emite la póliza espejo
    y el movimiento inverso (`REVERSAL_IN`/`REVERSAL_OUT`), y el original queda.
    Una operación ya revertida no se revierte dos veces.
18. **Lo retenido no es tuyo.** ISR e IVA retenidos salen del pago al proveedor
    y viven en 2400/2410 hasta enterarse al SAT. El gasto sigue siendo el monto
    completo: retener no abarata el servicio.
19. **Las reglas fiscales se calculan en el backend.** El aviso de deducibilidad
    viaja en el schema; la UI lo muestra, no lo deduce.

## Arquitectura

- Servicio único: FastAPI (`app/`) sirve `/api/*` + SPA React construida (`frontend/dist`) por catch-all (registrado al final).
- Dominios en `app/domains/<x>/` (router delgado / service con transacciones / schemas Pydantic v2). Modelos compartidos en `app/models/`.
- Eventos internos: `app/core/events.py` (bus síncrono; un suscriptor que falla no tumba la operación).
- API: `/api/<dominio>` plural, sin slash final; paginación `{items, total, limit, offset}`; errores `{"detail": "mensaje humano en español"}`; nunca devolver ORM crudo (`Schema.model_validate()`).
- Roles por organización: OWNER, ADMIN, ACCOUNTANT, MEMBER, VIEWER. Contabilidad visible solo para los tres primeros (`require_role`).
- UI en español con lenguaje de empresario (§39 del task pack); los términos contables solo dentro de la sección Contabilidad.

## Cómo ejecutar

```bash
source .venv/bin/activate
alembic upgrade head && uvicorn app.main:app --reload   # API
cd frontend && npm run dev                              # SPA (proxy /api → :8000)
```

## Cómo testear

```bash
pytest                 # SQLite en memoria, rápido
TEST_DATABASE_URL=postgresql://... pytest   # PostgreSQL real (como CI)
ruff check .
cd frontend && npm run typecheck && npm run build
```

Tests obligatorios antes de cerrar cualquier feature financiera: tenant isolation, partida doble balanceada, efectos en saldos (cash ↑/↓), consistencia de reportes con el ledger.

## Cómo desplegar

Railway (proyecto ARCA, servicio `ARCA` + PostgreSQL). El servicio está conectado al repo GitHub `Ecamposg95/ARCA`: **push a `main` = deploy automático** (no usar `railway up`; desde /mnt/d además corrompe el upload). Railpack construye (config en `railpack.json`); el arranque ejecuta `alembic upgrade head`. Healthcheck `GET /api/health`. Variables obligatorias: `DATABASE_URL`, `SECRET_KEY`, `ENV=production`.

## Migraciones

- Solo Alembic. Nunca `create_all()` en producción, nunca DDL suelto en scripts.
- Nombres `AAAAMMDD_NN_descripcion.py`, `revision = "AAAAMMDD_NN"`.
- `alembic heads` debe imprimir exactamente UN head.
- Registrar cada módulo de modelos nuevo en `app/models/__init__.py` (si no, create_all/autogenerate lo omiten en silencio).

## Capa agéntica (ADR-005)

- Agentes se autentican con llave `ak_…` (org fija por llave, scopes READ / READ,PROPOSE); superficie en `/api/agent/tools` + `/api/agent/invoke`.
- El catálogo vive en `app/agents/tools.py` — herramientas nuevas SOLO llaman services existentes; las de escritura crean `AgentProposal`, jamás ejecutan.
- La aprobación humana (`app/domains/proposals/service.py`) es el único puente propuesta→operación real; re-valida contra el schema Create vigente.
- Toda invocación se registra en `AgentActionLog`. No agregar herramientas que salten estas capas.

## Reglas para features nuevas

- Vertical slices: DB → dominio → API → UI → contabilidad → tests, una operación a la vez.
- Prioridad de calidad: 1) correctitud financiera, 2) seguridad, 3) integridad de datos, 4) UX, 5) performance, 6) extensibilidad.
- Conceptos explícitos (Income, Expense, Receivable, Payable...) — no generalizar a una tabla universal.
- Conservar `source_type`/`source_id` en entidades que puedan originarse fuera (futura integración Atlas ONE).
- Commits: Conventional Commits en español (`feat(gastos): ...`).
- Actualizar `docs/MVP_STATUS.md` al avanzar.
