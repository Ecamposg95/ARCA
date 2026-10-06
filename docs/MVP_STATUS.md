# MVP STATUS — ARCA

_Actualizado: 2026-10-05 (portal de despacho)_

## Done

- M0 Foundation: repo, arquitectura Atlas, config fail-fast, healthchecks, Alembic (3 migraciones, un head), auth JWT (register/login/refresh/me), multi-tenancy validada por membresía, roles.
- Onboarding §29-30: registro → empresa → OWNER → catálogo contable → categorías → cuenta "Caja" con saldo inicial.
- Accounting core: ledger double-entry (motor centralizado con invariante SUM(debit)==SUM(credit)), catálogo §17, motor de reglas §18, balanza.
- M1 Money: cuentas financieras, movimientos (lock → refresh → re-check), ingresos, gastos, traspasos, clientes, proveedores.
- Reportes: Estado de Resultados, Balance General (cuadra por construcción), Flujo de efectivo, dashboard agregado.
- Frontend completo (React+TS+Vite+Tailwind+TanStack): onboarding, dashboard con gráficos, ingresos, gastos, movimientos, cuentas, contactos, contabilidad (diario/balanza/catálogo), reportes, configuración.
- Tests: 39 (tenant isolation, partida doble, efectos en saldos, reportes vs ledger, RBAC, paginación, auth).
- CI GitHub Actions (postgres:16 + ruff + pytest + typecheck/build frontend).
- Railway: PostgreSQL + servicio `ARCA` conectado al repo GitHub (`Ecamposg95/ARCA`, auto-deploy en push a main), dominio https://arca-production-d769.up.railway.app
- Deployment productivo validado end-to-end (registro real → ingreso → gasto → dashboard/balance/balanza correctos vía HTTPS).

## In Progress

- (nada)

- M2 Business Finance: CxC y CxP con devengo (§18), cobros/pagos parciales, OVERDUE calculado, cancelación con asiento de reversa (`reversal_of`), dashboard con saldos reales, páginas Por cobrar / Por pagar. 54+ tests.
- Tema visual Atlas Cortex (teal #2c9aa6, Plus Jakarta Sans + JetBrains Mono, dark tokens definidos).
- Instrumentos con naturaleza: tarjetas de crédito contabilizadas como pasivo (2200) con límite y crédito disponible, pago de tarjeta que no duplica el gasto, método de pago normalizado en cada movimiento.
- Folios de póliza (convención mexicana Ingreso/Egreso/Diario, serie por organización y mes) con contador transaccional y respaldo de asientos históricos.
- **A0 Fundación agéntica** (ADR-005): llaves de agente por organización (`ak_…`, sha256, scopes, revocables), catálogo de 18 herramientas (14 lectura + 4 propose), `/api/agent/tools` + `/api/agent/invoke` con auditoría total, bandeja de propuestas con aprobación humana que ejecuta los services reales, UI (Configuración→Agentes, página Propuestas con badge). 64 tests.
- **Portal de despacho** (spec 2026-10-05): cartera del usuario en `GET /api/portfolio` con semáforo (mes sin cerrar, vencidos por pagar, propuestas pendientes), alta de otra empresa en `POST /api/organizations`, selector de empresa en el encabezado, página "Mis empresas" (`/despacho`), rol real desde `/api/me`. Demo: `scripts/demo_despacho.py`.
- **Puente a CONTPAQi** (spec 2026-10-05): cuenta equivalente por cuenta (`accounts.contpaqi_code`, editable en el catálogo), exportación de las pólizas del mes en el layout de "Cargado de pólizas" (`GET /api/accounting/contpaqi`, vista previa en `/contpaqi/preview`), botón por mes en Cierre de periodo. **Formato de referencia, sin verificar contra un CONTPAQi real**: falta calcarlo de un "bajado de pólizas". "Descargar Excel" de Reportes ya descarga con sesión (respondía 401).
- **Contabilidad electrónica SAT** (spec 2026-10-06): código agrupador por cuenta (`accounts.sat_code`, defaults del catálogo de ARCA, selector con la lista oficial de 1,080 códigos), catálogo y balanza del mes en XML 1.3 del Anexo 24 validados contra los XSD oficiales (`GET /api/accounting/sat/catalogo`, `/sat/balanza`, vista previa en `/sat/preview`), botón SAT por mes en Cierre de periodo. Sin sellar: el sello y el envío los hace el contador.

## Next

- A2 MCP server (exponer el catálogo vía MCP autenticado con AgentKey) o A1 ARCA CFO (chat con Claude; requiere ANTHROPIC_API_KEY) — orden a decidir.
- A3 Magic Inbox (documento → propuesta con evidencia).
- M3/M4 restantes: aging detallado de cartera, tendencias.
- Reversal journal entries para cancelar operaciones pagadas (parciales incluidas).

## Blocked

- (nada)

## Technical Debt

- `railway up` desde /mnt/d (WSL drvfs) sube archivos corruptos (NUL bytes). Ya no afecta el flujo normal (deploy vía GitHub), pero no usar `railway up` desde /mnt/d.
- Bundle frontend 713KB (recharts) — code-splitting pendiente.
- Sin rate limiting en /auth (slowapi como cortex) ni lockout de cuentas; tampoco en /api/agent/invoke por llave.
- Propuestas de agente sin expiración ni edición previa a aprobar.
- Sin outbox durable para eventos (bus síncrono en proceso).
- `cash_flow.opening_cash` cuenta saldos iniciales de cuentas creadas dentro del periodo como "apertura".
