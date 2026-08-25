# ARCA M2 — Receivables & Payables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cuentas por cobrar y por pagar con cobros/pagos parciales, contabilizadas desde su creación (devengo) y reflejadas en dashboard y UI.

**Architecture:** Mismo patrón que Income/Expense: modelos explícitos `Receivable`/`Payable` (§58), servicios que orquestan `record_transaction` (tipos RECEIVABLE_COLLECTION / PAYABLE_PAYMENT, ya existentes) + reglas contables centralizadas en `rules.py`. A diferencia de Income, la creación SÍ postea asiento (devengo §18): CxC = Cargo 1200/Abono ingreso; CxP = Cargo gasto/Abono 2100. La cancelación sin pagos postea el asiento inverso (primer uso del patrón de reversos §27).

**Tech Stack:** el existente (FastAPI/SQLAlchemy/Alembic · React/TanStack). Sin dependencias nuevas.

**Spec:** `docs/TASK_PACK.md` §14, §15, §18, §19, §20, §23, §32, §47 + `docs/superpowers/specs/2026-08-24-arca-mvp-design.md`.

## Global Constraints

- Las de M0+M1 (Decimal, tenant NOT NULL, motor contable único, paginación `{items,total,limit,offset}`, errores en español, commits en español).
- `amount_paid` nunca excede `amount`; cobro/pago parcial válido si `0 < monto ≤ saldo restante`.
- Status en BD: `OPEN | PARTIAL | PAID | CANCELLED`. **OVERDUE se calcula** (due_date < hoy y saldo pendiente), no se almacena — se expone como `is_overdue` y como filtro; evita jobs de actualización.
- Cancelar solo con `amount_paid == 0`; postea asiento de reversa (líneas invertidas, `source_type` igual + descripción "Cancelación: …"). Con pagos parciales → 400 (reversos completos llegan después).
- `category_id` requerido en ambos (INCOME para CxC, EXPENSE para CxP): define la cuenta de ingreso/gasto del asiento de devengo, igual que Income/Expense.

## Decisiones (mini-ADR inline)

1. **Devengo al crear** (§18 lo pide explícito): la CxC reconoce ingreso al emitirse, no al cobrarse. El cobro solo mueve 1100↔1200. Simétrico para CxP con 5xxx↔2100.
2. **OVERDUE derivado**, no persistido (ver Global Constraints).
3. Cobros parciales: cada cobro es un `FinancialTransaction` + asiento propios; `amount_paid` acumula; status OPEN→PARTIAL→PAID.

---

### Task 1: Modelos + migración

**Files:** Create `app/models/receivable.py`, `app/models/payable.py`, `alembic/versions/20260824_04_receivables_payables.py`; Modify `app/models/__init__.py`.

**Produces:** `Receivable(organization_id, customer_id FK NOT NULL, description, amount Numeric(14,2), amount_paid Numeric(14,2) default 0, due_date Date, category_id FK, status default 'OPEN', notes, cancelled_at/by/reason, created_by)` + `Payable` espejo con `vendor_id`. Ambos con UUIDPKMixin/TenantMixin/AuditMixin.

- [ ] Modelos + registro en `__init__` + migración a mano (down_revision `20260824_03`); `alembic upgrade head` sobre SQLite scratch; `alembic heads` = 1. Commit.

### Task 2: Reglas contables de devengo, cobro/pago y reversa

**Files:** Modify `app/services/accounting/rules.py`; Test `tests/test_ledger.py` (agregar casos).

**Produces:**
```python
receivable_created_entry(db, org_id, description, amount, date, revenue_account_code, source_id, created_by)   # D 1200 / H revenue
receivable_collected_entry(db, org_id, description, amount, date, source_id, created_by)                        # D 1100 / H 1200
payable_created_entry(db, org_id, description, amount, date, expense_account_code, source_id, created_by)       # D expense / H 2100
payable_payment_entry(db, org_id, description, amount, date, source_id, created_by)                             # D 2100 / H 1100
reversal_of(db, org_id, entry: JournalEntry, description, created_by) -> JournalEntry                           # líneas invertidas del asiento dado
```
`reversal_of` busca las líneas del asiento original y postea (vía `post_journal_entry`, resolviendo account_id→code) el espejo débito↔crédito con `source_type=entry.source_type`, `reference=f"reversal:{entry.id}"`.

- [ ] Tests: cada regla produce el asiento esperado; `reversal_of` deja el saldo neto de las cuentas afectadas en cero. Implementar. Commit.

### Task 3: Dominio receivables

**Files:** Create `app/domains/receivables/{__init__,schemas,service,router}.py`; Modify `app/routers.py`; Test `tests/test_receivables.py`.

**Produces:**
- Schemas: `ReceivableCreate(customer_id, description, amount>0, due_date, category_id, date=hoy?, notes?)` — `date` es la fecha de emisión (default hoy); `CollectionCreate(amount>0, financial_account_id, date?)`; `ReceivableRead(..., amount_paid, balance, is_overdue, status)` con `balance = amount - amount_paid` y `status` reportado como `OVERDUE` si `is_overdue` y status en (OPEN, PARTIAL) — el campo `stored_status` no se expone.
- Service: `create_receivable` (valida customer+categoría del tenant → row → `receivable_created_entry` → evento `receivable.created`), `collect_receivable` (valida monto ≤ balance → `record_transaction(RECEIVABLE_COLLECTION)` → `receivable_collected_entry` → acumula `amount_paid`, recalcula status → evento `receivable.paid` al liquidar), `cancel_receivable` (solo sin pagos; `reversal_of` del asiento de creación + status CANCELLED).
- Router `/api/receivables`: GET lista (filtros `status` incl. OVERDUE computado, paginación, orden due_date asc), POST, GET id, POST `/{id}/collect`, POST `/{id}/cancel`. Roles WRITE_ROLES en mutaciones.

- [ ] Tests §47: crear CxC → asiento devengo (AR y revenue suben, cash no); cobro parcial → PARTIAL, cash ↑, AR baja; segundo cobro liquida → PAID; cobro que excede saldo → 400; cancelar sin pagos → reversa deja trial balance neto 0; cancelar con pagos → 400; tenant isolation (Org A no cobra CxC de Org B → 404). Implementar. Commit.

### Task 4: Dominio payables (espejo)

**Files:** Create `app/domains/payables/{__init__,schemas,service,router}.py`; Modify `app/routers.py`; Test `tests/test_payables.py`.

Igual que Task 3 con vendor/EXPENSE/`payable_created_entry`/`payable_payment_entry`, transacción `PAYABLE_PAYMENT` (egreso), endpoint `POST /{id}/pay`, eventos `payable.created`/`payable.paid`.

- [ ] Tests espejo (incluye: pagar CxP baja cash y baja 2100; balance general sigue cuadrando con pasivo pendiente). Implementar. Commit.

### Task 5: Dashboard real + reportes

**Files:** Modify `app/domains/dashboard/service.py`; Test `tests/test_reports.py` (agregar caso).

- [ ] `summary()`: `receivables` = Σ(amount−amount_paid) de OPEN/PARTIAL; `overdue_receivables` = subset con due_date < hoy; `payables` = Σ saldo CxP. Test: con CxC 7000 (cobrada 2000, vencida) y CxP 4000 → receivables 5000, overdue 5000, payables 4000, y balance general cuadra (AR en activos, AP en pasivos). Commit.

### Task 6: Frontend

**Files:** Create `frontend/src/features/debts/DebtsPage.tsx` (factory compartido CxC/CxP con configs `RECEIVABLES_CONFIG`/`PAYABLES_CONFIG`); Modify `frontend/src/types/api.ts`, `App.tsx` (rutas `/por-cobrar`, `/por-pagar`), `AppLayout.tsx` (nav Ventas→"Por cobrar", Gastos→"Por pagar"; quick actions "Cuenta por cobrar"/"Cuenta por pagar"), `DashboardPage.tsx` (cards "Por cobrar" con subtítulo vencido y "Por pagar", enlazadas).

- [ ] DebtsPage: header con totales (Por cobrar $X / Vencido $Y en rojo), filtros de estado (Abiertas/Vencidas/Pagadas/Canceladas), tabla (contacto, concepto, vence, badge estado —OVERDUE = "Vencido" warn—, pagado/total, saldo), modal de alta (contacto, concepto, monto, categoría, vence, notas) y modal "Registrar cobro/pago" (monto prellenado con saldo, cuenta, fecha), acción cancelar solo sin pagos. Empty states §40. `tsc` + build limpios; smoke local end-to-end. Commit.

### Task 7: Cierre

- [ ] Suite completa + ruff + build; actualizar `docs/MVP_STATUS.md` (M2 done, deuda técnica: reversos con pagos parciales pendientes) y `AGENTS.md` si aplica; merge a main; push (auto-deploy); validar producción: crear CxC/CxP reales vía API, cobrar parcial, verificar dashboard y balance. Commit.

## Self-review

- §14/§15 cubiertos (campos, estados incl. OVERDUE computado, acciones); §18 las 4 reglas nuevas; §19 eventos; §20/§32 dashboard; §47 tests CxC/CxP. Income/Expense NO cambian (una venta de contado sigue siendo Income; CxC es para ventas a crédito — el catálogo §17 ya tiene 1200/2100 sembradas).
- Tipos consistentes: `collect_receivable(db, org_id, receivable, amount, financial_account_id, date, user_id)` ↔ router `/collect`; `pay_payable(...)` ↔ `/pay`.
