# TASK PACK MAESTRO — ARCA MVP

> Spec autoritativa del producto, provista por Emmanuel Campos (2026-08-24).
> Las decisiones de implementación derivadas están en `docs/superpowers/specs/2026-08-24-arca-mvp-design.md`.

## 0. Identidad del proyecto

**Nombre:** ARCA — **Repositorio:** `atlas-arca` — **Tipo:** Financial Operating System / Accounting Platform — **Organización:** Atlas Tech — **Deployment:** Railway (project ID c8c39843-5939-4bc2-8dca-70978da2df89) — **Estado:** MVP / Greenfield — **Arquitectura:** estándares Atlas.

ARCA: plataforma financiera y contable para que un emprendedor o pequeña empresa opere sus finanzas sin conocimientos contables avanzados, con un motor contable formal, auditable y extensible por debajo.

## 1. North Star

MVP funcional donde una persona pueda: crear su empresa; registrar clientes y proveedores; registrar ingresos y gastos; registrar cobros y pagos; administrar cuentas de efectivo/banco; consultar CxC y CxP; visualizar su situación financiera; obtener Estado de Resultados y Balance General; visualizar flujo de efectivo; todo respaldado por un ledger contable; entender su negocio sin saber contabilidad.

> El usuario administra su negocio. ARCA traduce sus operaciones a finanzas y contabilidad.

## 2. Objetivo del primer deployment

App completamente desplegada en Railway con: frontend, backend, PostgreSQL, auth, multi-tenancy, empresa inicial, dashboard, ingresos, gastos, clientes, proveedores, cuentas financieras, movimientos, ledger contable mínimo, reportes financieros básicos. Usable end-to-end con datos reales desde el navegador.

## 3. Dos niveles conceptuales

- **Nivel 1 — Business UX:** Vendí / Cobré / Compré / Gasté / Pagué / Me deben / Debo / Tengo / Gané / Perdí.
- **Nivel 2 — Accounting Engine:** transacción, cuenta, débito, crédito, journal entry, ledger, balance, conciliación, período, trazabilidad.

No exponer complejidad contable innecesaria al usuario general.

## 4. Principios no negociables

API-first · multi-tenant desde día cero · backend como autoridad · PostgreSQL fuente de verdad · IDs UUID · soft-delete donde tenga sentido · auditoría · timestamps consistentes · arquitectura modular · separación dominio/infraestructura · tipado fuerte · validación estricta · seguridad por organización · APIs bajo `/api/*` · migraciones versionadas · tests del dominio crítico · deploy reproducible · sin lógica financiera crítica solo en frontend · UI desacoplada de reglas contables · preparado para agentes IA sin depender de ellos.

## 5. Stack

Backend: Python 3.11+, FastAPI, SQLAlchemy 2.x, PostgreSQL, Pydantic v2, Alembic, JWT, pytest, httpx. Frontend: React, TypeScript, Vite, React Router, Zustand (o state mgmt Atlas vigente), Axios, componentización reusable. Deployment: Railway (PostgreSQL, API, Web, env vars, health checks, migrations). No introducir infraestructura compleja prematuramente.

## 6. Estructura de alto nivel

Referencia conceptual: apps/{api,web}, modules/{auth,organizations,users,contacts,customers,vendors,accounts,transactions,income,expenses,receivables,payables,accounting,reporting}, engines/{ledger,accounting,financial_reporting}, shared/, migrations/, tests/, docs/. **No seguir ciegamente si contradice el ADF existente; priorizar consistencia con los demás repos Atlas.**

## 7. Modelo de dominio MVP

- **Organization:** id, name, legal_name, tax_id, currency, country, timezone, created_at, updated_at. Defaults: MXN / MX / America/Mexico_City.
- **User:** id, email, password_hash, name, status, created_at, updated_at.
- **OrganizationMember:** organization_id, user_id, role. Roles: OWNER, ADMIN, ACCOUNTANT, MEMBER, VIEWER.

## 8. Contactos

- **Customer:** id, organization_id, name, legal_name, tax_id, email, phone, notes, status.
- **Vendor:** misma filosofía. No construir CRM completo.

## 9. Financial Accounts

**FinancialAccount** — tipos: CASH, BANK, CREDIT_CARD, OTHER. Campos: id, organization_id, name, type, currency, opening_balance, current_balance, institution, last_four, active, created_at. Ejemplos: Caja, BBVA Operativa, Santander Nómina, AMEX.

## 10. Transaction model

**FinancialTransaction** — tipos: INCOME, EXPENSE, TRANSFER, RECEIVABLE_COLLECTION, PAYABLE_PAYMENT, ADJUSTMENT. Campos: id, organization_id, financial_account_id, transaction_type, amount, currency, date, description, reference, status, source_type, source_id, created_by, created_at, updated_at.

Mantener separación: Business Operation → Financial Transaction → Accounting Entry.

## 11. Ingresos

`+ Nuevo ingreso`: fecha, cliente opcional, concepto, monto, cuenta destino, estado, notas. Estados: PENDING, PAID, CANCELLED. Al pagar: movimiento financiero → saldo → evento financiero → asiento contable.

## 12. Gastos

`+ Nuevo gasto`: proveedor, concepto, categoría, monto, fecha, cuenta, método, referencia, notas. Estados: PENDING, PAID, CANCELLED. Al pagar: Expense → FinancialTransaction → Accounting Entry → Ledger.

## 13. Categorías

Income: Ventas, Servicios, Intereses, Otros ingresos. Expense: Nómina, Renta, Servicios, Marketing, Software, Transporte, Viáticos, Inventario, Honorarios, Impuestos, Equipo, Otros. Cada categoría mapea internamente a cuentas contables.

## 14. Cuentas por cobrar

**Receivable:** id, organization_id, customer_id, description, amount, due_date, status, amount_paid, created_at. Estados: OPEN, PARTIAL, PAID, OVERDUE, CANCELLED. Acción: "Registrar cobro".

## 15. Cuentas por pagar

**Payable:** vendor, amount, due_date, status, amount_paid. Acción: "Registrar pago".

## 16. Accounting core

Double-entry ledger correcto (no sistema de alta complejidad aún).

- **Account:** id, organization_id, code, name, type (ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE), parent_id, active.
- **JournalEntry:** id, organization_id, date, description, reference, source_type, source_id, status, created_at.
- **JournalEntryLine:** id, journal_entry_id, account_id, debit, credit, description.

**Constraint obligatorio: SUM(debit) == SUM(credit).** No permitir asientos desbalanceados.

## 17. Catálogo contable inicial (seed automático por organización)

1000 Activo · 1100 Caja y Bancos · 1200 Cuentas por Cobrar · 1300 Otros Activos · 2000 Pasivo · 2100 Cuentas por Pagar · 3000 Capital · 3100 Capital · 3200 Resultados Acumulados · 4000 Ingresos · 4100 Ventas · 4200 Servicios · 5000 Gastos · 5100 Gastos Operativos · 5200 Nómina · 5300 Renta · 5400 Software · 5500 Marketing · 5600 Transporte · 5700 Otros Gastos.

## 18. Accounting rules engine (centralizado, no hardcode en controllers)

- Ingreso pagado: Debit Bank/Cash — Credit Revenue.
- Gasto pagado: Debit Expense — Credit Bank/Cash.
- CxC creada: Debit Accounts Receivable — Credit Revenue.
- Cobro CxC: Debit Bank — Credit Accounts Receivable.
- CxP creada: Debit Expense — Credit Accounts Payable.
- Pago CxP: Debit Accounts Payable — Credit Bank.

## 19. Eventos del dominio

income.created/paid, expense.created/paid, receivable.created/paid, payable.created/paid, transaction.created, journal_entry.created. Mecanismo interno simple (sin Kafka). Objetivo: desacoplar Business Operation → Financial Event → Accounting Engine.

## 20–21. Dashboard principal + gráficos

Cards: Disponible (cash), Ingresos este mes, Gastos este mes, Resultado, Por cobrar, Por pagar. Gráficos: Cash Flow (entradas vs salidas), Revenue vs Expenses por mes, distribución de gastos por categoría. Interfaz ejecutiva: jerarquía, espacio, tipografía, cifras grandes, tablas limpias.

## 22. Navegación

ARCA · Inicio · Dinero (Movimientos) · Ventas (Ingresos, Por cobrar, Clientes) · Gastos (Por pagar, Proveedores) · Contabilidad (Libro diario, Mayor, Balanza) · Reportes · Empresa/Configuración.

## 23. Quick action

`+ Nuevo`: Ingreso, Gasto, Cuenta por cobrar, Cuenta por pagar, Transferencia, Cliente, Proveedor. Operaciones principales a 1–2 clics.

## 24. Financial reporting (dinámico desde el ledger, nunca almacenado manualmente)

- **Estado de Resultados:** Ingresos − Gastos = Utilidad/Pérdida. Filtros: este mes, mes anterior, este año, custom.
- **Balance General:** Activos / Pasivos / Capital. Debe cumplirse Assets = Liabilities + Equity.
- **Flujo de efectivo (MVP):** Opening Cash + Inflows − Outflows = Closing Cash.

## 25. Accounting UX

Sección "Contabilidad" visible para Owner/Admin/Accountant: catálogo de cuentas, pólizas, libro mayor, balanza. El usuario general puede ignorarla.

## 26. Audit trail

created_by/created_at/updated_by/updated_at/source en operaciones financieras. Futuro: cancelled_at/by/reason. Nunca eliminar silenciosamente transacciones contables.

## 27. Cancelaciones

Patrón ACTIVE/CANCELLED desde ahora; reversal journal entries en fases posteriores. Arquitectura preparada para reversos.

## 28. Multi-tenancy

Toda entidad de negocio con organization_id. Nunca confiar en organization_id del frontend sin validar membresía. Tenant isolation en todos los queries + tests específicos (Org A no puede leer Org B aunque conozca UUIDs).

## 29. Auth

Register, Login, Logout, Refresh token, Current user. Primer usuario: Create User → Create Organization → OWNER → Seed CoA → Default Cash account → Dashboard.

## 30. Onboarding MVP (corto)

1) ¿Cómo se llama tu negocio? 2) ¿A qué se dedica? (opciones) 3) ¿Con cuánto dinero inicia ARCA? (opcional) 4) Listo. ARCA configura empresa, moneda, catálogo, cuenta inicial, categorías. No exponer "catálogo contable" en onboarding.

## 31. API (REST limpio)

/api/auth/ · /api/me/ · /api/organizations/ · /api/customers/ · /api/vendors/ · /api/accounts/ · /api/transactions/ · /api/income/ · /api/expenses/ · /api/receivables/ · /api/payables/ · /api/accounting/{accounts,journal-entries,ledger,trial-balance}/ · /api/reports/{profit-loss,balance-sheet,cash-flow}/ · /api/dashboard/.

## 32. Dashboard API

`GET /api/dashboard/summary` agregado: cash, monthly_revenue, monthly_expenses, monthly_profit, receivables, overdue_receivables, payables, cash_flow[], revenue_vs_expenses[], expense_categories[].

## 33. Validaciones financieras

amount > 0. Rechazar NaN, Infinity, negativos, monedas inválidas, fechas imposibles. Usar Decimal, nunca float.

## 34. Moneda

MVP: MXN. Modelo con currency_code para futuro. Sin FX aún.

## 35. México

Mercado inicial MX. NO construir aún: SAT, CFDI, DIOT, declaraciones, cálculo fiscal, contabilidad electrónica, nómina, complementos de pago. SÍ preparar: tax_id, fiscal fields, document references.

## 36. Magic Inbox

No es requisito del primer deployment. Dejar espacio conceptual para ingestión de documentos en fases siguientes.

## 37. AI

No convertir IA en dependencia del MVP. Resultados exactos con reglas deterministas. Futuro: ARCA CFO vía Financial API. Nunca LLM → escrituras directas a BD.

## 38. UI/UX direction

Modern financial operating system (fintech, Stripe, Linear, Ramp, Mercury, premium SaaS), NO legacy accounting software. Limpia, sobria, enterprise, accesible, alta densidad útil, excelente jerarquía, cifras grandes, navegación clara, tablas profesionales, microinteracciones discretas. No copiar interfaces.

## 39. Terminología UX

Preferir: Ingresos, Gastos, Dinero, Por cobrar, Por pagar, Movimientos, Ganancia, Clientes, Proveedores. Evitar exponer: Debe, Haber, Pólizas, Cuenta T, Auxiliares, Partida doble (solo dentro de Contabilidad).

## 40. Empty states

Todas las pantallas con empty states útiles + CTA. Sin tablas vacías sin explicación.

## 41. Seed / demo data

Mecanismo simple de datos demo en desarrollo: "ARCA Demo Company" con 5 clientes, 5 proveedores, 2 cuentas bancarias, ingresos, gastos, CxC, CxP, journal entries, 3–6 meses de datos. No cargar demo automáticamente en producción.

## 42. Railway deployment

Servicios: PostgreSQL, API, Web. Variables: DATABASE_URL, JWT_SECRET, ENVIRONMENT, CORS_ORIGINS, FRONTEND_URL, API_URL (usar nombres reales conforme al estándar Atlas).

## 43. Migrations

Deploy ejecuta `alembic upgrade head`. Nunca `Base.metadata.create_all()` en producción.

## 44. Healthcheck

`GET /health` → `{"status": "ok"}` (idealmente API, DB, version, environment sin info sensible).

## 45. Logging

Estructurado. Registrar: startup, errors, auth failures relevantes, request errors, financial rule failures. No registrar passwords, JWT, info sensible.

## 46. Security baseline

Password hashing seguro, secrets fuera del repo, JWT expiration, CORS restrictivo, tenant isolation, validación, ORM contra SQLi, errores sanitizados, endpoints protegidos, roles, debug OFF en producción.

## 47. Tests críticos

Tenant isolation (Org A ≠ Org B) · double entry (debit == credit) · ingreso pagado (cash ↑, revenue ↑) · gasto (cash ↓, expense ↑) · crear y cobrar CxC · crear y pagar CxP · Estado de Resultados consistente con ledger · Balance (Assets = Liabilities + Equity).

## 48. Error handling

Errores para humanos. "No puedes eliminar esta cuenta porque tiene movimientos." / "El monto debe ser mayor a cero." Evitar IntegrityError crudos y 422 oscuros.

## 49. Definition of Done — MVP 0

Repo estructurado · README · entorno local reproducible · Railway configurado · PostgreSQL + API + frontend desplegados · HTTPS · registro de usuario · creación de empresa · tenant isolation · dashboard · clientes · proveedores · cuentas financieras · ingresos · gastos · CxC · CxP · saldos correctos · ledger double-entry · Estado de Resultados · Balance General · flujo básico · datos persistentes · migraciones · healthcheck · tests críticos.

## 50. Milestone plan

- **M0 Foundation:** repo, arquitectura, DB, auth, organization, multi-tenancy, Railway, CI. → ARCA accesible en producción.
- **M1 Money:** financial accounts, transactions, income, expenses. → cuánto dinero tiene, entra y sale.
- **M2 Business Finance:** customers, vendors, receivables, payables, collections, payments. → quién le debe y a quién debe.
- **M3 Accounting Engine:** CoA, journal entries, rules engine, general ledger, trial balance. → contabilidad auditable.
- **M4 Financial Intelligence:** P&L, Balance Sheet, Cash Flow, dashboard, trends. → ARCA explica el negocio.

## 51. Fuera de alcance

SAT APIs, PAC, CFDI, nómina, inventarios, compras avanzadas, cotizaciones, POS, bancos vía API, Open Banking, conciliación automática, IA generativa, OCR, activos fijos, presupuestos, centros de costo, consolidación, multi-moneda, FX, contabilidad fiscal avanzada, despacho multiempresa, mobile apps.

## 52. Decision log

`/docs/decisions/` con ADRs para decisiones estructurales (multi-tenancy, ledger, eventos, money data type).

## 53. AGENTS.md

Explicar: qué es ARCA, North Star, arquitectura, dominios, invariantes financieros, multi-tenancy, ejecutar/testear/desplegar, qué no modificar, reglas para features. Incluir: nunca romper double-entry; nunca entidades financieras sin organization_id; nunca float para dinero; nunca acceso cross-tenant; nunca lógica contable crítica solo en frontend.

## 54. README

Descripción, arquitectura, requisitos, instalación, variables, migrations, seed, tests, Railway, estructura, status del MVP.

## 55. Primera sesión

1) Analizar estándares Atlas 2) detectar patrones reutilizables 3) definir estructura 4) plan técnico 5) backlog 6) dependencias 7) implementar M0 8) desplegar en Railway 9) validar 10) continuar M1. No hacer semanas de arquitectura antes de desplegar.

## 56. Estrategia: vertical slices

Create income: DB → Domain → API → UI → Accounting → Test → Production. Después Expense, después Receivable. Validar ARCA continuamente.

## 57. Prioridad de calidad

1 Correctitud financiera · 2 Seguridad · 3 Integridad de datos · 4 UX · 5 Performance · 6 Extensibilidad. Una interfaz hermosa con un ledger incorrecto es un producto inválido.

## 58. Principio arquitectónico crítico

No convertir FinancialTransaction en tabla universal. Mantener conceptos explícitos: Income, Expense, Receivable, Payable, FinancialTransaction, JournalEntry, JournalEntryLine. Duplicación controlada > modelo genérico inmantenible.

## 59. Preparación para Atlas ONE

Conservar source_type, source_id, external_reference en entidades pertinentes para operaciones externas futuras (Atlas ONE → SaleConfirmed → ARCA).

## 60. Futura arquitectura

ARCA → Money, Revenue, Expenses, Receivables, Payables, Accounting, Treasury, Tax, Assets, Budgeting, Reporting, Intelligence (ARCA CFO). El MVP no debe impedir esta evolución.

## 61–62. Experiencia objetivo / wow moment

El usuario debe pensar "aquí entiendo mi negocio". Primer wow: crear empresa, registrar 3–5 operaciones, ver automáticamente efectivo, ingresos, gastos, utilidad, CxC/CxP, Estado de Resultados, Balance. "Yo registré operaciones normales y ARCA hizo la contabilidad por mí."

## 63. Criterio de éxito

Usar una empresa real varias semanas y que ARCA responda confiablemente: cuánto tiene, ingresó, gastó, ganó, le deben, debe, qué movimientos y asientos hay debajo.

## 64. Output esperado

Arquitectura inicial, README, AGENTS.md, ADRs, backend, frontend, schema, migrations, tests, seed, Railway config, deployment funcional. Mantener `/docs/MVP_STATUS.md` (Done / In Progress / Next / Blocked / Technical Debt).

## 65. Instrucción final

No clonar CONTPAQi. Rigor contable profesional con experiencia en lenguaje del empresario. Loop: OPERACIÓN → EVENTO FINANCIERO → MOVIMIENTO → CONTABILIDAD → ESTADOS FINANCIEROS → INTELIGENCIA. **Construir, desplegar, validar y después ampliar. Comenzar por M0 y M1.**
