# MVP STATUS — ARCA

_Actualizado: 2026-08-24 (M2)_

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

## Next

- M3/M4 restantes: aging detallado de cartera, tendencias, selector multi-empresa en UI.
- Reversal journal entries para cancelar operaciones pagadas (parciales incluidas).
- Selector de organización multi-empresa en UI (el backend ya lo soporta vía X-Organization-ID).
- Rol real desde /api/me en el frontend (hoy asume OWNER para navegación).

## Blocked

- (nada)

## Technical Debt

- `railway up` desde /mnt/d (WSL drvfs) sube archivos corruptos (NUL bytes). Ya no afecta el flujo normal (deploy vía GitHub), pero no usar `railway up` desde /mnt/d.
- Bundle frontend 713KB (recharts) — code-splitting pendiente.
- Sin rate limiting en /auth (slowapi como cortex) ni lockout de cuentas.
- Sin outbox durable para eventos (bus síncrono en proceso).
- `cash_flow.opening_cash` cuenta saldos iniciales de cuentas creadas dentro del periodo como "apertura".
