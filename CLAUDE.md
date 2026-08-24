# CLAUDE.md — ARCA

Lee `AGENTS.md` primero: ahí viven los invariantes financieros que NUNCA se rompen (partida doble, tenant isolation, Decimal para dinero, saldos solo vía `record_transaction`, reglas contables solo en `app/services/accounting/rules.py`).

## Contexto rápido

- **Qué es:** Financial OS para pymes mexicanas. UX en lenguaje de empresario (español); motor contable formal por debajo. Spec: `docs/TASK_PACK.md`; estado: `docs/MVP_STATUS.md`.
- **Stack:** FastAPI 0.127 + SQLAlchemy 2 + Pydantic v2 + Alembic + PostgreSQL · React 18 + TS + Vite + Tailwind + TanStack Query v5 + Zustand · Railway (Railpack).
- **Layout:** dominios en `app/domains/<x>/` (router/service/schemas); modelos en `app/models/` (registrar módulos nuevos en su `__init__.py` o create_all/autogenerate los omiten); motor contable en `app/services/accounting/`.

## Comandos

```bash
source .venv/bin/activate
pytest                          # 39+ tests, SQLite en memoria
ruff check .
alembic upgrade head && uvicorn app.main:app --reload
cd frontend && npm run dev      # proxy /api → :8000
cd frontend && npm run typecheck && npm run build
```

## Convenciones

- API `/api/<dominio>` plural sin slash final; paginación `{items,total,limit,offset}`; errores `{"detail":"mensaje en español"}`; nunca ORM crudo.
- Migraciones `AAAAMMDD_NN_slug.py` con `revision="AAAAMMDD_NN"`; un solo head; nunca `create_all()` en producción.
- Montos: `Decimal`/`Numeric(14,2)`; schemas con `Field(gt=0, allow_inf_nan=False)`; el front manda strings.
- Commits: Conventional Commits en español.
- UI: tokens semánticos Tailwind (`bg-surface`, `text-muted`…), cero colores crudos; cifras con clase `.figures` (Archivo tabular); copy en español, empty states con CTA.

## Deployment

Railway proyecto ARCA (`c8c39843-…`), servicios Postgres + `ARCA` (conectado a GitHub `Ecamposg95/ARCA`): **push a main = deploy**. Dominio: https://arca-production-d769.up.railway.app. Config de build en `railpack.json` (el build de frontend va en el step `build`, no en `install`). **OJO:** no usar `railway up` desde `/mnt/d` (drvfs corrompe el upload); si hiciera falta un deploy manual, hacerlo desde un clon nativo.
