# ARCA

**Financial Operating System by Atlas Tech**

ARCA permite a un emprendedor o pequeña empresa operar sus finanzas sin conocimientos contables: registra ventas, gastos, cobros y pagos en su propio lenguaje, y por debajo un motor contable formal (partida doble, auditable) produce estados financieros exactos.

```text
OPERACIÓN → EVENTO FINANCIERO → MOVIMIENTO → CONTABILIDAD → ESTADOS FINANCIEROS
```

## Arquitectura

Servicio único (convención Atlas): FastAPI sirve el API bajo `/api/*` y la SPA React construida vía catch-all. PostgreSQL como fuente de verdad; Alembic ejecuta migraciones en cada arranque.

```text
app/
├── main.py             # FastAPI, healthchecks, SPA catch-all
├── config.py           # Settings congelada, fail-fast en producción
├── database.py         # engine + sesión (pool_pre_ping)
├── models/             # SQLAlchemy (mixins: UUID pk, tenant NOT NULL, auditoría)
├── domains/<x>/        # router / service / schemas por dominio
├── services/
│   ├── accounting/     # MOTOR CONTABLE: engine (partida doble), rules, coa
│   ├── transactions.py # único punto que muta saldos (lock → refresh → re-check)
│   └── onboarding.py   # cadena de alta de empresa
├── security/           # JWT, bcrypt, contexto de organización, roles
├── core/events.py      # bus de eventos interno
frontend/               # React 18 + TS + Vite + Tailwind + TanStack Query
alembic/versions/       # migraciones AAAAMMDD_NN_descripcion.py
tests/                  # pytest (modo dual SQLite / PostgreSQL)
docs/                   # TASK_PACK, decisiones (ADRs), MVP_STATUS
```

## Requisitos

- Python 3.11+
- Node 20+
- PostgreSQL (producción; en local basta SQLite)

## Instalación local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cd frontend && npm install && cd ..
```

## Ejecutar

```bash
# API (usa SQLite local por default)
alembic upgrade head
uvicorn app.main:app --reload

# Frontend en modo dev (proxy /api → :8000)
cd frontend && npm run dev
```

## Variables de entorno

Ver `.env.example`. En producción son obligatorias `DATABASE_URL` y `SECRET_KEY` (≥32 caracteres); la app no arranca sin ellas.

## Migraciones

```bash
alembic upgrade head      # aplicar
alembic heads             # debe imprimir EXACTAMENTE un head
```

Convención de nombres: `AAAAMMDD_NN_descripcion.py` con `revision = "AAAAMMDD_NN"`. Nunca `Base.metadata.create_all()` en producción.

## Seed de datos demo (solo desarrollo)

```bash
python scripts/seed_demo.py
```

Crea "ARCA Demo Company" (demo@arca.test / demodemo123) con clientes, proveedores, cuentas y 4 meses de operaciones.

## Tests

```bash
pytest                                        # modo SQLite en memoria (rápido)
TEST_DATABASE_URL=postgresql://... pytest     # modo PostgreSQL real (CI)
ruff check .
```

## Deployment (Railway)

Servicios: PostgreSQL + `ARCA` (API + SPA), conectado al repo GitHub: **cada push a `main` despliega automáticamente**. Build con Railpack (`railpack.json`); el arranque ejecuta `alembic upgrade head` antes de uvicorn. Healthcheck: `GET /api/health`. Producción: https://arca-production-d769.up.railway.app

## Estado del MVP

Ver [`docs/MVP_STATUS.md`](docs/MVP_STATUS.md). Spec del producto: [`docs/TASK_PACK.md`](docs/TASK_PACK.md). Reglas para agentes: [`AGENTS.md`](AGENTS.md).
