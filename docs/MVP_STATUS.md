# MVP STATUS — ARCA

_Actualizado: 2026-10-13 (C-2 apertura y cierre anual, prod `0f23acb`)_

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

- **C-1 Pólizas manuales y catálogo editable** (spec 2026-10-12): `POST /api/accounting/journal-entries` (sólo Diario, cuentas de detalle, nunca las cuentas con saldo espejo: 1100/1200/2100/2200/1400/1490/2300), reverso único por `/reverse`, alta de cuentas de detalle bajo una mayor (`POST /api/accounting/accounts`), renombrar y desactivar sin movimientos; UI con formulario de póliza, reverso desde el diario y catálogo editable.
- **C-2 Apertura y cierre anual** (spec 2026-10-12): póliza de apertura por cuenta cuadrada contra 3200 o 3100 (`GET/POST /api/accounting/opening-balance`, una viva por empresa, se corrige revirtiéndola desde el diario); cierre de ejercicio que traspasa 4xxx/5xxx a 3200 con candado anual `fiscal_year_locks` validado en el motor y reapertura con motivo que revierte la póliza (`GET /api/periods/years`, `POST /years/{año}/close`, `POST /years/{año}/reopen`); el estado de resultados y el dashboard ignoran el cierre, el balance lo incluye y la balanza SAT abre enero con la póliza real. UI: tarjeta de saldos iniciales, tabla de ejercicios en Cierre de periodo y etiquetas "Apertura"/"Cierre anual" en el diario. Demo con venta y renta del año anterior.

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

Plan maestro del MVP e integraciones Atlas (2026-10-12): `docs/MEGA_PLAN_MVP.md`; referencia técnica: `docs/ARCHITECTURE.md`.

- Fase 0 · ROB robustez (outbox durable, webhooks HMAC, rate limiting, expiración de propuestas) en paralelo con la fase 1.
- Fase 1 · B estados financieros NIF (C1 y C2 ya en producción).
- Fase 2 · E importar CFDI, BANK conciliación bancaria, eventos de Atlas ONE.
- Fase 3 · TAX cédula y calendario, DESP flujo del despacho, HRFlow etapa 1.
- Fase 4 · FACT facturación CFDI 4.0 vía PAC (sirve a ARCA, ONE y nómina de HRFlow).
- Fase 5 · CFO proactivo y bandeja mágica con Cortex.

## Blocked

- (nada)

## Technical Debt

- `railway up` desde /mnt/d (WSL drvfs) sube archivos corruptos (NUL bytes). Ya no afecta el flujo normal (deploy vía GitHub), pero no usar `railway up` desde /mnt/d.
- Bundle frontend 713KB (recharts) — code-splitting pendiente.
- Sin rate limiting en /auth (slowapi como cortex) ni lockout de cuentas; tampoco en /api/agent/invoke por llave.
- Propuestas de agente sin expiración ni edición previa a aprobar.
- Sin outbox durable para eventos (bus síncrono en proceso).
- `cash_flow.opening_cash` cuenta saldos iniciales de cuentas creadas dentro del periodo como "apertura".
