# ARCA · Referencia técnica

_Fecha: 2026-10-12 · Audiencia: ingeniería de Atlas y de partners que se integran. Las reglas que nunca se rompen están en `AGENTS.md`; el plan de alcances e integraciones en `docs/MEGA_PLAN_MVP.md`._

ARCA es un monolito modular en FastAPI con el motor contable como núcleo y una capa agéntica con aprobación humana. Las integraciones entran por webhooks firmados e idempotentes y salen por un outbox durable. Toda escritura al libro pasa por un único punto, y todo reporte se deriva del libro en cada consulta.

## 1. Contexto del sistema

| Actor | Qué le manda a ARCA | Qué recibe de ARCA |
| --- | --- | --- |
| Dueño de la pyme (frontend React) | Operaciones en lenguaje de negocio: vendí, cobré, gasté, pagué | Dashboard, reportes, avisos, propuestas por aprobar |
| Despacho contable (frontend React, rol ACCOUNTANT) | Pólizas, catálogo, cierres, mapeos fiscales | Balanza, XML del SAT, export CONTPAQi, paquete NIF, cédula |
| Atlas ONE (POS y ERP) | Eventos de venta, cobro, devolución y caja | CFDI timbrados (fase FACT) |
| Atlas Cortex (agentes) | Invocaciones de herramientas con llave `ak_` | Datos de lectura, estatus de propuestas, webhook `proposal.decided` |
| HRFlow (nómina) | Eventos de nómina autorizada y pagada | CFDI de nómina timbrados (fase FACT) |
| PAC | — | Solicitudes de timbrado y cancelación |
| SAT | — | Catálogo y balanza XML del Anexo 24, DIOT |
| Bancos | Estados de cuenta CSV y Excel | — |

## 2. Capas y responsabilidades

| Capa | Ruta | Responsabilidad | Regla |
| --- | --- | --- | --- |
| Routers | `app/domains/<x>/router.py` | Validar entrada (Pydantic v2), resolver tenant y rol, traducir errores a 400 en español | Nunca ORM crudo ni lógica contable |
| Services | `app/domains/<x>/service.py` | Casos de uso, transacciones, publicación de eventos | Una función por caso de uso; no hace commit cuando lo compone otro service |
| Reglas contables | `app/services/accounting/rules.py` | Una función por evento de negocio que arma la póliza | Único lugar donde se decide cargo y abono |
| Motor | `app/services/accounting/engine.py` | `post_journal_entry`: partida doble, folio, candado de mes y de ejercicio, evento | Único punto de escritura al ledger |
| Folios | `app/services/accounting/folios.py` | Consecutivo por empresa, tipo y mes bajo lock de fila | Nunca reasignar ni reciclar |
| Movimientos | `app/services/transactions.py` | `record_transaction`: saldo de instrumentos con lock → refresh → re-check | Única forma de mover `current_balance` |
| Reversos | `app/services/reversals.py` | Póliza espejo y movimiento inverso de una operación | Una operación se revierte una sola vez |
| Formatos externos | `app/services/accounting/contpaqi.py`, `sat.py`, `coa.py` | Layout CONTPAQi, XML Anexo 24, catálogo inicial | Funciones puras con archivo dorado en pruebas |
| Modelos | `app/models/` | SQLAlchemy 2, `UUIDPKMixin`, `TenantMixin`, `AuditMixin`, `Numeric(14,2)` | Registrar módulos nuevos en `app/models/__init__.py` |
| Capa agéntica | `app/agents/tools.py`, `app/domains/agent_api/`, `app/domains/proposals/` | Catálogo de herramientas, invocación auditada, propuestas | Un agente nunca escribe al ledger: propone y un humano aprueba |
| Eventos | `app/core/events.py` | Bus en proceso (`event_bus.publish`) | Se vuelve outbox durable en la fase 0 del plan |
| Seguridad | `app/security/` | Contraseñas, tokens JWT, dependencias de membresía y rol, llaves de agente | Tenant siempre desde la membresía, nunca del payload |
| Frontend | `frontend/src/features/<x>/` | UX en lenguaje de empresario, TanStack Query v5, Zustand, tokens semánticos Tailwind | Consume; nunca calcula reglas |

## 3. Flujo de una operación

Ejemplo: el dueño registra un gasto pagado con tarjeta.

1. `POST /api/expenses` llega al router con JWT y `X-Organization-ID`; `require_role(WRITE_ROLES)` valida la membresía.
2. `expenses/service.py` crea el `Expense`, calcula IVA y deducibilidad en backend.
3. Llama a `rules.py::expense_entry(...)`, que arma las líneas: cargo 5xxx gasto, cargo 1190 IVA acreditable pagado, abono 2200 Tarjetas.
4. `engine.py::post_journal_entry` valida que `SUM(debit) == SUM(credit)`, que el mes esté abierto, asigna folio `Eg-2026-10-0007` y persiste la póliza.
5. `transactions.py::record_transaction` registra el movimiento en el instrumento (tarjeta: sube la deuda) con lock de fila.
6. Se publica `expense.created`; el dashboard, el estado de resultados y la balanza lo reflejan en la siguiente consulta porque se calculan desde el ledger.

Deshacer: `POST /api/expenses/{id}/cancel` emite la póliza espejo (`reversal_of`) y el movimiento `REVERSAL_IN`; el original queda intacto con `status=CANCELLED`.

## 4. Modelo de datos

Toda tabla de negocio lleva `organization_id` NOT NULL (`TenantMixin`), `id` UUID, `created_at`/`updated_at` (`AuditMixin`). Dinero: `Numeric(14,2)`. Las entidades que pueden nacer fuera llevan `source_type`, `source_id` y `external_reference`.

| Tabla | Para qué | Columnas que importan |
| --- | --- | --- |
| `organizations` | Empresa (tenant) | `name`, `legal_name`, `tax_id` (RFC), `business_type`, `default_tax_rate`, `currency`, `timezone` |
| `organization_members` | Membresía y rol | `user_id`, `role` ∈ OWNER, ADMIN, ACCOUNTANT, MEMBER, VIEWER; único por (org, user) |
| `users` | Identidad | `email` único, hash de contraseña |
| `accounts` | Catálogo contable | `code` único por org, `name`, `type` ∈ ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE, `parent_id`, `active`, `system`, `contpaqi_code`, `sat_code` |
| `journal_entries` | Pólizas | `folio` único por org, `kind` ∈ INGRESO, EGRESO, DIARIO, `date`, `description`, `reference`, `source_type`, `source_id` (64), `status`, `created_by` |
| `journal_entry_lines` | Líneas | `account_id`, `debit`, `credit` (uno de los dos > 0), `description` |
| `folio_counters` | Consecutivo | único por (org, kind, period) |
| `period_locks` | Mes cerrado | `year`, `month`, `closed_by`, `reopened_at`, `reopen_reason`, `notes` |
| `fiscal_year_locks` | Ejercicio cerrado | único por (org, `year`), `closed_by`, `closing_entry_id`, `reopened_at`, `reopened_by`, `reopen_reason`, `notes` |
| `financial_accounts` | Instrumentos | `type` ∈ CASH, BANK, CREDIT_CARD, OTHER, `opening_balance`, `current_balance`, `credit_limit` |
| `financial_transactions` | Movimientos | `transaction_type` (INCOME, EXPENSE, TRANSFER_IN/OUT, RECEIVABLE_COLLECTION, PAYABLE_PAYMENT, REVERSAL_IN/OUT, ADJUSTMENT), `amount`, `date`, `status`, `source_type`, `source_id` |
| `income`, `expenses` | Operaciones | monto, IVA, método de pago, categoría, contacto, proyecto, `status`, `cancelled_*` |
| `receivables`, `payables` | Cartera | `amount`, `balance`, `due_date`, `status` ∈ OPEN, PARTIAL, PAID, CANCELLED; OVERDUE se calcula |
| `contacts`, `categories`, `projects` | Maestros | categorías mapean a cuenta contable; proyecto es etiqueta, nunca cambia cuentas |
| `fixed_assets`, `loans`, `recurring` | Patrimonio y periódicos | depreciación y pagos idempotentes por `source_id = {entidad}:{AAAA-MM}` |
| `agent_keys` | Llaves de agente | hash sha256 del token `ak_…`, `scopes` (READ, PROPOSE), `revoked_at` |
| `agent_invocations` | Auditoría | herramienta, argumentos, resultado, llave, latencia |
| `proposals` | Bandeja | tipo, payload, evidencia, agente, `status`, decisión y quién |

Tablas que agrega el plan maestro: `outbox_events`, `inbound_events`, `integration_connections` (fase 0); `cfdi_documents` (E y FACT); `bank_statements`, `bank_lines`, `reconciliations` (BANK); `fiscal_profiles`, `tax_filings`, `obligations` (TAX); `client_tasks` (DESP); `invoices`, `csd_credentials` (FACT); `notices` (CFO); `payroll_periods` (HRFlow).

## 5. Motor contable

```python
from app.services.accounting.engine import LineSpec, post_journal_entry

entry = post_journal_entry(
    db, organization_id,
    date=date(2026, 10, 12),
    description="Provisión de nómina 2a quincena",
    lines=[
        LineSpec("5200", debit=Decimal("180000.00")),
        LineSpec("2400", credit=Decimal("12000.00")),
        LineSpec("2150", credit=Decimal("168000.00")),
    ],
    source_type="manual", source_id=None, reference=None,
    created_by=user_id, kind="DIARIO",
)
```

- Rechaza menos de dos líneas, montos negativos, líneas con cargo y abono a la vez, cuentas inexistentes o inactivas, descuadre y meses cerrados (`ClosedPeriodError`). No hace commit: la transacción es del caller.
- `kind` lo declara la regla, nunca se infiere; define la serie del folio (`Ig-`, `Eg-`, `Dr-`).
- Saldos por tipo: `account_type_balance`; balanza: `trial_balance`. Naturaleza deudora para ASSET y EXPENSE, salvo contra-activos (1490).
- Catálogo inicial (`coa.py::DEFAULT_CHART`): 1000 Activo (1100 Caja y Bancos, 1190/1191 IVA acreditable, 1200 CxC, 1300 Otros, 1400 Activo fijo, 1490 Depreciación acumulada), 2000 Pasivo (2100 CxP, 2190/2191 IVA trasladado, 2200 Tarjetas, 2300 Préstamos, 2400 ISR retenido, 2410 IVA retenido), 3000 Capital (3100 Capital, 3200 Resultados acumulados), 4000 Ingresos (4100 Ventas, 4200 Servicios), 5000 Gastos (5100 a 5900). Cada cuenta sembrada lleva `system=True` y un código agrupador SAT por defecto.
- Cuentas que agrega el plan: 2150 Sueldos por pagar, 2420 IMSS obrero por enterar, 2430 IMSS e INFONAVIT patronal por pagar, 2440 Provisiones de nómina, 2500 Propinas por pagar, 5210 Cuotas patronales, 5220 Provisión de aguinaldo y vacaciones.

## 6. API

- Base `/api`; recursos en plural sin slash final (`/api/expenses`, `/api/receivables/{id}/collect`).
- Autenticación: `POST /api/auth/register`, `/login`, `/refresh`; JWT Bearer de acceso (720 min por defecto) y refresh (30 días). Toda ruta de negocio exige `X-Organization-ID`, validado contra `organization_members`.
- Roles: `ACCOUNTING_ROLES` = OWNER, ADMIN, ACCOUNTANT para `/api/accounting/*` y `/api/periods/*`; `WRITE_ROLES` agrega MEMBER; VIEWER sólo lee.
- Paginación `{items, total, limit, offset}` con `limit ≤ 200`. Errores `{"detail": "mensaje en español"}` con 400 para reglas de negocio, 401/403 para auth, 404 para recursos ajenos o inexistentes (misma respuesta en ambos casos para no filtrar existencia entre tenants).
- Dinero: strings decimales en entrada (`"1160.00"`), `Decimal` en salida; `Field(gt=0, allow_inf_nan=False)` en schemas. Fechas ISO `AAAA-MM-DD`; nunca fecha futura en pólizas.
- Idempotencia: todo endpoint que reciba datos de otro sistema acepta `external_reference` y responde 200 con el recurso existente si se repite.
- Descargas: `/api/reports/{report}/csv`, `/api/accounting/contpaqi`, `/api/accounting/sat/catalogo`, `/api/accounting/sat/balanza`; requieren sesión (token en cabecera, no en query).
- Documentación OpenAPI en `/docs` sólo fuera de producción (`DOCS_ENABLED`).
- Salud: `GET /api/health` (proceso) y `GET /api/health/deep` (base de datos).

## 7. Capa agéntica (ADR-005)

- Llaves por empresa: `POST /api/agent-keys` devuelve una sola vez el token `ak_…`; se guarda el hash sha256; scopes `READ` y `PROPOSE`; revocación inmediata.
- Catálogo: `GET /api/agent/tools` lista 21 herramientas: 17 de lectura (`dashboard_summary`, `profit_loss`, `balance_sheet`, `cash_flow`, `trial_balance`, `list_accounts`, `list_categories`, `list_customers`, `list_vendors`, `list_incomes`, `list_expenses`, `list_receivables`, `list_payables`, `list_transactions`, `aging_report`, `cash_projection`, `net_worth`) y 4 de propuesta (`propose_income`, `propose_expense`, `propose_receivable`, `propose_payable`).
- Invocación: `POST /api/agent/invoke {"tool", "arguments"}` con Bearer `ak_`; cada llamada queda en `agent_invocations`. Una propuesta crea un renglón en `proposals` y responde `proposal_id`; `GET /api/agent/proposal-status/{id}` devuelve su estado.
- Aprobación: la página Propuestas muestra resumen, payload legible, evidencia y agente; aprobar ejecuta el service real (misma ruta que un humano), rechazar exige motivo. Eventos `proposal.created`, `proposal.approved`, `proposal.rejected`.
- El plan agrega `propose_cfdi_link`, `propose_bank_match`, `propose_journal_entry`, `notify_owner`, el webhook `proposal.decided` y un servidor MCP sobre la misma llave.

## 8. Integraciones: contrato de webhooks

Entrada: `POST /api/integrations/{source}/events` con `source` ∈ `atlas-one`, `hrflow`, `cortex`.

| Cabecera | Valor |
| --- | --- |
| `X-Atlas-Signature` | `sha256=<HMAC-SHA256(secreto, cuerpo crudo)>` |
| `X-Atlas-Timestamp` | Unix segundos; se rechaza fuera de ±300 s |
| `X-Atlas-Event-Id` | UUID del evento en el origen |
| `Content-Type` | `application/json` |

Cuerpo mínimo: `event`, `occurred_at` (ISO con zona), `external_reference` (único por empresa y origen), `organization_external_id` (id de la empresa en el origen, mapeado en `integration_connections`), más el payload del evento (ejemplos en `docs/MEGA_PLAN_MVP.md`).

Respuestas: 202 aceptado y procesado; 200 duplicado ignorado; 401 firma o ventana inválida; 404 conexión no configurada; 422 payload inválido (el evento se guarda en `inbound_events` con `status=REJECTED` y el motivo). Nunca 500 silencioso: un fallo de regla contable deja el evento en `FAILED` con el error y dispara alerta al tercer fallo.

Salida (`outbox_events`): el worker entrega `proposal.decided`, `invoice.stamped`, `payroll.stamped` a la URL de la conexión con las mismas cabeceras, reintentos exponenciales (1, 5, 25, 125, 625 s) y `FAILED` al quinto intento. Reconciliación diaria por rango de fechas contra la API de lectura del origen.

## 9. Seguridad

- Contraseñas con hash (`app/security/passwords.py`), mínimo 8 caracteres; tokens firmados con `SECRET_KEY` y expiración; refresh rotable.
- Tenant isolation: todo query filtra por `organization_id` obtenido de la membresía; `tests/test_tenant_isolation.py` lo vigila. Un recurso de otra empresa responde 404.
- Llaves de agente con hash, scopes, revocación y auditoría completa; una llave nunca ejecuta: propone.
- Secretos fiscales (CSD, e.firma) cifrados por empresa (Fernet con llave maestra `FISCAL_MASTER_KEY` en entorno, rotación con doble llave documentada), nunca en logs ni en respuestas; acceso registrado.
- Webhooks con HMAC y ventana de tiempo; rate limiting y bloqueo temporal en auth y por llave (fase 0).
- Nada se borra: `CANCELLED` + campos `cancelled_*`, reversos como pólizas espejo, meses y ejercicios con candado y reapertura con motivo.
- CORS por lista (`CORS_ORIGINS`); HTTPS terminado en Railway; `/docs` apagado en producción.

## 10. Despliegue y operación

- Un solo servicio en Railway (ADR-001): Railpack compila el frontend en el step `build` y FastAPI sirve el estático; PostgreSQL administrado por Railway; `alembic upgrade head` al arranque; push a `main` despliega. Dominio: https://arca-production-d769.up.railway.app.
- Variables: `DATABASE_URL`, `SECRET_KEY`, `ENV` (`production` apaga docs), `CORS_ORIGINS`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `DOCS_ENABLED`. El plan agrega `FISCAL_MASTER_KEY`, `PAC_*`, `SMTP_*`, `OUTBOX_WORKER_ENABLED`.
- CI (GitHub Actions): Postgres 16, `ruff check .`, `pytest`, `npm run typecheck`, `npm run build`.
- Migraciones: `AAAAMMDD_NN_slug.py` con `revision="AAAAMMDD_NN"`, un solo head; nunca `create_all()` en producción.
- Otros hosts: Atlas ONE y HRFlow corren en un VPS de IONOS con Docker y Caddy; Cortex en Railway. Las integraciones cruzan hosts por HTTPS con secretos por conexión.
- Runbooks: resembrar la demo del despacho con `scripts/demo_despacho.py --url <prod> --contador-email <correo>`; reabrir un mes con motivo desde Cierre de periodo; nunca `railway up` desde `/mnt/d` (drvfs corrompe la carga).
- Observabilidad hoy: healthchecks y logs estructurados (`arca.accounting` registra todo descuadre rechazado). El plan agrega Sentry, métricas del outbox (pendientes, reintentos, edad del más viejo) y alertas por correo.

## 11. Pruebas

- `pytest` corre en SQLite en memoria con las migraciones aplicadas; fixtures `db` y `client` en `tests/conftest.py`. 388 pruebas al 2026-10-13.
- Cada módulo trae: aislamiento de tenant, partida doble (la suite falla si una póliza descuadra), efecto en saldos de instrumentos, reporte contra ledger, RBAC y paginación. Los formatos externos (CONTPAQi, XML SAT, DIOT, CFDI) llevan archivo dorado.
- Frontend: `npm run typecheck` y `npm run build`; capturas con Edge headless desde Windows para revisar UI.

## 12. Glosario

| Término | Significado |
| --- | --- |
| Póliza | Asiento contable con folio; tipos Ingreso, Egreso y Diario |
| Instrumento | Cuenta de efectivo, banco o tarjeta con saldo propio; la tarjeta es pasivo |
| Devengo | CxC y CxP se registran al emitir, no al cobrar o pagar; el IVA queda "pendiente" hasta el flujo |
| Candado | Mes o ejercicio cerrado que rechaza pólizas; se reabre con motivo |
| Propuesta | Operación sugerida por un agente que un humano aprueba o rechaza |
| Anexo 24 | Contabilidad electrónica del SAT: catálogo y balanza en XML |
| CFDI | Comprobante fiscal digital; PUE pago en una exhibición, PPD en parcialidades, REP complemento de pago |
| DIOT | Declaración informativa de operaciones con terceros |
| PAC | Proveedor autorizado de certificación que timbra CFDI |
| CSD, e.firma | Certificado de sello digital para timbrar; firma electrónica para trámites con el SAT |
| RESICO | Régimen simplificado de confianza |
