# ARCA MVP — Design Decisions (M0 + M1)

**Date:** 2026-08-24
**Source spec:** `docs/TASK_PACK.md` (the authoritative product spec, provided by Emmanuel)
**Conventions source:** Atlas Development Framework (canon, in the Atlas Brain vault) + survey of Atlas-Rmazh, atlas-cortex, dasic-atlas-api.

This document records how the task pack's open choices were resolved against Atlas canon. Where the two disagreed, Atlas canon won (the task pack itself mandates this: "priorizar consistencia con los demás repositorios Atlas").

## What we are building first

M0 (foundation + deploy) and M1 (money), with the minimal double-entry ledger underneath from day one, per task pack §2. M2 (receivables/payables), M3 (accounting UX), M4 (full reporting) follow in later plans. Basic customers/vendors CRUD is pulled into this slice because Income/Expense reference them.

## Decisions

| # | Question | Decision | Rationale |
|---|---|---|---|
| 1 | Deployment topology | **Single app service** — FastAPI serves the built React SPA via catch-all; Railway runs 2 services: Postgres + app | Atlas canon ("No Docker — Railway con nixpacks", single service). Task pack §42 lists API+Web separately but §6 says defer to Atlas standards. Recorded as ADR-001. |
| 2 | Repo layout | `app/` (FastAPI) + `frontend/` (Vite SPA) + `alembic/` + `tests/` + `scripts/` + `docs/`. New feature modules use `app/domains/<x>/` (router/service/schemas); shared models in `app/models/` | ADF canon layout + dasic's go-forward domains pattern. The task pack's `apps/`+`modules/`+`engines/` tree is satisfied conceptually: engines live in `app/services/accounting/`. |
| 3 | Primary keys | **UUID string (CHAR 36) PKs on all tables** | Task pack mandate ("IDs UUID"). Deliberate deviation from the integer-PK norm in older Atlas repos; ADF spec itself shows UUID. ADR-002. |
| 4 | Tenancy | `organization_id` **NOT NULL** on every tenant table; `X-Organization-ID` header validated against membership in `get_current_org_id`; every query filters by org | Golden Rules 1–2; fixes Rmazh's known nullable-tenant debt. |
| 5 | Money type | `Numeric(14, 2)` / Python `Decimal`, never float. Amounts validated `> 0` at the schema boundary | Task pack §33; Atlas money rules. ADR-004. |
| 6 | Ledger | Double-entry: `Account`, `JournalEntry`, `JournalEntryLine`; `sum(debit) == sum(credit)` enforced in the posting service (single choke point) + tests. Balances derived from ledger; `FinancialAccount.current_balance` maintained transactionally (lock → refresh → re-check) | Task pack §16; Rmazh money patterns (derived balances, TOCTOU rule). ADR-003. |
| 7 | Accounting rules | Centralized in `app/services/accounting/rules.py` — one function per business event (income_paid, expense_paid, …), mapping to seeded account codes. No journal-entry construction in routers | Task pack §18; Golden Rule 7. |
| 8 | Chart of accounts | Seeded per organization at creation from the §17 catalog (codes 1000–5700). Categories seeded per org with a `account_code` mapping to CoA | Task pack §17, §13, §30. |
| 9 | Auth | JWT HS256 via python-jose, `Authorization: Bearer`; passlib+bcrypt; access token 12h; **refresh token flow implemented** (30-day refresh JWT, `POST /api/auth/refresh`) | Atlas canon transport; refresh tokens are a task-pack §29 requirement no Atlas repo has — deliberate addition. |
| 10 | Roles | `OrganizationMember.role` ∈ OWNER, ADMIN, ACCOUNTANT, MEMBER, VIEWER; `require_role([...])` dependency. VIEWER is read-only; accounting section gated to OWNER/ADMIN/ACCOUNTANT | Task pack §7, §25. Cortex-style policy engine deferred until roles differentiate further. |
| 11 | Settings | Frozen `Settings` dataclass + `lru_cache` in `app/config.py`; fail-fast on missing `DATABASE_URL`/`SECRET_KEY` (≥32 chars) in production; **no dev secret fallback in prod ever** | dasic pattern, best of breed. |
| 12 | Env vars | `DATABASE_URL` (normalized to `postgresql://`), `SECRET_KEY`, `CORS_ORIGINS`, `ENV`, `PORT`, `DOCS_ENABLED` (default off in prod), `ACCESS_TOKEN_EXPIRE_MINUTES` | Survey §9.2 conflict resolution. |
| 13 | Migrations | Alembic only (no `create_all()` in prod); `alembic upgrade head` in Railway `startCommand`; dated names `YYYYMMDD_NN_slug.py` with `revision = "YYYYMMDD_NN"`; single head enforced; every model module imported in `env.py` | cortex deploy pattern + dasic naming. |
| 14 | API conventions | All under `/api/<domain>`, plural nouns, **no trailing slash**; routers own `/<x>` prefix, mounted with `prefix="/api"`; pagination envelope `{items, total, limit, offset}` (tested); errors `{"detail": "human message"}`; never return raw ORM — `Schema.model_validate()` | ADF canon; one envelope shape, tested (fixes Rmazh drift). |
| 15 | Events | Synchronous in-process `EventBus` in `app/core/events.py`; subscribers in `app/subscribers/`; handler exceptions caught+logged. Events per task pack §19. Durable outbox deferred (noted as future work) | ADF canon. |
| 16 | Frontend stack | React 18 + TS + Vite 5 + React Router v6 + **TanStack Query v5** (server state) + Zustand (auth/UI state) + Axios client + Tailwind (`darkMode: 'class'`, semantic CSS-var tokens, zero raw colors) + Recharts | dasic/canon hybrid per survey §9.2. |
| 17 | Frontend structure | `frontend/src/{api,stores,types,components/ui,components/layout,features/<x>/{pages,components,hooks}}` | Feature-first (dasic) with canon api/store dirs. |
| 18 | Testing | pytest + httpx; dual-mode conftest (SQLite in-memory default; `TEST_DATABASE_URL` → real Postgres with `alembic upgrade head`); mandated tests: tenant isolation, cross-tenant denial, double-entry balance, income/expense effects, pagination shape, auth | dasic dual-mode + Golden Rules minimum suite. |
| 19 | Lint/CI | ruff (`F`,`E9`,`B`, line 120, ignore B008/B904); GitHub Actions: postgres:16 service + ruff + pytest + frontend tsc/build. CI validates only; Railway deploys on push to main | dasic tooling. |
| 20 | Language | UI copy in Spanish (task pack terminology §39); code/identifiers in English; commits Conventional-Commits in Spanish | Atlas practice. |
| 21 | Onboarding | `POST /api/auth/register` performs the full §29 chain: user → organization → OWNER membership → CoA seed → default categories → default "Caja" cash account. Onboarding UI keeps §30's 4 short steps | Task pack §29–30. |
| 22 | Cancellations | No hard deletes of posted entities. Status `CANCELLED` + `cancelled_at/by/reason` columns on financial docs; reversal journal entries deferred to a later milestone (architecture allows: entries reference `source_type/source_id`) | Task pack §26–27. |

## Domain model (M0+M1 tables)

`users`, `organizations`, `organization_members`, `customers`, `vendors`, `categories`, `financial_accounts`, `financial_transactions`, `incomes`, `expenses`, `accounts` (CoA), `journal_entries`, `journal_entry_lines`. Receivables/payables tables deferred to M2 plan.

All tenant tables: UUID pk, `organization_id` FK NOT NULL indexed, audit timestamps, soft-delete `deleted_at` where it makes sense (contacts, categories, financial_accounts — never journal entries).

## Non-goals (this slice)

Everything in task pack §51, plus: receivables/payables (M2), reversal entries, module feature-flag system (single product for now; add `require_module` when a second module ships), Postgres RLS, durable outbox, rate limiting.
