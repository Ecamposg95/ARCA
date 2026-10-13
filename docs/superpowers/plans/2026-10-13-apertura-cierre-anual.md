# Apertura y cierre anual (C-2) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el contador capture los saldos iniciales de la empresa en una póliza de apertura y cierre cada ejercicio con una póliza que traspasa el resultado a Resultados Acumulados y deja el año bajo candado, reabrible con motivo.

**Architecture:** Un modelo nuevo (`FiscalYearLock`) y su migración; el motor (`post_journal_entry`) valida también el candado anual y acepta `bypass_period_lock` sólo para la póliza de cierre y su reverso. Dos reglas nuevas en `rules.py` (`opening_entry`, `year_close_entry`); el módulo de periodos es dueño del candado anual (`close_year`, `reopen_year`, `list_years`). Los reportes de resultados y el dashboard excluyen `source_type="year_close"`; el balance lo incluye. En el frontend, una tarjeta de saldos iniciales con su formulario y una tabla de ejercicios en el panel de cierre.

**Tech Stack:** FastAPI 0.127, SQLAlchemy 2, Pydantic v2, Alembic, pytest (SQLite en memoria) · React 18, TypeScript, TanStack Query v5, Tailwind.

**Spec:** `docs/superpowers/specs/2026-10-12-apertura-cierre-anual-design.md`

## Global Constraints

- "Todo asiento pasa por `app/services/accounting/engine.py::post_journal_entry()` que exige `SUM(debit) == SUM(credit)`. Prohibido crear `JournalEntry`/`JournalEntryLine` por otra vía." (AGENTS.md §1; en pruebas se permite crear filas a mano sólo para simular datos heredados.)
- "Nunca usar `float` para dinero. `Decimal` en Python, `Numeric(14,2)` en BD, strings en JSON de entrada." (AGENTS.md §3)
- "Todo query de negocio filtra por `organization_id` obtenido de `get_current_org_id` (membresía validada), jamás del payload." (AGENTS.md §4)
- "Las reglas contables viven en `app/services/accounting/rules.py`. Una función por evento de negocio. Nada de armar asientos en routers." (AGENTS.md §9)
- "Nunca asentar una póliza con fecha futura." (AGENTS.md §12)
- "Un mes cerrado no acepta pólizas. El candado se valida dentro de `post_journal_entry()`, nunca en los routers" (AGENTS.md §16); el candado anual va en el mismo lugar.
- "Deshacer es revertir, nunca borrar ni editar." (AGENTS.md §17)
- "Migraciones `AAAAMMDD_NN_slug.py` con `revision="AAAAMMDD_NN"`; un solo head; nunca `create_all()` en producción." y "Registrar cada módulo de modelos nuevo en `app/models/__init__.py`" (CLAUDE.md / AGENTS.md)
- "API `/api/<dominio>` plural sin slash final; paginación `{items,total,limit,offset}`; errores `{"detail":"mensaje en español"}`; nunca ORM crudo." (CLAUDE.md)
- "Montos: `Decimal`/`Numeric(14,2)`; schemas con `Field(gt=0, allow_inf_nan=False)`; el front manda strings." (CLAUDE.md) — la apertura usa `Field(ge=0, max_digits=14, decimal_places=2, allow_inf_nan=False)` porque un saldo en cero se ignora.
- "Contabilidad visible solo para los tres primeros (`require_role`)." (AGENTS.md) — `ACCOUNTING_ROLES` en `/api/accounting` (router) y en cada endpoint de `/api/periods/years`.
- "Las cuentas 1100, 1200, 2100, 2200, 1400, 1490 y 2300 mantienen saldos espejo (...): nunca aceptan pólizas manuales; `rules.MODULE_CONTROLLED_CODES` es la lista." (AGENTS.md) — tampoco entran en la apertura.
- "Commits: Conventional Commits en español." (CLAUDE.md)
- "UI: tokens semánticos Tailwind (`bg-surface`, `text-muted`…), cero colores crudos; cifras con clase `.figures` (Archivo tabular); copy en español, empty states con CTA." (CLAUDE.md)
- `ruff check .` con `line-length = 120` (ruff.toml).
- Los mensajes de error son los del spec, letra por letra.
- Los endpoints que regresan `dict` (no `response_model`) serializan `Decimal` como número: en `/api/periods/years` los montos se convierten a `str` explícitamente.

## Review Focus

1. Cerrar un año cuyo diciembre ya está cerrado por mes: la póliza de cierre debe entrar (bypass) y la reapertura también, y diciembre debe seguir cerrado por mes después (prueba `test_a_december_closed_by_month_does_not_block_the_year`, Task 4).
2. Reabrir, registrar una venta más en ese año y volver a cerrar: un solo renglón de candado reutilizado, el rastro de la reapertura en `notes`, y el segundo cierre debe saldar el año completo (cierre + reverso se anulan) dejando 3200 con la utilidad total (prueba `test_reclosing_reuses_the_lock_and_closes_the_full_year`, Task 4).
3. Apertura con todas las líneas en cero: 400 "Captura el saldo de al menos una cuenta." y nada asentado (prueba `test_an_opening_with_every_amount_in_zero_is_rejected`, Task 2).
4. Un VIEWER que llama `GET /api/periods/years`, `POST /years/{año}/close` o `/reopen` recibe 403; un año fuera de 2000–2100 recibe 422 (prueba `test_viewers_cannot_touch_years_and_years_are_bounded`, Task 4).
5. Pólizas con `source_type` NULL (asientos heredados): el filtro `source_type != 'year_close'` en SQL las descartaría (`NULL != 'x'` no es verdadero); deben seguir contando en el estado de resultados y el dashboard (prueba `test_entries_without_source_type_still_count_in_profit_and_loss`, Task 3).

---

## Mapa de archivos

| Archivo | Responsabilidad | Task |
| --- | --- | --- |
| `app/models/fiscal_year.py` (nuevo) | `FiscalYearLock` | 1 |
| `app/models/__init__.py` | registrar el modelo | 1 |
| `alembic/versions/20261012_01_fiscal_year_locks.py` (nuevo) | tabla `fiscal_year_locks` | 1 |
| `app/services/accounting/engine.py` | `YEAR_CLOSE_SOURCE`, candado anual, `bypass_period_lock`, `not_year_close()`, `include_closing` | 1, 3 |
| `app/services/accounting/rules.py` | `opening_entry`, `HAND_REVERSIBLE_SOURCES`, `reversal_of(bypass_period_lock)`, `year_close_entry` | 2, 3, 4 |
| `app/domains/accounting/router.py` | `GET/POST /opening-balance` | 2 |
| `app/domains/reports/service.py` | `include_closing` en `_lines_by_account` y en `balance_sheet` | 3 |
| `app/domains/periods/service.py` | `is_year_closed`, `close_year`, `reopen_year`, `list_years` | 4 |
| `app/domains/periods/router.py` | `GET /years`, `POST /years/{year}/close`, `POST /years/{year}/reopen` | 4 |
| `app/domains/accounting/service.py` | comentario de `sat_balance` (sin cambio de código) | 4 |
| `tests/test_cierre_anual.py` (nuevo) | motor, reportes, cierre y reapertura | 1, 3, 4 |
| `tests/test_apertura.py` (nuevo) | apertura | 2 |
| `tests/test_sat_export.py` | balanza con cierre real | 4 |
| `frontend/src/types/api.ts` | `OpeningBalance`, `FiscalYear` | 5 |
| `frontend/src/features/accounting/OpeningBalanceForm.tsx` (nuevo) | modal de saldos iniciales | 5 |
| `frontend/src/features/accounting/PeriodsPanel.tsx` | tarjeta de saldos iniciales, tabla de ejercicios | 5, 6 |
| `frontend/src/features/accounting/AccountingPage.tsx` | `onShowEntry` → `showEntry` | 5 |
| `frontend/src/features/accounting/JournalDiary.tsx` | etiquetas y "Revertir" en aperturas | 6 |
| `scripts/demo_despacho.py` | venta y renta del año anterior | 7 |
| `AGENTS.md`, `docs/MVP_STATUS.md`, `docs/MEGA_PLAN_MVP.md` | invariantes y estado | 7 |

**Orden.** Backend (worktree A): Task 1 → 2 → 3 → 4. Frontend (worktree B, en paralelo, contra el contrato de API de este plan): Task 5 → 6. Task 7 al final, con ambos integrados.

**Contrato de API que consume el frontend** (lo producen las Tasks 2 y 4):

- `GET /api/accounting/opening-balance` → `{"entry": JournalEntryRead | null, "balancing_codes": ["3200", "3100"]}`
- `POST /api/accounting/opening-balance` body `{"date": "AAAA-MM-DD", "description": null, "balancing_code": "3200" | "3100", "lines": [{"account_id": "…", "amount": "1500.00"}]}` → 201 `JournalEntryRead`
- `GET /api/periods/years` → `{"items": [{"year": 2025, "entries": 3, "revenue": "5000.00", "expenses": "2000.00", "result": "3000.00", "closed": true, "can_close": false, "blocked_by": null, "closing_entry_id": "…", "closing_folio": "Dr-2025-12-0001", "reopened_at": null}], "total", "limit", "offset"}` — descendente por año.
- `POST /api/periods/years/{year}/close` body `{"notes": null}` → `{"year", "closed": true, "closing_entry_id", "closing_folio"}`
- `POST /api/periods/years/{year}/reopen` body `{"reason": "…"}` (3–500) → `{"year", "closed": false}`

---

### Task 1: Candado de ejercicio en el motor

**Files:**
- Create: `app/models/fiscal_year.py`
- Modify: `app/models/__init__.py` (una línea después de `financial_account`)
- Create: `alembic/versions/20261012_01_fiscal_year_locks.py`
- Modify: `app/services/accounting/engine.py` (constante, `_assert_period_open`, firma de `post_journal_entry`)
- Test: `tests/test_cierre_anual.py` (nuevo)

**Interfaces:**
- Consumes: `PeriodLock` (forma de referencia), `post_journal_entry`, `LineSpec`, `ClosedPeriodError` de `engine.py`.
- Produces:
  - `app.models.fiscal_year.FiscalYearLock` con columnas `organization_id, year: int, closed_by: str|None, closing_entry_id: str|None, reopened_at: datetime|None, reopened_by: str|None, reopen_reason: str|None (500), notes: str|None (1000)`; `UniqueConstraint(organization_id, year, name="uq_fiscal_year_lock")`.
  - `engine.YEAR_CLOSE_SOURCE = "year_close"`.
  - `post_journal_entry(db, organization_id, date, description, lines, source_type=None, source_id=None, reference=None, created_by=None, kind="DIARIO", bypass_period_lock: bool = False) -> JournalEntry`.
  - `ClosedPeriodError("El ejercicio {year} está cerrado. Reábrelo si necesitas corregir algo.")` cuando hay candado anual vivo para `date.year`.
  - En `tests/test_cierre_anual.py`: helpers `_setup(client, email="contador@example.com") -> (headers, org_id, account, category)`, `_income(client, headers, account, category, when, amount="5000")`, `_expense(client, headers, account, category, when, amount="2000")`, `_lock_year(db, organization_id, year)`, `_simple_lines(amount="100")`, constantes `TODAY`, `LAST_YEAR`. Las Tasks 3 y 4 las reutilizan.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_cierre_anual.py`:

```python
"""Cierre de ejercicio: el resultado pasa a Resultados Acumulados y el año queda bajo candado."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.fiscal_year import FiscalYearLock
from app.services.accounting.engine import (
    YEAR_CLOSE_SOURCE,
    ClosedPeriodError,
    LineSpec,
    post_journal_entry,
)
from tests.helpers import auth_headers, register

TODAY = date.today()
LAST_YEAR = TODAY.year - 1


def _setup(client, email="contador@example.com"):
    """Empresa con 100,000 en caja (póliza de hoy) y las categorías que usan las pruebas."""
    body = register(client, email=email, initial_cash="100000")
    headers = auth_headers(body)
    account = client.get("/api/accounts", headers=headers).json()[0]

    def category(kind: str, name: str) -> str:
        rows = client.get(f"/api/categories?kind={kind}", headers=headers).json()
        return next(c["id"] for c in rows if c["name"] == name)

    return headers, body["organization"]["id"], account, category


def _income(client, headers, account, category, when, amount="5000"):
    """Venta cobrada sin IVA: 4100 recibe exactamente `amount`."""
    return client.post(
        "/api/income",
        headers=headers,
        json={
            "date": when.isoformat(),
            "description": "Venta",
            "amount": amount,
            "category_id": category("INCOME", "Ventas"),
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )


def _expense(client, headers, account, category, when, amount="2000"):
    """Renta pagada sin IVA: 5300 recibe exactamente `amount`."""
    return client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": when.isoformat(),
            "description": "Renta",
            "amount": amount,
            "category_id": category("EXPENSE", "Renta"),
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )


def _lock_year(db, organization_id, year):
    """Candado anual puesto a mano: esta parte prueba el motor antes de que exista close_year.

    commit (no flush): con la sesión de pruebas en modo SAVEPOINT, el rollback de
    una petición que falla desharía un flush pendiente."""
    lock = FiscalYearLock(organization_id=organization_id, year=year)
    db.add(lock)
    db.commit()
    return lock


def _simple_lines(amount="100"):
    return [LineSpec("5100", debit=Decimal(amount)), LineSpec("3100", credit=Decimal(amount))]


def test_year_close_source_is_a_fixed_constant():
    assert YEAR_CLOSE_SOURCE == "year_close"


def test_a_locked_year_rejects_entries(client, db):
    _headers, org_id, _account, _category = _setup(client)
    _lock_year(db, org_id, LAST_YEAR)

    with pytest.raises(ClosedPeriodError, match=f"El ejercicio {LAST_YEAR} está cerrado"):
        post_journal_entry(db, org_id, date(LAST_YEAR, 6, 15), "Gasto", _simple_lines())


def test_a_reopened_year_accepts_entries_again(client, db):
    from datetime import datetime, timezone

    _headers, org_id, _account, _category = _setup(client)
    lock = _lock_year(db, org_id, LAST_YEAR)
    lock.reopened_at = datetime.now(timezone.utc)
    lock.reopen_reason = "Faltó una factura"
    db.commit()

    entry = post_journal_entry(db, org_id, date(LAST_YEAR, 6, 15), "Gasto", _simple_lines())
    assert entry.folio.startswith(f"Dr-{LAST_YEAR}-06-")


def test_bypass_skips_both_the_year_and_the_month_lock(client, db):
    from app.models.period import PeriodLock

    _headers, org_id, _account, _category = _setup(client)
    _lock_year(db, org_id, LAST_YEAR)
    db.add(PeriodLock(organization_id=org_id, year=LAST_YEAR, month=12))
    db.commit()

    with pytest.raises(ClosedPeriodError):
        post_journal_entry(db, org_id, date(LAST_YEAR, 12, 31), "Cierre", _simple_lines())
    entry = post_journal_entry(
        db, org_id, date(LAST_YEAR, 12, 31), "Cierre", _simple_lines(), bypass_period_lock=True
    )
    assert entry.date == date(LAST_YEAR, 12, 31)


def test_a_locked_year_rejects_operations_through_the_api(client, db):
    headers, org_id, account, category = _setup(client)
    _lock_year(db, org_id, LAST_YEAR)

    response = _income(client, headers, account, category, date(LAST_YEAR, 6, 15))
    assert response.status_code == 400
    assert "ejercicio" in response.json()["detail"]
    # El año en curso no tiene candado.
    assert _income(client, headers, account, category, TODAY).status_code == 201


def test_the_year_lock_belongs_to_one_company(client, db):
    _headers, org_a, _account, _category = _setup(client)
    _lock_year(db, org_a, LAST_YEAR)

    headers_b, _org_b, account_b, category_b = _setup(client, email="otra@example.com")
    assert _income(client, headers_b, account_b, category_b, date(LAST_YEAR, 6, 15)).status_code == 201
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `source .venv/bin/activate && pytest tests/test_cierre_anual.py -q`
Expected: error de colección `ModuleNotFoundError: No module named 'app.models.fiscal_year'`.

- [ ] **Step 3: Modelo**

Crear `app/models/fiscal_year.py`:

```python
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin


class FiscalYearLock(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Un ejercicio cerrado: su resultado ya pasó a Resultados Acumulados.

    Es el candado anual. Como el de mes, no impide corregir: obliga a reabrir
    el año a propósito, con motivo, y la reapertura revierte la póliza de
    cierre para que el libro vuelva a mostrar ingresos y gastos vivos.
    """

    __tablename__ = "fiscal_year_locks"
    __table_args__ = (UniqueConstraint("organization_id", "year", name="uq_fiscal_year_lock"),)

    year = Column(Integer, nullable=False)
    closed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    # None cuando el año no tuvo ingresos ni gastos: se cierra sin póliza.
    closing_entry_id = Column(String(36), ForeignKey("journal_entries.id"), nullable=True)
    reopened_at = Column(DateTime(timezone=True), nullable=True)
    reopened_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    reopen_reason = Column(String(500), nullable=True)
    notes = Column(String(1000), nullable=True)
```

En `app/models/__init__.py`, después de la línea de `financial_account`:

```python
from app.models.fiscal_year import FiscalYearLock  # noqa: F401
```

- [ ] **Step 4: Migración**

Crear `alembic/versions/20261012_01_fiscal_year_locks.py`:

```python
"""candado de ejercicio: cierre anual

Revision ID: 20261012_01
Revises: 20261006_01
Create Date: 2026-10-12

`fiscal_year_locks`: un renglón por empresa y año cerrado, con la póliza de
cierre que traspasó el resultado a Resultados Acumulados. Misma forma que
`period_locks`, más `closing_entry_id`.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261012_01"
down_revision = "20261006_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fiscal_year_locks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("closed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("closing_entry_id", sa.String(36), sa.ForeignKey("journal_entries.id"), nullable=True),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopened_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reopen_reason", sa.String(500), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "year", name="uq_fiscal_year_lock"),
    )


def downgrade() -> None:
    op.drop_table("fiscal_year_locks")
```

- [ ] **Step 5: Motor**

En `app/services/accounting/engine.py`, después de `TWO_PLACES = Decimal("0.01")`:

```python
# Origen de la póliza de cierre de ejercicio. Los estados de resultados y el
# dashboard la excluyen (traspasa resultados, no es un ingreso ni un gasto);
# balance, balanza, diario, CONTPAQi y SAT la incluyen.
YEAR_CLOSE_SOURCE = "year_close"
```

Reemplazar `_assert_period_open` completa por:

```python
def _assert_period_open(db: Session, organization_id: str, date: date_type) -> None:
    from app.models.fiscal_year import FiscalYearLock
    from app.models.period import PeriodLock

    # El ejercicio primero: si el año entero está cerrado, decir "el mes" confunde.
    year_lock = (
        db.query(FiscalYearLock.id)
        .filter(
            FiscalYearLock.organization_id == organization_id,
            FiscalYearLock.year == date.year,
            FiscalYearLock.reopened_at.is_(None),
        )
        .first()
    )
    if year_lock is not None:
        raise ClosedPeriodError(
            f"El ejercicio {date.year} está cerrado. Reábrelo si necesitas corregir algo."
        )

    lock = (
        db.query(PeriodLock)
        .filter(
            PeriodLock.organization_id == organization_id,
            PeriodLock.year == date.year,
            PeriodLock.month == date.month,
            PeriodLock.reopened_at.is_(None),
        )
        .first()
    )
    if lock is not None:
        raise ClosedPeriodError(
            f"{date.strftime('%m/%Y')} está cerrado. Reábrelo si necesitas corregir algo."
        )
```

En `post_journal_entry`, agregar el parámetro al final de la firma y documentarlo:

```python
    kind: str = "DIARIO",
    bypass_period_lock: bool = False,
) -> JournalEntry:
    """Valida y persiste una póliza balanceada. No hace commit (transacción del caller).

    `kind` (INGRESO/EGRESO/DIARIO) lo declara cada regla de negocio y define la
    serie del folio; no se infiere de las líneas.

    `bypass_period_lock` sólo lo usan la póliza de cierre anual y su reverso: el
    módulo de periodos es dueño de los candados y esas pólizas no cambian lo
    declarado del mes (sólo traspasan resultados a capital).
    """
```

y cambiar la llamada al candado:

```python
    # El candado se valida AQUÍ, en el único punto por donde pasa toda póliza:
    # ponerlo en cada router dejaría puertas abiertas por olvido.
    if not bypass_period_lock:
        _assert_period_open(db, organization_id, date)
```

- [ ] **Step 6: Correr las pruebas, un solo head y ruff**

Run: `source .venv/bin/activate && pytest tests/test_cierre_anual.py -q && alembic heads && ruff check app tests`
Expected: 6 passed; `alembic heads` imprime sólo `20261012_01 (head)`; ruff sin errores.

- [ ] **Step 7: Suite completa**

Run: `pytest -q`
Expected: todo verde (348 + 6 = 354).

- [ ] **Step 8: Commit**

```bash
git add app/models/fiscal_year.py app/models/__init__.py alembic/versions/20261012_01_fiscal_year_locks.py app/services/accounting/engine.py tests/test_cierre_anual.py
git commit -m "feat(contabilidad): candado de ejercicio en el motor de pólizas"
```

---

### Task 2: Póliza de apertura y `GET/POST /api/accounting/opening-balance`

**Files:**
- Modify: `app/services/accounting/rules.py` (imports; constantes junto a `MANUAL_SOURCE`; `reverse_manual_entry`; sección nueva al final)
- Modify: `app/domains/accounting/router.py` (imports; schemas y endpoints antes de `@router.get("/trial-balance")`)
- Test: `tests/test_apertura.py` (nuevo)

**Interfaces:**
- Consumes: `post_journal_entry`, `LineSpec`, `AccountingError`, `TWO_PLACES` de `engine.py`; `MODULE_CONTROLLED_CODES`, `MANUAL_SOURCE`, `REVERSAL_PREFIX` de `rules.py`; `_entry_read(db, organization_id, entry)` y `JournalEntryRead` del router.
- Produces:
  - `rules.OPENING_SOURCE = "opening"`, `rules.HAND_REVERSIBLE_SOURCES = ("manual", "opening")`, `rules.OPENING_BALANCING_CODES = ("3200", "3100")`, `rules.BALANCE_SHEET_TYPES`, `rules.MAX_OPENING_LINES = 100`.
  - `@dataclass(frozen=True) rules.OpeningLine(account_id: str, amount: Decimal)`.
  - `rules.opening_source_id(organization_id: str) -> str` (`"opening:{org}"`).
  - `rules.live_opening_entry(db, organization_id) -> JournalEntry | None`.
  - `rules.opening_entry(db, organization_id, date, lines: list[OpeningLine], balancing_code="3200", description=None, created_by=None) -> JournalEntry` (`LookupError` si la cuenta no es de la empresa; `AccountingError` en reglas; no hace commit).
  - `reverse_manual_entry` acepta `source_type in HAND_REVERSIBLE_SOURCES`.
  - Router: `OpeningLineCreate`, `OpeningBalanceCreate`, `OpeningBalanceRead`; `GET /api/accounting/opening-balance`, `POST /api/accounting/opening-balance` (contrato arriba).

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_apertura.py`:

```python
"""Apertura: los saldos con los que la empresa llega a ARCA, cuadrados contra capital."""

from datetime import date, timedelta
from decimal import Decimal

from tests.helpers import auth_headers, register

TODAY = date.today()
OPENING_DATE = date(TODAY.year - 1, 12, 31)


def _setup(client, email="contador@example.com"):
    body = register(client, email=email, initial_cash="50000")
    headers = auth_headers(body)
    accounts = client.get("/api/accounting/accounts", headers=headers).json()
    return headers, {account["code"]: account for account in accounts}


def _open(client, headers, lines, when=OPENING_DATE, balancing_code=None, description=None):
    payload = {"date": when.isoformat(), "description": description, "lines": lines}
    if balancing_code is not None:
        payload["balancing_code"] = balancing_code
    return client.post("/api/accounting/opening-balance", headers=headers, json=payload)


def _line(account, amount):
    return {"account_id": account["id"], "amount": amount}


def _by_code(entry, acc):
    """{código: (cargo, abono)} de las líneas de una póliza."""
    code_of = {account["id"]: code for code, account in acc.items()}
    return {
        code_of[line["account_id"]]: (Decimal(line["debit"]), Decimal(line["credit"])) for line in entry["lines"]
    }


def test_opening_posts_each_account_in_its_nature_and_balances_against_3200(client):
    headers, acc = _setup(client)
    response = _open(
        client,
        headers,
        [_line(acc["1191"], "1600.00"), _line(acc["2410"], "400.00"), _line(acc["3100"], "500.00")],
    )
    assert response.status_code == 201, response.text
    entry = response.json()
    assert entry["folio"].startswith(f"Dr-{OPENING_DATE.year}-12-")
    assert entry["kind"] == "DIARIO"
    assert entry["source_type"] == "opening"
    assert entry["date"] == OPENING_DATE.isoformat()
    assert entry["description"] == f"Saldos iniciales al 31/12/{OPENING_DATE.year}"
    assert _by_code(entry, acc) == {
        "1191": (Decimal("1600.00"), Decimal("0.00")),
        "2410": (Decimal("0.00"), Decimal("400.00")),
        "3100": (Decimal("0.00"), Decimal("500.00")),
        "3200": (Decimal("0.00"), Decimal("700.00")),
    }

    trial = client.get("/api/accounting/trial-balance", headers=headers).json()
    assert Decimal(str(trial["total_debit"])) == Decimal(str(trial["total_credit"]))
    sheet = client.get("/api/reports/balance-sheet", headers=headers).json()
    assert sheet["balanced"] is True
    assert Decimal(str(sheet["total_assets"])) == Decimal("51600")


def test_a_negative_residual_is_charged_to_3200(client):
    headers, acc = _setup(client)
    response = _open(client, headers, [_line(acc["1191"], "300"), _line(acc["2410"], "1000")])
    assert response.status_code == 201, response.text
    assert _by_code(response.json(), acc)["3200"] == (Decimal("700.00"), Decimal("0.00"))


def test_the_residual_can_go_to_capital(client):
    headers, acc = _setup(client)
    response = _open(
        client, headers, [_line(acc["1191"], "1000"), _line(acc["3200"], "250")], balancing_code="3100"
    )
    assert response.status_code == 201, response.text
    lines = _by_code(response.json(), acc)
    assert lines["3100"] == (Decimal("0.00"), Decimal("750.00"))
    assert lines["3200"] == (Decimal("0.00"), Decimal("250.00"))


def test_zero_lines_are_ignored_and_a_balanced_capture_needs_no_balancing_line(client):
    headers, acc = _setup(client)
    response = _open(
        client,
        headers,
        [_line(acc["1191"], "800"), _line(acc["2410"], "800"), _line(acc["1300"], "0")],
    )
    assert response.status_code == 201, response.text
    assert set(_by_code(response.json(), acc)) == {"1191", "2410"}


def test_an_opening_with_every_amount_in_zero_is_rejected(client):
    headers, acc = _setup(client)
    response = _open(client, headers, [_line(acc["1191"], "0"), _line(acc["2410"], "0.00")])
    assert response.status_code == 400
    assert "al menos una cuenta" in response.json()["detail"]
    assert client.get("/api/accounting/opening-balance", headers=headers).json()["entry"] is None


def test_rejections(client):
    headers, acc = _setup(client)
    cases = [
        ([_line(acc["4100"], "100")], None, "sólo lleva cuentas de balance"),
        ([_line(acc["1100"], "100")], None, "abre desde su módulo"),
        ([_line(acc["2300"], "100")], None, "Patrimonio"),
        ([_line(acc["1000"], "100")], None, "cuenta mayor"),
        ([_line(acc["1191"], "100"), _line(acc["3200"], "100")], None, "es la de cuadre"),
        ([_line(acc["1191"], "100"), _line(acc["3100"], "100")], "3100", "es la de cuadre"),
        ([_line(acc["1191"], "100"), _line(acc["1191"], "50")], None, "aparece dos veces"),
    ]
    for lines, balancing_code, message in cases:
        response = _open(client, headers, lines, balancing_code=balancing_code)
        assert response.status_code == 400, (message, response.text)
        assert message in response.json()["detail"]


def test_bad_payloads_are_rejected_by_the_schema(client):
    headers, acc = _setup(client)
    assert _open(client, headers, [_line(acc["1191"], "-1")]).status_code == 422
    assert _open(client, headers, [_line(acc["1191"], "10.005")]).status_code == 422
    assert _open(client, headers, []).status_code == 422
    assert _open(client, headers, [_line(acc["1191"], "10")], balancing_code="3300").status_code == 422


def test_future_date_is_rejected(client):
    headers, acc = _setup(client)
    response = _open(client, headers, [_line(acc["1191"], "100")], when=TODAY + timedelta(days=1))
    assert response.status_code == 400
    assert "futura" in response.json()["detail"]


def test_closed_month_is_rejected(client):
    headers, acc = _setup(client)
    end = TODAY.replace(day=1) - timedelta(days=1)
    assert (
        client.post("/api/periods/close", headers=headers, json={"year": end.year, "month": end.month}).status_code
        == 200
    )
    response = _open(client, headers, [_line(acc["1191"], "100")], when=end)
    assert response.status_code == 400
    assert "cerrado" in response.json()["detail"]


def test_only_one_live_opening(client):
    headers, acc = _setup(client)
    first = _open(client, headers, [_line(acc["1191"], "100")])
    assert first.status_code == 201
    second = _open(client, headers, [_line(acc["1191"], "200")])
    assert second.status_code == 400
    assert second.json()["detail"] == (
        f"Ya existe una póliza de apertura ({first.json()['folio']}). Reviértela desde el diario para capturar otra."
    )


def test_other_company_account_is_not_found(client):
    headers, _acc = _setup(client)
    _other_headers, other_acc = _setup(client, email="otra@example.com")
    assert _open(client, headers, [_line(other_acc["1191"], "100")]).status_code == 404


def test_reversing_the_opening_frees_the_slot(client):
    headers, acc = _setup(client)
    first = _open(client, headers, [_line(acc["1191"], "100")]).json()
    current = client.get("/api/accounting/opening-balance", headers=headers).json()
    assert current["entry"]["id"] == first["id"]
    assert current["balancing_codes"] == ["3200", "3100"]

    reversal = client.post(
        f"/api/accounting/journal-entries/{first['id']}/reverse",
        headers=headers,
        json={"date": TODAY.isoformat(), "description": None},
    )
    assert reversal.status_code == 201, reversal.text
    assert reversal.json()["reversal_of"] == first["id"]
    assert client.get("/api/accounting/opening-balance", headers=headers).json()["entry"] is None

    again = _open(client, headers, [_line(acc["1191"], "150")])
    assert again.status_code == 201, again.text
    assert client.get("/api/accounting/opening-balance", headers=headers).json()["entry"]["id"] == again.json()["id"]
    # El reverso de una apertura no se revierte.
    twice = client.post(
        f"/api/accounting/journal-entries/{reversal.json()['id']}/reverse",
        headers=headers,
        json={"date": TODAY.isoformat()},
    )
    assert twice.status_code == 400


def test_openings_are_isolated_by_company(client):
    headers_a, acc_a = _setup(client)
    headers_b, _acc_b = _setup(client, email="otra@example.com")
    assert _open(client, headers_a, [_line(acc_a["1191"], "100")]).status_code == 201
    assert client.get("/api/accounting/opening-balance", headers=headers_b).json()["entry"] is None
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `source .venv/bin/activate && pytest tests/test_apertura.py -q`
Expected: FAIL; las llamadas a `/api/accounting/opening-balance` regresan 404/405 (la ruta no existe).

- [ ] **Step 3: Regla en `rules.py`**

En el bloque `from app.services.accounting.coa import (...)`, agregar después de `CODE_LOANS_PAYABLE,`:

```python
    CODE_RETAINED_EARNINGS,
```

Reemplazar la línea `from app.services.accounting.engine import AccountingError, LineSpec, post_journal_entry` por:

```python
from app.services.accounting.engine import (
    TWO_PLACES,
    AccountingError,
    LineSpec,
    post_journal_entry,
)
```

Después de `MAX_MANUAL_LINES = 100` agregar:

```python
OPENING_SOURCE = "opening"
# Pólizas que nacen a mano y por eso se revierten a mano desde el diario. Las
# de operaciones se cancelan en su módulo; la de cierre anual, reabriendo el año.
HAND_REVERSIBLE_SOURCES = (MANUAL_SOURCE, OPENING_SOURCE)
```

En `reverse_manual_entry`, cambiar el docstring y la primera validación:

```python
    """Reverso de una póliza manual o de apertura: espejo, una sola vez, nunca sobre un reverso."""
    if entry.source_type not in HAND_REVERSIBLE_SOURCES:
        raise AccountingError("Esta póliza nació de una operación; cancélala desde su módulo.")
```

Al final del archivo:

```python


# --- Apertura (C-2) ---

# La cuenta contra la que cuadra la apertura: 3200 por defecto, 3100 si el
# contador prefiere llevar la diferencia a capital.
OPENING_BALANCING_CODES = (CODE_RETAINED_EARNINGS, CODE_CAPITAL)
BALANCE_SHEET_TYPES = ("ASSET", "LIABILITY", "EQUITY")
MAX_OPENING_LINES = 100


@dataclass(frozen=True)
class OpeningLine:
    """Saldo inicial de una cuenta, en su naturaleza (deudora o acreedora), >= 0."""

    account_id: str
    amount: Decimal


def opening_source_id(organization_id: str) -> str:
    return f"opening:{organization_id}"


def live_opening_entry(db: Session, organization_id: str) -> JournalEntry | None:
    """La apertura vigente: contabilizada, que no es un reverso y que nadie revirtió.

    El reverso conserva `source_type`/`source_id` (lo hace `reversal_of`), así
    que originales y reversos salen de la misma consulta y se separan por
    `reference`.
    """
    entries = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.organization_id == organization_id,
            JournalEntry.source_type == OPENING_SOURCE,
            JournalEntry.source_id == opening_source_id(organization_id),
            JournalEntry.status == "POSTED",
        )
        .order_by(JournalEntry.created_at.desc())
        .all()
    )
    reversed_ids = {
        entry.reference[len(REVERSAL_PREFIX):]
        for entry in entries
        if entry.reference and entry.reference.startswith(REVERSAL_PREFIX)
    }
    return next(
        (
            entry
            for entry in entries
            if not (entry.reference or "").startswith(REVERSAL_PREFIX) and entry.id not in reversed_ids
        ),
        None,
    )


def opening_entry(
    db: Session,
    organization_id: str,
    date: date_type,
    lines: list[OpeningLine],
    balancing_code: str = CODE_RETAINED_EARNINGS,
    description: str | None = None,
    created_by: str | None = None,
) -> JournalEntry:
    """Póliza de apertura: los saldos con los que la empresa llega a ARCA.

    Cada cuenta de balance entra en su naturaleza (activo al cargo; pasivo y
    capital al abono) y la diferencia va a la cuenta de cuadre. Las cuentas con
    saldo espejo abren desde su módulo. Una sola apertura viva por empresa; para
    corregirla se revierte y se captura otra. No hace commit.
    """
    if balancing_code not in OPENING_BALANCING_CODES:
        raise AccountingError("La apertura cuadra contra Resultados Acumulados (3200) o Capital (3100).")
    if date > date_type.today():
        raise AccountingError("No se puede asentar una póliza con fecha futura.")
    if len(lines) > MAX_OPENING_LINES:
        raise AccountingError(f"La apertura lleva hasta {MAX_OPENING_LINES} cuentas.")
    existing = live_opening_entry(db, organization_id)
    if existing is not None:
        raise AccountingError(
            f"Ya existe una póliza de apertura ({existing.folio}). Reviértela desde el diario para capturar otra."
        )

    wanted = {line.account_id for line in lines}
    accounts = {
        account.id: account
        for account in db.query(Account)
        .filter(Account.organization_id == organization_id, Account.id.in_(wanted))
        .all()
    }
    specs: list[LineSpec] = []
    seen: set[str] = set()
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for line in lines:
        account = accounts.get(line.account_id)
        if account is None:
            raise LookupError("Esa cuenta no existe.")
        if account.id in seen:
            raise AccountingError(f"La cuenta {account.code} aparece dos veces.")
        seen.add(account.id)
        if not account.active:
            raise AccountingError(f"La cuenta {account.code} está inactiva.")
        if account.parent_id is None:
            raise AccountingError(
                f"Las pólizas van a cuentas de detalle, no a la cuenta mayor {account.code}."
            )
        if account.type not in BALANCE_SHEET_TYPES:
            raise AccountingError("La apertura sólo lleva cuentas de balance; ingresos y gastos empiezan en cero.")
        if account.code in MODULE_CONTROLLED_CODES:
            raise AccountingError(
                f"La cuenta {account.code} abre desde su módulo: bancos y tarjetas en Movimientos, "
                "cartera en Por cobrar y Por pagar, activos fijos y préstamos en Patrimonio."
            )
        if account.code == balancing_code:
            raise AccountingError(f"La cuenta {account.code} es la de cuadre; su saldo se calcula.")
        amount = Decimal(line.amount).quantize(TWO_PLACES)
        if amount < 0:
            raise AccountingError("Los saldos iniciales no pueden ser negativos.")
        if amount == 0:
            continue  # una cuenta sin saldo no lleva línea
        if account.type == "ASSET":
            specs.append(LineSpec(account.code, debit=amount))
            total_debit += amount
        else:
            specs.append(LineSpec(account.code, credit=amount))
            total_credit += amount

    if not specs:
        raise AccountingError("Captura el saldo de al menos una cuenta.")
    residual = total_debit - total_credit
    if residual > 0:
        specs.append(LineSpec(balancing_code, credit=residual, description="Cuadre de la apertura"))
    elif residual < 0:
        specs.append(LineSpec(balancing_code, debit=-residual, description="Cuadre de la apertura"))

    text = (description or "").strip() or f"Saldos iniciales al {date:%d/%m/%Y}"
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=text[:500],
        lines=specs,
        source_type=OPENING_SOURCE,
        source_id=opening_source_id(organization_id),
        created_by=created_by,
        kind="DIARIO",
    )
```

- [ ] **Step 4: Endpoints en el router de contabilidad**

En `app/domains/accounting/router.py`, agregar debajo de `from decimal import Decimal`:

```python
from typing import Literal
```

Reemplazar el bloque `from app.services.accounting.rules import (...)` por:

```python
from app.services.accounting.rules import (
    MODULE_CONTROLLED_CODES,
    OPENING_BALANCING_CODES,
    REVERSAL_PREFIX,
    ManualLine,
    OpeningLine,
    live_opening_entry,
    manual_entry,
    opening_entry,
    reverse_manual_entry,
)
```

Inmediatamente antes de `@router.get("/trial-balance")`:

```python
class OpeningLineCreate(BaseModel):
    account_id: str = Field(min_length=1)
    # Saldo en la naturaleza de la cuenta; cero se ignora. Centavos exactos.
    amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2, allow_inf_nan=False)


class OpeningBalanceCreate(BaseModel):
    date: date_type
    description: str | None = Field(default=None, max_length=500)
    balancing_code: Literal["3200", "3100"] = "3200"
    lines: list[OpeningLineCreate] = Field(min_length=1, max_length=100)


class OpeningBalanceRead(BaseModel):
    """La apertura viva (sin reverso), o null, y las cuentas contra las que puede cuadrar."""

    entry: JournalEntryRead | None
    balancing_codes: list[str]


@router.get("/opening-balance", response_model=OpeningBalanceRead)
def get_opening_balance(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    entry = live_opening_entry(db, org_id)
    return OpeningBalanceRead(
        entry=_entry_read(db, org_id, entry) if entry is not None else None,
        balancing_codes=list(OPENING_BALANCING_CODES),
    )


@router.post("/opening-balance", response_model=JournalEntryRead, status_code=201)
def create_opening_balance(
    payload: OpeningBalanceCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
):
    """Saldos iniciales por cuenta. Las reglas viven en rules.opening_entry."""
    # FOR UPDATE sobre la empresa: dos aperturas simultáneas se serializan y la
    # segunda ya ve la primera ("Ya existe una póliza de apertura").
    db.query(Organization.id).filter(Organization.id == org_id).with_for_update().one()
    try:
        entry = opening_entry(
            db,
            org_id,
            date=payload.date,
            lines=[OpeningLine(line.account_id, line.amount) for line in payload.lines],
            balancing_code=payload.balancing_code,
            description=payload.description,
            created_by=user.id,
        )
    except LookupError as error:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error
    db.commit()
    db.refresh(entry)
    return _entry_read(db, org_id, entry)
```

(`Organization`, `User`, `get_current_user`, `HTTPException`, `Field` y `BaseModel` ya están importados en este archivo.)

- [ ] **Step 5: Correr las pruebas y ruff**

Run: `source .venv/bin/activate && pytest tests/test_apertura.py tests/test_polizas_manuales.py -q && ruff check app tests`
Expected: 13 passed en `test_apertura.py` y las de pólizas manuales siguen verdes; ruff sin errores.

- [ ] **Step 6: Suite completa**

Run: `pytest -q`
Expected: todo verde (354 + 13 = 367).

- [ ] **Step 7: Commit**

```bash
git add app/services/accounting/rules.py app/domains/accounting/router.py tests/test_apertura.py
git commit -m "feat(contabilidad): póliza de apertura con saldos iniciales"
```

---

### Task 3: Reportes: el cierre no es un gasto

**Files:**
- Modify: `app/services/accounting/engine.py` (import `or_`, `not_year_close()`, `include_closing` en `account_type_balance`)
- Modify: `app/domains/reports/service.py` (`_lines_by_account`, `balance_sheet`)
- Modify: `app/services/accounting/rules.py` (`reversal_of` con `bypass_period_lock`)
- Test: `tests/test_cierre_anual.py` (agregar al final)

**Interfaces:**
- Consumes: `YEAR_CLOSE_SOURCE`, `post_journal_entry(..., bypass_period_lock)` (Task 1); helpers `_setup`, `_income`, `_simple_lines`, `TODAY`, `LAST_YEAR` de `tests/test_cierre_anual.py` (Task 1).
- Produces:
  - `engine.not_year_close()` → expresión SQLAlchemy `or_(JournalEntry.source_type.is_(None), JournalEntry.source_type != YEAR_CLOSE_SOURCE)`.
  - `engine.account_type_balance(db, organization_id, account_type, start=None, end=None, include_closing: bool = False) -> Decimal`.
  - `reports.service._lines_by_account(db, organization_id, account_types, start=None, end=None, include_closing: bool = False) -> list[dict]`.
  - `balance_sheet` con `include_closing=True` en sus cinco consultas.
  - `rules.reversal_of(db, organization_id, entry, description, date, created_by=None, bypass_period_lock: bool = False) -> JournalEntry`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar al final de `tests/test_cierre_anual.py`:

```python


# --- Reportes: el cierre no es un gasto (Task 3) ---


def _fake_close(db, organization_id, when, amount="5000"):
    """Póliza con origen de cierre anual (4100 → 3200), sin pasar por close_year."""
    entry = post_journal_entry(
        db,
        organization_id,
        date=when,
        description="Cierre simulado",
        lines=[LineSpec("4100", debit=Decimal(amount)), LineSpec("3200", credit=Decimal(amount))],
        source_type=YEAR_CLOSE_SOURCE,
        source_id=f"year_close:{when.year}",
        kind="DIARIO",
    )
    db.commit()
    return entry


def test_profit_and_loss_and_dashboard_ignore_the_closing_entry(client, db):
    headers, org_id, account, category = _setup(client)
    assert _income(client, headers, account, category, TODAY).status_code == 201
    _fake_close(db, org_id, TODAY)

    month = {"start": TODAY.replace(day=1).isoformat(), "end": TODAY.isoformat()}
    report = client.get("/api/reports/profit-loss", headers=headers, params=month).json()
    assert Decimal(str(report["total_revenue"])) == Decimal("5000")
    summary = client.get("/api/dashboard/summary", headers=headers).json()
    assert Decimal(str(summary["monthly_revenue"])) == Decimal("5000")


def test_balance_sheet_and_trial_balance_include_the_closing_entry(client, db):
    headers, org_id, account, category = _setup(client)
    assert _income(client, headers, account, category, TODAY).status_code == 201
    _fake_close(db, org_id, TODAY)

    sheet = client.get("/api/reports/balance-sheet", headers=headers).json()
    assert sheet["balanced"] is True
    equity = {row["code"]: Decimal(str(row["amount"])) for row in sheet["equity"]}
    assert "3999" not in equity
    assert equity["3200"] == Decimal("5000")
    trial = {row["code"]: row for row in client.get("/api/accounting/trial-balance", headers=headers).json()["rows"]}
    assert Decimal(str(trial["4100"]["debit"])) == Decimal("5000")
    assert Decimal(str(trial["4100"]["balance"])) == Decimal("0")


def test_entries_without_source_type_still_count_in_profit_and_loss(client, db):
    """`source_type` NULL (asientos antiguos o cargados a mano) no debe caer con el filtro del cierre."""
    from app.models.accounting import Account, JournalEntry, JournalEntryLine

    headers, org_id, _account, _category = _setup(client)
    accounts = {a.code: a for a in db.query(Account).filter(Account.organization_id == org_id).all()}
    entry = JournalEntry(
        organization_id=org_id, folio="Dr-9999-99-0001", kind="DIARIO", date=TODAY,
        description="Asiento heredado", status="POSTED", source_type=None,
    )
    db.add(entry)
    db.flush()
    db.add(JournalEntryLine(journal_entry_id=entry.id, account_id=accounts["1300"].id, debit=Decimal("700"), credit=0))
    db.add(JournalEntryLine(journal_entry_id=entry.id, account_id=accounts["4200"].id, debit=0, credit=Decimal("700")))
    db.commit()

    month = {"start": TODAY.replace(day=1).isoformat(), "end": TODAY.isoformat()}
    report = client.get("/api/reports/profit-loss", headers=headers, params=month).json()
    assert Decimal(str(report["total_revenue"])) == Decimal("700")
    summary = client.get("/api/dashboard/summary", headers=headers).json()
    assert Decimal(str(summary["monthly_revenue"])) == Decimal("700")


def test_a_reversal_can_bypass_the_lock_only_when_asked(client, db):
    from app.models.period import PeriodLock
    from app.services.accounting.rules import reversal_of

    _headers, org_id, _account, _category = _setup(client)
    original = post_journal_entry(db, org_id, date(LAST_YEAR, 12, 31), "Gasto", _simple_lines())
    db.add(PeriodLock(organization_id=org_id, year=LAST_YEAR, month=12))
    db.commit()

    with pytest.raises(ClosedPeriodError):
        reversal_of(db, org_id, original, "Reverso", date(LAST_YEAR, 12, 31))
    reversal = reversal_of(db, org_id, original, "Reverso", date(LAST_YEAR, 12, 31), bypass_period_lock=True)
    assert reversal.reference == f"reversal:{original.id}"
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `source .venv/bin/activate && pytest tests/test_cierre_anual.py -q`
Expected: 2 FAIL — `test_profit_and_loss_and_dashboard_ignore_the_closing_entry` (`total_revenue` es 0, no 5000) y `test_a_reversal_can_bypass_the_lock_only_when_asked` (`TypeError: reversal_of() got an unexpected keyword argument 'bypass_period_lock'`). Las otras dos ya pasan: son guardas de que el cambio no rompa el balance ni los asientos con `source_type` NULL.

- [ ] **Step 3: Motor**

En `app/services/accounting/engine.py`, cambiar `from sqlalchemy import func` por:

```python
from sqlalchemy import func, or_
```

Inmediatamente antes de `def post_journal_entry(`:

```python
def not_year_close():
    """Filtro: la póliza no es de cierre anual. `source_type` puede ser NULL
    (asientos antiguos) y en SQL `NULL != 'x'` no es verdadero: sin el IS NULL
    esas pólizas desaparecerían de los reportes."""
    return or_(JournalEntry.source_type.is_(None), JournalEntry.source_type != YEAR_CLOSE_SOURCE)


```

En `account_type_balance`, agregar el parámetro, el docstring y el filtro:

```python
def account_type_balance(
    db: Session,
    organization_id: str,
    account_type: str,
    start: date_type | None = None,
    end: date_type | None = None,
    include_closing: bool = False,
) -> Decimal:
    """Saldo neto (naturaleza normal) de todas las cuentas de un tipo, desde el ledger.

    Sin `include_closing` se ignoran las pólizas de cierre anual: traspasan el
    resultado a capital, no son ventas ni gastos. El balance general sí las pide.
    """
```

y, justo antes de `if start is not None:` dentro de esa función:

```python
    if not include_closing:
        query = query.filter(not_year_close())
```

- [ ] **Step 4: Reportes**

En `app/domains/reports/service.py`, cambiar el import del motor por:

```python
from app.services.accounting.engine import account_type_balance, not_year_close
```

En `_lines_by_account`, agregar el parámetro y el docstring:

```python
def _lines_by_account(
    db: Session,
    organization_id: str,
    account_types: tuple[str, ...],
    start: date_type | None = None,
    end: date_type | None = None,
    include_closing: bool = False,
) -> list[dict]:
    """Saldo por cuenta de los tipos pedidos. Sin `include_closing` ignora las
    pólizas de cierre anual: el estado de resultados de un año cerrado sigue
    mostrando sus ventas y sus gastos."""
```

y, antes de `if start is not None:` dentro de esa función:

```python
    if not include_closing:
        query = query.filter(not_year_close())
```

En `balance_sheet`, reemplazar las tres primeras líneas por:

```python
    # El balance es el libro: incluye las pólizas de cierre. Tras cerrar un año,
    # 3200 trae su resultado y "3999" sólo muestra lo que aún no se cierra.
    assets = _lines_by_account(db, organization_id, ("ASSET",), end=as_of, include_closing=True)
    liabilities = _lines_by_account(db, organization_id, ("LIABILITY",), end=as_of, include_closing=True)
    equity = _lines_by_account(db, organization_id, ("EQUITY",), end=as_of, include_closing=True)
```

y las dos llamadas a `account_type_balance` por:

```python
    revenue = account_type_balance(db, organization_id, "REVENUE", end=as_of, include_closing=True)
    expenses = account_type_balance(db, organization_id, "EXPENSE", end=as_of, include_closing=True)
```

(`net_worth` y el dashboard no cambian: ASSET/LIABILITY no reciben líneas de cierre, y el dashboard debe ignorarlas.)

- [ ] **Step 5: `reversal_of` con bypass**

En `app/services/accounting/rules.py`, en `reversal_of`, agregar el parámetro y pasarlo al motor:

```python
def reversal_of(
    db: Session,
    organization_id: str,
    entry: JournalEntry,
    description: str,
    date: date_type,
    created_by: str | None = None,
    bypass_period_lock: bool = False,
) -> JournalEntry:
    """Asiento de reversa: las mismas líneas del original con cargo↔abono invertidos.

    Es la única forma correcta de 'deshacer' contabilidad: el original nunca
    se toca (task pack §27). `bypass_period_lock` sólo lo usa la reapertura de
    un ejercicio (ver `post_journal_entry`).
    """
```

y en la llamada final a `post_journal_entry` dentro de `reversal_of`, después de `kind="DIARIO",`:

```python
        bypass_period_lock=bypass_period_lock,
```

- [ ] **Step 6: Correr las pruebas y ruff**

Run: `source .venv/bin/activate && pytest tests/test_cierre_anual.py tests/test_reports.py tests/test_dashboard_flujo.py -q && ruff check app tests`
Expected: todo verde (10 en `test_cierre_anual.py`); ruff sin errores.

- [ ] **Step 7: Suite completa**

Run: `pytest -q`
Expected: todo verde (367 + 4 = 371).

- [ ] **Step 8: Commit**

```bash
git add app/services/accounting/engine.py app/domains/reports/service.py app/services/accounting/rules.py tests/test_cierre_anual.py
git commit -m "feat(reportes): el cierre anual no cuenta como ingreso ni gasto"
```

---

### Task 4: Cierre y reapertura del ejercicio

**Files:**
- Modify: `app/services/accounting/rules.py` (import `func`, `YEAR_CLOSE_SOURCE`; sección nueva al final)
- Modify: `app/domains/periods/service.py` (imports; sección nueva al final)
- Modify: `app/domains/periods/router.py` (imports; endpoints al final)
- Modify: `app/domains/accounting/service.py` (sólo el comentario de `sat_balance`)
- Test: `tests/test_cierre_anual.py` (agregar al final), `tests/test_sat_export.py` (docstring y prueba nueva)

**Interfaces:**
- Consumes: `FiscalYearLock` (Task 1); `post_journal_entry(..., bypass_period_lock=True)`, `YEAR_CLOSE_SOURCE` (Task 1); `account_type_balance` sin `include_closing` (Task 3); `reversal_of(..., bypass_period_lock=True)` (Task 3); helpers `_setup`, `_income`, `_expense`, `TODAY`, `LAST_YEAR`, `FiscalYearLock`, `auth_headers` de `tests/test_cierre_anual.py` (Task 1); `_setup`, `_income`, `_expense`, `_balanza`, `TODAY` de `tests/test_sat_export.py`.
- Produces:
  - `rules.RESULT_TYPES = ("REVENUE", "EXPENSE")`.
  - `rules.year_close_entry(db, organization_id, year: int, created_by: str | None = None) -> JournalEntry | None` (fecha 31-dic, `source_type="year_close"`, `source_id=f"year_close:{year}"`, descripción `"Cierre del ejercicio {year}"`, `bypass_period_lock=True`; `None` si ninguna cuenta tiene neto).
  - `periods.service.is_year_closed(db, organization_id, year) -> bool`.
  - `periods.service.close_year(db, organization_id, year, user_id=None, notes=None) -> FiscalYearLock` (hace commit; `ValueError` con los mensajes del spec).
  - `periods.service.reopen_year(db, organization_id, year, reason, user_id=None) -> FiscalYearLock` (hace commit).
  - `periods.service.list_years(db, organization_id) -> list[dict]` con llaves `year, entries, revenue, expenses, result, closed, can_close, blocked_by, closing_entry_id, closing_folio, reopened_at` (montos `Decimal`).
  - Router: `GET /api/periods/years`, `POST /api/periods/years/{year}/close`, `POST /api/periods/years/{year}/reopen` (contrato arriba).

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar al final de `tests/test_cierre_anual.py`:

```python


# --- Cierre y reapertura del ejercicio (Task 4) ---


def _close(client, headers, year, notes=None):
    return client.post(f"/api/periods/years/{year}/close", headers=headers, json={"notes": notes})


def _reopen(client, headers, year, reason="Faltó una factura de diciembre"):
    return client.post(f"/api/periods/years/{year}/reopen", headers=headers, json={"reason": reason})


def _entry(client, headers, entry_id):
    response = client.get(f"/api/accounting/journal-entries/{entry_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _lines_by_code(client, headers, entry):
    accounts = {a["id"]: a["code"] for a in client.get("/api/accounting/accounts", headers=headers).json()}
    return {
        accounts[line["account_id"]]: (Decimal(line["debit"]), Decimal(line["credit"])) for line in entry["lines"]
    }


def _trial(client, headers, as_of):
    rows = client.get("/api/accounting/trial-balance", headers=headers, params={"as_of": as_of.isoformat()}).json()
    return {row["code"]: Decimal(str(row["balance"])) for row in rows["rows"]}


def _last_year_with_profit(client, email="contador@example.com"):
    """Venta de 5,000 en junio y renta de 2,000 en julio del año pasado: utilidad de 3,000."""
    headers, org_id, account, category = _setup(client, email=email)
    assert _income(client, headers, account, category, date(LAST_YEAR, 6, 15)).status_code == 201
    assert _expense(client, headers, account, category, date(LAST_YEAR, 7, 20)).status_code == 201
    return headers, org_id, account, category


def test_closing_moves_the_result_to_retained_earnings(client):
    headers, _org_id, _account, _category = _last_year_with_profit(client)

    response = _close(client, headers, LAST_YEAR)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["year"] == LAST_YEAR and body["closed"] is True
    assert body["closing_folio"].startswith(f"Dr-{LAST_YEAR}-12-")

    entry = _entry(client, headers, body["closing_entry_id"])
    assert entry["date"] == f"{LAST_YEAR}-12-31"
    assert entry["source_type"] == "year_close"
    assert entry["source_id"] == f"year_close:{LAST_YEAR}"
    assert entry["description"] == f"Cierre del ejercicio {LAST_YEAR}"
    assert _lines_by_code(client, headers, entry) == {
        "4100": (Decimal("5000.00"), Decimal("0.00")),
        "5300": (Decimal("0.00"), Decimal("2000.00")),
        "3200": (Decimal("0.00"), Decimal("3000.00")),
    }

    year = {"start": f"{LAST_YEAR}-01-01", "end": f"{LAST_YEAR}-12-31"}
    report = client.get("/api/reports/profit-loss", headers=headers, params=year).json()
    assert Decimal(str(report["total_revenue"])) == Decimal("5000")
    assert Decimal(str(report["net_profit"])) == Decimal("3000")

    sheet = client.get("/api/reports/balance-sheet", headers=headers, params={"as_of": f"{LAST_YEAR}-12-31"}).json()
    assert sheet["balanced"] is True
    equity = {row["code"]: Decimal(str(row["amount"])) for row in sheet["equity"]}
    assert "3999" not in equity
    assert equity["3200"] == Decimal("3000")

    trial = _trial(client, headers, date(LAST_YEAR, 12, 31))
    assert trial["4100"] == Decimal("0") and trial["5300"] == Decimal("0")
    assert trial["3200"] == Decimal("3000")


def test_a_loss_is_charged_to_retained_earnings(client):
    headers, _org_id, account, category = _setup(client)
    _income(client, headers, account, category, date(LAST_YEAR, 6, 15), amount="1000")
    _expense(client, headers, account, category, date(LAST_YEAR, 7, 20), amount="4000")

    body = _close(client, headers, LAST_YEAR).json()
    lines = _lines_by_code(client, headers, _entry(client, headers, body["closing_entry_id"]))
    assert lines["3200"] == (Decimal("3000.00"), Decimal("0.00"))


def test_a_year_without_results_is_locked_without_an_entry(client):
    headers, _org_id, account, category = _setup(client)

    response = _close(client, headers, LAST_YEAR)
    assert response.status_code == 200, response.text
    assert response.json()["closing_entry_id"] is None
    assert response.json()["closing_folio"] is None
    blocked = _income(client, headers, account, category, date(LAST_YEAR, 6, 15))
    assert blocked.status_code == 400
    assert "ejercicio" in blocked.json()["detail"]


def test_the_current_year_cannot_be_closed_nor_twice(client):
    headers, _org_id, _account, _category = _last_year_with_profit(client)

    current = _close(client, headers, TODAY.year)
    assert current.status_code == 400
    assert current.json()["detail"] == f"El ejercicio {TODAY.year} todavía no termina."

    assert _close(client, headers, LAST_YEAR).status_code == 200
    again = _close(client, headers, LAST_YEAR)
    assert again.status_code == 400
    assert again.json()["detail"] == f"El ejercicio {LAST_YEAR} ya está cerrado."


def test_years_close_in_order_and_reopen_in_reverse(client):
    headers, _org_id, account, category = _last_year_with_profit(client)
    older = LAST_YEAR - 1
    assert _income(client, headers, account, category, date(older, 3, 10), amount="800").status_code == 201

    blocked = _close(client, headers, LAST_YEAR)
    assert blocked.status_code == 400
    assert blocked.json()["detail"] == f"Primero cierra el ejercicio {older}."

    assert _close(client, headers, older).status_code == 200
    assert _close(client, headers, LAST_YEAR).status_code == 200

    early = _reopen(client, headers, older)
    assert early.status_code == 400
    assert early.json()["detail"] == f"Primero reabre el ejercicio {LAST_YEAR}."
    assert _reopen(client, headers, LAST_YEAR).status_code == 200
    assert _reopen(client, headers, older).status_code == 200


def test_reopening_requires_a_reason_and_reverses_the_closing_entry(client):
    headers, _org_id, account, category = _last_year_with_profit(client)
    closing_id = _close(client, headers, LAST_YEAR).json()["closing_entry_id"]

    blocked = _income(client, headers, account, category, date(LAST_YEAR, 8, 1))
    assert blocked.status_code == 400
    assert "ejercicio" in blocked.json()["detail"]

    assert client.post(f"/api/periods/years/{LAST_YEAR}/reopen", headers=headers, json={}).status_code == 422
    not_closed = _reopen(client, headers, LAST_YEAR - 1)
    assert not_closed.status_code == 400
    assert not_closed.json()["detail"] == f"El ejercicio {LAST_YEAR - 1} no está cerrado."

    response = _reopen(client, headers, LAST_YEAR)
    assert response.status_code == 200, response.text
    assert response.json() == {"year": LAST_YEAR, "closed": False}

    diary = client.get(
        "/api/accounting/journal-entries", headers=headers, params={"source_type": "year_close"}
    ).json()["items"]
    reversal = next(item for item in diary if item["reversal_of"] == closing_id)
    assert reversal["date"] == f"{LAST_YEAR}-12-31"
    assert reversal["description"] == f"Reapertura del ejercicio {LAST_YEAR}: Faltó una factura de diciembre"
    assert _trial(client, headers, date(LAST_YEAR, 12, 31))["4100"] == Decimal("5000")

    assert _income(client, headers, account, category, date(LAST_YEAR, 8, 1)).status_code == 201


def test_reclosing_reuses_the_lock_and_closes_the_full_year(client, db):
    headers, org_id, account, category = _last_year_with_profit(client)
    first = _close(client, headers, LAST_YEAR).json()["closing_entry_id"]
    _reopen(client, headers, LAST_YEAR, reason="Faltó la venta de agosto")
    assert _income(client, headers, account, category, date(LAST_YEAR, 8, 1), amount="1000").status_code == 201

    second = _close(client, headers, LAST_YEAR)
    assert second.status_code == 200, second.text
    assert second.json()["closing_entry_id"] != first

    locks = db.query(FiscalYearLock).filter(
        FiscalYearLock.organization_id == org_id, FiscalYearLock.year == LAST_YEAR
    ).all()
    assert len(locks) == 1
    assert locks[0].reopened_at is None
    assert "Faltó la venta de agosto" in locks[0].notes

    # Cierre, reverso y cierre nuevo: resultados en cero y 3200 con la utilidad completa.
    trial = _trial(client, headers, date(LAST_YEAR, 12, 31))
    assert trial["4100"] == Decimal("0") and trial["5300"] == Decimal("0")
    assert trial["3200"] == Decimal("4000")
    lines = _lines_by_code(client, headers, _entry(client, headers, second.json()["closing_entry_id"]))
    assert lines["4100"] == (Decimal("6000.00"), Decimal("0.00"))


def test_a_december_closed_by_month_does_not_block_the_year(client):
    headers, _org_id, _account, _category = _last_year_with_profit(client)
    assert (
        client.post("/api/periods/close", headers=headers, json={"year": LAST_YEAR, "month": 12}).status_code
        == 200
    )

    closed = _close(client, headers, LAST_YEAR)
    assert closed.status_code == 200, closed.text
    assert closed.json()["closing_entry_id"] is not None
    assert _reopen(client, headers, LAST_YEAR).status_code == 200
    # Diciembre sigue cerrado por mes: el candado mensual es independiente.
    periods = client.get("/api/periods", headers=headers, params={"months": 36}).json()["items"]
    december = next(p for p in periods if p["year"] == LAST_YEAR and p["month"] == 12)
    assert december["closed"] is True


def test_the_years_listing(client):
    headers, _org_id, account, category = _last_year_with_profit(client)
    assert _income(client, headers, account, category, TODAY, amount="700").status_code == 201

    items = client.get("/api/periods/years", headers=headers).json()["items"]
    assert [item["year"] for item in items] == [TODAY.year, LAST_YEAR]
    current, last = items
    assert set(last) == {
        "year", "entries", "revenue", "expenses", "result", "closed", "can_close",
        "blocked_by", "closing_entry_id", "closing_folio", "reopened_at",
    }
    assert (last["revenue"], last["expenses"], last["result"]) == ("5000.00", "2000.00", "3000.00")
    assert last["entries"] == 2
    assert last["can_close"] is True and last["closed"] is False and last["blocked_by"] is None
    assert current["can_close"] is False  # todavía no termina

    _close(client, headers, LAST_YEAR)
    last = client.get("/api/periods/years", headers=headers).json()["items"][1]
    assert last["closed"] is True and last["can_close"] is False
    assert last["closing_folio"].startswith(f"Dr-{LAST_YEAR}-12-")
    # El cierre no es venta ni gasto: el año sigue mostrando lo que vendió.
    assert (last["revenue"], last["result"]) == ("5000.00", "3000.00")
    assert last["entries"] == 3

    _reopen(client, headers, LAST_YEAR)
    last = client.get("/api/periods/years", headers=headers).json()["items"][1]
    assert last["closed"] is False and last["closing_folio"] is None and last["reopened_at"] is not None


def test_only_the_next_year_in_order_can_be_closed(client):
    headers, _org_id, account, category = _last_year_with_profit(client)
    older = LAST_YEAR - 1
    _income(client, headers, account, category, date(older, 3, 10), amount="800")

    items = {item["year"]: item for item in client.get("/api/periods/years", headers=headers).json()["items"]}
    assert items[older]["can_close"] is True
    assert items[LAST_YEAR]["can_close"] is False
    assert items[LAST_YEAR]["blocked_by"] == older


def test_december_profit_survives_the_close_for_the_dashboard(client, db):
    from app.services.accounting.engine import account_type_balance

    headers, org_id, account, category = _setup(client)
    _income(client, headers, account, category, date(LAST_YEAR, 12, 10))
    _close(client, headers, LAST_YEAR)

    december = {"start": date(LAST_YEAR, 12, 1), "end": date(LAST_YEAR, 12, 31)}
    assert account_type_balance(db, org_id, "REVENUE", **december) == Decimal("5000")
    assert account_type_balance(db, org_id, "REVENUE", include_closing=True, **december) == Decimal("0")


def test_a_closed_year_belongs_to_one_company(client):
    headers_a, _org_a, _account_a, _category_a = _last_year_with_profit(client)
    assert _close(client, headers_a, LAST_YEAR).status_code == 200

    headers_b, _org_b, account_b, category_b = _setup(client, email="otra@example.com")
    assert _income(client, headers_b, account_b, category_b, date(LAST_YEAR, 6, 15)).status_code == 201
    assert all(not item["closed"] for item in client.get("/api/periods/years", headers=headers_b).json()["items"])


def test_viewers_cannot_touch_years_and_years_are_bounded(client):
    headers, _org_id, _account, _category = _last_year_with_profit(client)
    client.post(
        "/api/organizations/current/members",
        headers=headers,
        json={"email": "mira@example.com", "name": "Mira", "role": "VIEWER", "password": "supersegura123"},
    )
    viewer = auth_headers(
        client.post("/api/auth/login", json={"email": "mira@example.com", "password": "supersegura123"}).json()
    )
    assert client.get("/api/periods/years", headers=viewer).status_code == 403
    assert _close(client, viewer, LAST_YEAR).status_code == 403
    assert _reopen(client, viewer, LAST_YEAR).status_code == 403

    assert _close(client, headers, 1999).status_code == 422
    assert _close(client, headers, 2101).status_code == 422
```

En `tests/test_sat_export.py`, cambiar el docstring de `test_prior_year_results_open_the_year_in_retained_earnings` por:

```python
    """Sin cierre real del año anterior, el XML lo hace virtual. Ingresos y gastos
    de años anteriores no arrastran saldo; su resultado neto abre en 3200."""
```

y agregar al final del archivo:

```python


def test_a_real_year_close_replaces_the_virtual_one(client):
    """Con el ejercicio anterior cerrado de verdad, la balanza deja de simular:
    enero abre 3200 con la póliza real y diciembre la trae dentro."""
    headers, account, category = _setup(client)
    last_year = TODAY.year - 1
    _income(client, headers, account, category, amount="11600", when=date(last_year, 6, 15))
    _expense(client, headers, account, category, amount="2320", when=date(last_year, 7, 20))
    closed = client.post(f"/api/periods/years/{last_year}/close", headers=headers, json={})
    assert closed.status_code == 200, closed.text

    january = _balanza(client, headers, year=TODAY.year, month=1)
    assert january["3200"]["@SaldoIni"] == Decimal("8000.00")  # 10,000 − 2,000, de la póliza real
    assert "4100" not in january and "5300" not in january  # resultados en cero, sin arrastre

    december = _balanza(client, headers, year=last_year, month=12)
    ventas = december["4100"]
    assert (ventas["@SaldoIni"], ventas["@Debe"], ventas["@SaldoFin"]) == (
        Decimal("10000.00"),
        Decimal("10000.00"),
        Decimal("0.00"),
    )
    assert december["5300"]["@Haber"] == Decimal("2000.00")
    assert december["3200"]["@Haber"] == Decimal("8000.00")
    leaves = [row for code, row in december.items() if len(code) == 4 and code[1:] != "000"]
    assert sum(r["@Debe"] for r in leaves) == sum(r["@Haber"] for r in leaves) > 0
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `source .venv/bin/activate && pytest tests/test_cierre_anual.py tests/test_sat_export.py -q`
Expected: las 13 pruebas nuevas de `test_cierre_anual.py` y `test_a_real_year_close_replaces_the_virtual_one` FAIL (`/api/periods/years...` regresa 404/405); las 10 de Tasks 1 y 3 siguen verdes.

- [ ] **Step 3: Regla `year_close_entry`**

En `app/services/accounting/rules.py`, agregar arriba de `from sqlalchemy.orm import Session`:

```python
from sqlalchemy import func
```

En el bloque `from app.services.accounting.engine import (...)`, agregar después de `TWO_PLACES,`:

```python
    YEAR_CLOSE_SOURCE,
```

Al final del archivo:

```python


# --- Cierre de ejercicio (C-2) ---

RESULT_TYPES = ("REVENUE", "EXPENSE")


def year_close_entry(
    db: Session,
    organization_id: str,
    year: int,
    created_by: str | None = None,
) -> JournalEntry | None:
    """Póliza de cierre: deja en cero cada cuenta de resultados y traspasa la
    utilidad (o la pérdida) a Resultados Acumulados (3200), fechada el 31 de diciembre.

    El neto de cada cuenta incluye los cierres y reaperturas previos del mismo
    año, que se anulan entre sí: recerrar un año reabierto produce el cierre
    correcto. Sin cuentas con neto regresa None (el año se cierra sin póliza).
    Entra aunque diciembre esté cerrado por mes (`bypass_period_lock`): el
    módulo de periodos es dueño del candado. No hace commit.
    """
    start, end = date_type(year, 1, 1), date_type(year, 12, 31)
    rows = (
        db.query(
            Account.code,
            func.coalesce(func.sum(JournalEntryLine.debit), 0),
            func.coalesce(func.sum(JournalEntryLine.credit), 0),
        )
        .join(JournalEntryLine, JournalEntryLine.account_id == Account.id)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .filter(
            Account.organization_id == organization_id,
            Account.type.in_(RESULT_TYPES),
            Account.parent_id.isnot(None),
            JournalEntry.organization_id == organization_id,
            JournalEntry.status == "POSTED",
            JournalEntry.date >= start,
            JournalEntry.date <= end,
        )
        .group_by(Account.code)
        .order_by(Account.code)
        .all()
    )
    lines: list[LineSpec] = []
    result = Decimal("0")  # acreedor positivo: utilidad
    for code, debit, credit in rows:
        net = Decimal(debit or 0) - Decimal(credit or 0)
        if net > 0:  # saldo deudor (gasto): se abona
            lines.append(LineSpec(code, credit=net))
            result -= net
        elif net < 0:  # saldo acreedor (ingreso): se carga
            lines.append(LineSpec(code, debit=-net))
            result += -net
    if not lines:
        return None
    if result > 0:
        lines.append(LineSpec(CODE_RETAINED_EARNINGS, credit=result, description="Utilidad del ejercicio"))
    elif result < 0:
        lines.append(LineSpec(CODE_RETAINED_EARNINGS, debit=-result, description="Pérdida del ejercicio"))
    return post_journal_entry(
        db,
        organization_id,
        date=end,
        description=f"Cierre del ejercicio {year}",
        lines=lines,
        source_type=YEAR_CLOSE_SOURCE,
        source_id=f"year_close:{year}",
        created_by=created_by,
        kind="DIARIO",
        bypass_period_lock=True,
    )
```

- [ ] **Step 4: Servicio de periodos**

En `app/domains/periods/service.py`, reemplazar el bloque de imports desde `from sqlalchemy import func` hasta `from app.models.period import PeriodLock` por:

```python
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.models.accounting import Account, JournalEntry, JournalEntryLine
from app.models.fiscal_year import FiscalYearLock
from app.models.period import PeriodLock
from app.services.accounting.engine import account_type_balance
from app.services.accounting.rules import reversal_of, year_close_entry
```

(`datetime`, `timezone`, `date_type` y `Decimal` ya están importados.)

Al final del archivo:

```python


# --- Ejercicios (C-2) ---


def _year_lock(db: Session, organization_id: str, year: int, live: bool = False) -> FiscalYearLock | None:
    query = db.query(FiscalYearLock).filter(
        FiscalYearLock.organization_id == organization_id,
        FiscalYearLock.year == year,
    )
    if live:
        query = query.filter(FiscalYearLock.reopened_at.is_(None))
    return query.first()


def is_year_closed(db: Session, organization_id: str, year: int) -> bool:
    return _year_lock(db, organization_id, year, live=True) is not None


def _years_with_results(db: Session, organization_id: str) -> set[int]:
    """Años con al menos una línea contabilizada en ingresos o gastos."""
    year_of = extract("year", JournalEntry.date)
    rows = (
        db.query(year_of)
        .join(JournalEntryLine, JournalEntryLine.journal_entry_id == JournalEntry.id)
        .join(Account, Account.id == JournalEntryLine.account_id)
        .filter(
            JournalEntry.organization_id == organization_id,
            JournalEntry.status == "POSTED",
            Account.type.in_(("REVENUE", "EXPENSE")),
        )
        .distinct()
        .all()
    )
    return {int(year) for (year,) in rows}


def _closed_years(db: Session, organization_id: str) -> set[int]:
    return {
        year
        for (year,) in db.query(FiscalYearLock.year).filter(
            FiscalYearLock.organization_id == organization_id,
            FiscalYearLock.reopened_at.is_(None),
        )
    }


def _pending_before(results: set[int], closed: set[int], year: int) -> int | None:
    """El año anterior más antiguo con resultados que sigue abierto: hay que cerrarlo primero."""
    pending = [other for other in results if other < year and other not in closed]
    return min(pending) if pending else None


def close_year(
    db: Session,
    organization_id: str,
    year: int,
    user_id: str | None = None,
    notes: str | None = None,
) -> FiscalYearLock:
    """Traspasa el resultado del año a 3200 y pone el candado anual. Hace commit."""
    if date_type(year, 12, 31) >= date_type.today():
        raise ValueError(f"El ejercicio {year} todavía no termina.")
    if is_year_closed(db, organization_id, year):
        raise ValueError(f"El ejercicio {year} ya está cerrado.")
    pending = _pending_before(_years_with_results(db, organization_id), _closed_years(db, organization_id), year)
    if pending is not None:
        raise ValueError(f"Primero cierra el ejercicio {pending}.")

    entry = year_close_entry(db, organization_id, year, created_by=user_id)

    # Un año reabierto conserva su renglón (la llave única es empresa+año): volver
    # a cerrarlo lo reutiliza y la reapertura queda escrita en las notas.
    lock = _year_lock(db, organization_id, year)
    if lock is None:
        lock = FiscalYearLock(organization_id=organization_id, year=year, notes=notes)
        db.add(lock)
    else:
        trace = f"Reabierto el {lock.reopened_at:%Y-%m-%d}: {lock.reopen_reason}"
        lock.notes = "\n".join(part for part in (lock.notes, trace, notes) if part)[-1000:]
        lock.reopened_at = None
        lock.reopened_by = None
        lock.reopen_reason = None
    lock.closed_by = user_id
    lock.closing_entry_id = entry.id if entry is not None else None
    db.commit()
    db.refresh(lock)
    return lock


def reopen_year(
    db: Session,
    organization_id: str,
    year: int,
    reason: str,
    user_id: str | None = None,
) -> FiscalYearLock:
    """Quita el candado anual y revierte la póliza de cierre al 31 de diciembre. Hace commit."""
    lock = _year_lock(db, organization_id, year, live=True)
    if lock is None:
        raise ValueError(f"El ejercicio {year} no está cerrado.")
    later = max((other for other in _closed_years(db, organization_id) if other > year), default=None)
    if later is not None:
        raise ValueError(f"Primero reabre el ejercicio {later}.")

    lock.reopened_at = datetime.now(timezone.utc)
    lock.reopened_by = user_id
    lock.reopen_reason = reason
    if lock.closing_entry_id:
        closing = (
            db.query(JournalEntry)
            .filter(JournalEntry.id == lock.closing_entry_id, JournalEntry.organization_id == organization_id)
            .one()
        )
        reversal_of(
            db,
            organization_id,
            closing,
            description=f"Reapertura del ejercicio {year}: {reason}"[:500],
            date=date_type(year, 12, 31),
            created_by=user_id,
            bypass_period_lock=True,
        )
    db.commit()
    db.refresh(lock)
    return lock


def list_years(db: Session, organization_id: str) -> list[dict]:
    """Del año de la póliza más antigua al año en curso, el más reciente primero."""
    today = date_type.today()
    oldest = (
        db.query(func.min(JournalEntry.date))
        .filter(JournalEntry.organization_id == organization_id, JournalEntry.status == "POSTED")
        .scalar()
    )
    first_year = oldest.year if oldest is not None else today.year
    locks = {
        lock.year: lock
        for lock in db.query(FiscalYearLock).filter(FiscalYearLock.organization_id == organization_id).all()
    }
    closed = {year for year, lock in locks.items() if lock.reopened_at is None}
    results = _years_with_results(db, organization_id)
    folios = dict(
        db.query(JournalEntry.id, JournalEntry.folio)
        .filter(
            JournalEntry.organization_id == organization_id,
            JournalEntry.id.in_([lock.closing_entry_id for lock in locks.values() if lock.closing_entry_id]),
        )
        .all()
    )

    rows: list[dict] = []
    for year in range(today.year, first_year - 1, -1):
        start, end = date_type(year, 1, 1), date_type(year, 12, 31)
        entries = (
            db.query(func.count(JournalEntry.id))
            .filter(
                JournalEntry.organization_id == organization_id,
                JournalEntry.status == "POSTED",
                JournalEntry.date >= start,
                JournalEntry.date <= end,
            )
            .scalar()
        )
        # Sin include_closing: el cierre traspasa resultados, no es venta ni gasto.
        revenue = account_type_balance(db, organization_id, "REVENUE", start=start, end=end)
        expenses = account_type_balance(db, organization_id, "EXPENSE", start=start, end=end)
        lock = locks.get(year)
        is_closed_year = year in closed
        blocked_by = _pending_before(results, closed, year)
        closing_entry_id = lock.closing_entry_id if lock is not None and is_closed_year else None
        rows.append(
            {
                "year": year,
                "entries": entries or 0,
                "revenue": revenue,
                "expenses": expenses,
                "result": revenue - expenses,
                "closed": is_closed_year,
                "can_close": end < today and not is_closed_year and blocked_by is None,
                "blocked_by": blocked_by if not is_closed_year else None,
                "closing_entry_id": closing_entry_id,
                "closing_folio": folios.get(closing_entry_id) if closing_entry_id else None,
                "reopened_at": lock.reopened_at if lock is not None and not is_closed_year else None,
            }
        )
    return rows
```

- [ ] **Step 5: Router de periodos**

En `app/domains/periods/router.py`, cambiar el import de FastAPI y agregar el modelo:

```python
from fastapi import APIRouter, Depends, HTTPException, Path, Query
```

```python
from app.database import get_db
from app.models.accounting import JournalEntry
```

Al final del archivo:

```python


# --- Ejercicios (C-2) ---


class YearClose(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)


class YearReopen(BaseModel):
    # Reabrir un ejercicio cerrado revierte su póliza de cierre: el motivo queda guardado.
    reason: str = Field(min_length=3, max_length=500)


def _year_read(item: dict) -> dict:
    """Montos como texto, igual que el resto de la API de dinero."""
    return {
        **item,
        "revenue": str(item["revenue"]),
        "expenses": str(item["expenses"]),
        "result": str(item["result"]),
    }


@router.get("/years")
def list_years(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _role: None = Depends(require_role(ACCOUNTING_ROLES)),
):
    items = [_year_read(item) for item in service.list_years(db, org_id)]
    return {"items": items, "total": len(items), "limit": len(items), "offset": 0}


@router.post("/years/{year}/close")
def close_year(
    payload: YearClose,
    year: int = Path(ge=2000, le=2100),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _role: None = Depends(require_role(ACCOUNTING_ROLES)),
):
    try:
        lock = service.close_year(db, org_id, year, user_id=user.id, notes=payload.notes)
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error
    folio = None
    if lock.closing_entry_id:
        folio = db.query(JournalEntry.folio).filter(JournalEntry.id == lock.closing_entry_id).scalar()
    return {"year": lock.year, "closed": True, "closing_entry_id": lock.closing_entry_id, "closing_folio": folio}


@router.post("/years/{year}/reopen")
def reopen_year(
    payload: YearReopen,
    year: int = Path(ge=2000, le=2100),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _role: None = Depends(require_role(ACCOUNTING_ROLES)),
):
    try:
        lock = service.reopen_year(db, org_id, year, payload.reason, user_id=user.id)
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"year": lock.year, "closed": False}
```

- [ ] **Step 6: Comentario de `sat_balance`**

En `app/domains/accounting/service.py`, dentro de `sat_balance`, reemplazar el comentario que empieza con `# ARCA no tiene cierre anual, así que el XML lo hace virtual` (cuatro líneas) por:

```python
    # Cierre virtual para los años que nadie ha cerrado: ingresos y gastos sólo
    # arrastran saldo desde el 1 de enero, y el resultado neto de los años
    # anteriores abre en Resultados Acumulados. Un ejercicio cerrado de verdad
    # (periods.close_year) ya trae sus resultados en cero y la utilidad en 3200,
    # así que aquí aporta cero y enero abre con la póliza real.
```

Sin cambio de código.

- [ ] **Step 7: Correr las pruebas y ruff**

Run: `source .venv/bin/activate && pytest tests/test_cierre_anual.py tests/test_sat_export.py tests/test_cierre_periodo.py -q && ruff check .`
Expected: 23 passed en `test_cierre_anual.py`, `test_sat_export.py` y `test_cierre_periodo.py` verdes; ruff sin errores.

- [ ] **Step 8: Suite completa**

Run: `pytest -q`
Expected: todo verde (371 + 14 = 385).

- [ ] **Step 9: Commit**

```bash
git add app/services/accounting/rules.py app/domains/periods/service.py app/domains/periods/router.py app/domains/accounting/service.py tests/test_cierre_anual.py tests/test_sat_export.py
git commit -m "feat(periodos): cierre y reapertura del ejercicio"
```

---

### Task 5: Frontend: tipos, formulario de saldos iniciales y tarjeta

**Files:**
- Modify: `frontend/src/types/api.ts` (antes de `TrialBalanceRow`)
- Create: `frontend/src/features/accounting/OpeningBalanceForm.tsx`
- Modify: `frontend/src/features/accounting/PeriodsPanel.tsx` (imports, `OpeningBalanceCard`, prop `onShowEntry`)
- Modify: `frontend/src/features/accounting/AccountingPage.tsx` (montaje de `PeriodsPanel`)

**Interfaces:**
- Consumes: `GET/POST /accounting/opening-balance` (contrato arriba, Task 2); `LedgerAccount` (`manual_allowed`, `parent_id`, `active`, `type`); `showEntry(id, dateIso)` de `AccountingPage`; `Card` de `components/ui/Table`; `SelectInput`, `TextInput` de `components/ui/Field`; `Modal` con `size="lg"`.
- Produces:
  - `types/api.ts`: `OpeningBalance { entry: JournalEntry | null; balancing_codes: string[] }` y `FiscalYear { year; entries; revenue: string; expenses: string; result: string; closed; can_close; blocked_by: number | null; closing_entry_id: string | null; closing_folio: string | null; reopened_at: string | null }`.
  - `OpeningBalanceForm({ open, onClose, accounts, onSaved })` con `onSaved: (entry: JournalEntry) => void`.
  - `PeriodsPanel({ onShowEntry }: { onShowEntry?: (id: string) => void })`; query `['accounting', 'opening-balance']`.

- [ ] **Step 1: Tipos**

En `frontend/src/types/api.ts`, inmediatamente antes de `export interface TrialBalanceRow {`:

```ts
/** GET /accounting/opening-balance: la apertura viva y contra qué puede cuadrar. */
export interface OpeningBalance {
  /** La póliza de apertura vigente (sin reverso), o null si no hay. */
  entry: JournalEntry | null
  /** Cuentas de cuadre permitidas, en orden: ["3200", "3100"]. */
  balancing_codes: string[]
}

/** Un renglón de GET /periods/years. Montos como texto. */
export interface FiscalYear {
  year: number
  entries: number
  revenue: string
  expenses: string
  result: string
  closed: boolean
  /** Terminó, sigue abierto y es el siguiente en orden. */
  can_close: boolean
  /** Año anterior con resultados que sigue abierto y debe cerrarse primero, o null. */
  blocked_by: number | null
  /** Póliza de cierre vigente (sólo si está cerrado y tuvo resultados), o null. */
  closing_entry_id: string | null
  closing_folio: string | null
  /** Última reapertura, si el año está abierto después de haberse cerrado. */
  reopened_at: string | null
}

```

- [ ] **Step 2: Crear `OpeningBalanceForm.tsx`**

```tsx
/** Saldos iniciales: la empresa llega a ARCA con lo que traía en CONTPAQi.
 *
 *  Una rejilla con las cuentas de balance que admiten captura; cada saldo va en
 *  la naturaleza de su cuenta y la diferencia la absorbe la cuenta de cuadre
 *  (3200 o 3100). Las cuentas con saldo espejo se muestran en gris: abren desde
 *  su módulo. El backend vuelve a validar todo. */

import { Fragment, useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { SelectInput, TextInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { formatMoney, today } from '@/lib/format'
import type { JournalEntry, LedgerAccount } from '@/types/api'

/** Importe en captura: hasta 12 enteros y dos decimales (mismo patrón que JournalEntryForm). */
const AMOUNT_PATTERN = /^\d{0,12}(\.\d{0,2})?$/

const BALANCE_TYPES = ['ASSET', 'LIABILITY', 'EQUITY']

const BALANCING_OPTIONS = [
  { value: '3200', label: '3200 · Resultados Acumulados' },
  { value: '3100', label: '3100 · Capital' },
]

/** Dónde se captura el saldo de cada cuenta con saldo espejo (rules.MODULE_CONTROLLED_CODES). */
const MODULE_OF: Record<string, string> = {
  '1100': 'Movimientos',
  '2200': 'Movimientos',
  '1200': 'Por cobrar y Por pagar',
  '2100': 'Por cobrar y Por pagar',
  '1400': 'Patrimonio',
  '1490': 'Patrimonio',
  '2300': 'Patrimonio',
}

function toNumber(value: string | undefined): number {
  const parsed = Number(value ?? '')
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0
}

const cents = (value: number) => Math.round(value * 100) / 100

const lastYearEnd = () => `${new Date().getFullYear() - 1}-12-31`

const cellInput =
  'w-full rounded border border-border bg-surface px-2 py-1.5 text-sm text-ink placeholder:text-muted/50 hover:border-muted/40'

export function OpeningBalanceForm({
  open,
  onClose,
  accounts,
  onSaved,
}: {
  open: boolean
  onClose: () => void
  accounts: LedgerAccount[]
  onSaved: (entry: JournalEntry) => void
}) {
  const queryClient = useQueryClient()
  const [date, setDate] = useState(lastYearEnd())
  const [balancingCode, setBalancingCode] = useState('3200')
  const [amounts, setAmounts] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

  const balancing = accounts.find((account) => account.code === balancingCode)

  // Cuentas de detalle, activas y de balance, agrupadas bajo su mayor.
  const { groups, controlled } = useMemo(() => {
    const detail = accounts
      .filter((a) => a.parent_id && a.active && BALANCE_TYPES.includes(a.type))
      .sort((a, b) => a.code.localeCompare(b.code))
    const majors = accounts
      .filter((a) => !a.parent_id && BALANCE_TYPES.includes(a.type))
      .sort((a, b) => a.code.localeCompare(b.code))
    return {
      groups: majors
        .map((major) => ({
          major,
          rows: detail.filter((a) => a.parent_id === major.id && a.manual_allowed && a.code !== balancingCode),
        }))
        .filter((group) => group.rows.length > 0),
      controlled: detail.filter((a) => !a.manual_allowed),
    }
  }, [accounts, balancingCode])

  // Lo que se envía: sólo cuentas visibles con saldo. Cambiar la cuenta de cuadre
  // saca su renglón de la rejilla y también su importe.
  const filled = groups
    .flatMap((group) => group.rows)
    .filter((account) => toNumber(amounts[account.id]) > 0)
  const assets = cents(
    filled.filter((a) => a.type === 'ASSET').reduce((sum, a) => sum + toNumber(amounts[a.id]), 0),
  )
  const liabilitiesAndEquity = cents(
    filled.filter((a) => a.type !== 'ASSET').reduce((sum, a) => sum + toNumber(amounts[a.id]), 0),
  )
  // Activo mayor que pasivo y capital: la diferencia se abona a la cuenta de cuadre (sube el capital).
  const residual = cents(assets - liabilitiesAndEquity)
  const canSave = filled.length > 0 && Boolean(date)

  function reset() {
    setDate(lastYearEnd())
    setBalancingCode('3200')
    setAmounts({})
    setError(null)
  }

  const save = useMutation({
    mutationFn: async () =>
      (
        await api.post<JournalEntry>('/accounting/opening-balance', {
          date,
          description: null,
          balancing_code: balancingCode,
          lines: filled.map((account) => ({
            account_id: account.id,
            amount: toNumber(amounts[account.id]).toFixed(2),
          })),
        })
      ).data,
    onSuccess: (entry) => {
      void queryClient.invalidateQueries({ queryKey: ['accounting'] })
      void queryClient.invalidateQueries({ queryKey: ['periods'] })
      reset()
      onSaved(entry)
    },
    onError: (err) => setError(errorMessage(err)),
  })

  function close() {
    setError(null)
    onClose()
  }

  return (
    <Modal title="Saldos iniciales" open={open} onClose={close} size="lg">
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault()
          if (save.isPending) return
          if (canSave) save.mutate()
        }}
      >
        <p className="text-sm text-muted">
          Captura el saldo de cada cuenta al día de corte, en su naturaleza. La diferencia entre activo y pasivo
          más capital va a la cuenta de cuadre.
        </p>
        <div className="grid gap-3 sm:grid-cols-[10rem_1fr]">
          <TextInput
            label="Fecha de corte"
            type="date"
            value={date}
            max={today()}
            onChange={(e) => setDate(e.target.value)}
            required
          />
          <SelectInput
            label="Cuadrar contra"
            value={balancingCode}
            options={BALANCING_OPTIONS}
            onChange={(e) => setBalancingCode(e.target.value)}
          />
        </div>

        <div className="max-h-[50vh] overflow-y-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10 bg-surface">
              <tr className="border-b border-border text-left text-[11px] uppercase tracking-wider text-muted">
                <th className="px-2 py-2 font-semibold">Código</th>
                <th className="px-2 py-2 font-semibold">Cuenta</th>
                <th className="px-2 py-2 font-semibold">Naturaleza</th>
                <th className="w-40 px-2 py-2 text-right font-semibold">Saldo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {groups.map(({ major, rows }) => (
                <Fragment key={major.id}>
                  <tr className="bg-surface-2/60">
                    <td className="figures px-2 py-1.5 text-xs text-muted">{major.code}</td>
                    <td className="px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted" colSpan={3}>
                      {major.name}
                    </td>
                  </tr>
                  {rows.map((account) => (
                    <tr key={account.id}>
                      <td className="figures px-2 py-1.5 text-muted">{account.code}</td>
                      <td className="px-2 py-1.5">{account.name}</td>
                      <td className="px-2 py-1.5 text-muted">{account.type === 'ASSET' ? 'Deudora' : 'Acreedora'}</td>
                      <td className="px-2 py-1.5">
                        <input
                          aria-label={`Saldo de ${account.code} ${account.name}`}
                          className={`${cellInput} figures text-right`}
                          inputMode="decimal"
                          placeholder="0.00"
                          value={amounts[account.id] ?? ''}
                          onChange={(e) => {
                            if (!AMOUNT_PATTERN.test(e.target.value)) return
                            setAmounts((prev) => ({ ...prev, [account.id]: e.target.value }))
                          }}
                        />
                      </td>
                    </tr>
                  ))}
                </Fragment>
              ))}
              {controlled.map((account) => (
                <tr key={account.id} className="text-muted">
                  <td className="figures px-2 py-1.5">{account.code}</td>
                  <td className="px-2 py-1.5">{account.name}</td>
                  <td className="px-2 py-1.5 text-xs" colSpan={2}>
                    Se captura desde {MODULE_OF[account.code] ?? 'su módulo'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <dl className="grid gap-2 rounded-lg bg-surface-2/60 px-4 py-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs text-muted">Activo</dt>
            <dd className="figures font-semibold">{formatMoney(assets)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Pasivo y capital</dt>
            <dd className="figures font-semibold">{formatMoney(liabilitiesAndEquity)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">
              Va a {balancingCode} {balancing?.name ?? ''}
            </dt>
            <dd className={`figures font-semibold ${residual < 0 ? 'text-neg' : ''}`}>
              {residual === 0 ? formatMoney(0) : `${residual > 0 ? '+' : '−'}${formatMoney(Math.abs(residual))}`}
              <span className="ml-1 text-xs font-normal text-muted">
                {residual > 0 ? 'abono' : residual < 0 ? 'cargo' : 'sin diferencia'}
              </span>
            </dd>
          </div>
        </dl>

        <div className="flex items-center justify-end gap-3">
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <Button type="button" variant="secondary" onClick={close}>
            Cancelar
          </Button>
          <Button type="submit" disabled={!canSave || save.isPending}>
            {save.isPending ? 'Guardando…' : 'Guardar saldos iniciales'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
```

- [ ] **Step 3: Tarjeta de saldos iniciales en `PeriodsPanel.tsx`**

Reemplazar los imports desde `import { Table } from '@/components/ui/Table'` hasta `import { formatMoney } from '@/lib/format'` por:

```tsx
import { Card, Table } from '@/components/ui/Table'
import { ContpaqiExport } from '@/features/accounting/ContpaqiExport'
import { OpeningBalanceForm } from '@/features/accounting/OpeningBalanceForm'
import { SatExport } from '@/features/accounting/SatExport'
import { formatDate, formatMoney } from '@/lib/format'
import type { LedgerAccount, OpeningBalance } from '@/types/api'
```

Reemplazar `export function PeriodsPanel() {` por el componente nuevo seguido de la firma con la prop:

```tsx
/** Saldos iniciales: la puerta de entrada de una empresa que llega con historia. */
function OpeningBalanceCard({ onShowEntry }: { onShowEntry?: (id: string) => void }) {
  const [formOpen, setFormOpen] = useState(false)
  const accountsQuery = useQuery({
    queryKey: ['accounting', 'accounts'],
    queryFn: async () => (await api.get<LedgerAccount[]>('/accounting/accounts')).data,
  })
  const openingQuery = useQuery({
    queryKey: ['accounting', 'opening-balance'],
    queryFn: async () => (await api.get<OpeningBalance>('/accounting/opening-balance')).data,
  })
  const entry = openingQuery.data?.entry ?? null

  if (openingQuery.isLoading) return <div className="h-24 animate-pulse rounded-xl bg-surface-2" />

  return (
    <>
      <Card>
        {entry ? (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-display text-base font-semibold">
                Saldos iniciales al {formatDate(entry.date)} · <span className="figures">{entry.folio}</span>
              </h3>
              <p className="mt-1 text-sm text-muted">
                Para corregirlos, revierte la póliza desde el diario y captura otra.
              </p>
            </div>
            {onShowEntry ? (
              <Button variant="secondary" onClick={() => onShowEntry(entry.id)}>
                Ver póliza
              </Button>
            ) : null}
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-display text-base font-semibold">Saldos iniciales</h3>
              <p className="mt-1 text-sm text-muted">Trae los saldos con los que la empresa llega a ARCA.</p>
            </div>
            <Button onClick={() => setFormOpen(true)}>Capturar saldos iniciales</Button>
          </div>
        )}
      </Card>
      <OpeningBalanceForm
        open={formOpen}
        onClose={() => setFormOpen(false)}
        accounts={accountsQuery.data ?? []}
        onSaved={(saved) => {
          setFormOpen(false)
          onShowEntry?.(saved.id)
        }}
      />
    </>
  )
}

export function PeriodsPanel({ onShowEntry }: { onShowEntry?: (id: string) => void }) {
```

En el `return` de `PeriodsPanel`, insertar la tarjeta como primer hijo del contenedor:

```tsx
    <div className="space-y-4">
      <OpeningBalanceCard onShowEntry={onShowEntry} />

      <p className="text-sm text-muted">
```

(El párrafo y la tabla de meses quedan sin cambios.)

- [ ] **Step 4: Conectar `onShowEntry` en `AccountingPage.tsx`**

Reemplazar `{tab === 'periodos' ? <PeriodsPanel /> : null}` por:

```tsx
      {tab === 'periodos' ? <PeriodsPanel onShowEntry={(id) => showEntry(id, null)} /> : null}
```

(`showEntry` con fecha `null` busca en todo el libro y, si la póliza no cae en la primera página, el diario la trae por id.)

- [ ] **Step 5: Typecheck y build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: sin errores.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/features/accounting/OpeningBalanceForm.tsx frontend/src/features/accounting/PeriodsPanel.tsx frontend/src/features/accounting/AccountingPage.tsx
git commit -m "feat(contabilidad): captura de saldos iniciales"
```

---

### Task 6: Frontend: tabla de ejercicios y diario

**Files:**
- Modify: `frontend/src/features/accounting/PeriodsPanel.tsx` (import de tipos, componente `FiscalYears`, montaje)
- Modify: `frontend/src/features/accounting/JournalDiary.tsx` (`SOURCE_LABELS`, `HAND_REVERSIBLE`, `canReverse`)

**Interfaces:**
- Consumes: `FiscalYear`, `Page` de `types/api.ts` (Task 5 / existente); `GET /periods/years`, `POST /periods/years/{year}/close`, `POST /periods/years/{year}/reopen` (contrato arriba, Task 4); `onShowEntry` de `PeriodsPanel` (Task 5).
- Produces: `FiscalYears({ onShowEntry })` local a `PeriodsPanel.tsx`, query `['periods', 'years']`; el diario muestra "Apertura" y "Cierre anual" y ofrece "Revertir" en aperturas.

- [ ] **Step 1: Tabla de ejercicios en `PeriodsPanel.tsx`**

Cambiar el import de tipos por:

```tsx
import type { FiscalYear, LedgerAccount, OpeningBalance, Page } from '@/types/api'
```

Inmediatamente antes de `export function PeriodsPanel(`:

```tsx
/** Ejercicios: cerrar un año traspasa ingresos y gastos a Resultados Acumulados
 *  y lo deja bajo candado; reabrirlo revierte esa póliza y pide motivo. */
function FiscalYears({ onShowEntry }: { onShowEntry?: (id: string) => void }) {
  const queryClient = useQueryClient()
  const [reopening, setReopening] = useState<FiscalYear | null>(null)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const currentYear = new Date().getFullYear()

  const { data, isLoading } = useQuery({
    queryKey: ['periods', 'years'],
    queryFn: async () => (await api.get<Page<FiscalYear>>('/periods/years')).data.items,
  })

  // Cerrar o reabrir asienta una póliza: el diario y la balanza también cambian.
  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['periods'] })
    void queryClient.invalidateQueries({ queryKey: ['accounting'] })
  }

  const close = useMutation({
    mutationFn: async (year: number) => {
      await api.post(`/periods/years/${year}/close`, { notes: null })
    },
    onSuccess: invalidate,
    onError: (err) => window.alert(errorMessage(err)),
  })

  const reopen = useMutation({
    mutationFn: async () => {
      await api.post(`/periods/years/${reopening!.year}/reopen`, { reason })
    },
    onSuccess: () => {
      invalidate()
      setReopening(null)
      setReason('')
      setError(null)
    },
    onError: (err) => setError(errorMessage(err)),
  })

  if (isLoading) return <div className="h-32 animate-pulse rounded-xl bg-surface-2" />

  return (
    <section className="space-y-3">
      <div>
        <h3 className="font-display text-base font-semibold">Ejercicios</h3>
        <p className="text-sm text-muted">
          Cerrar un ejercicio pasa su utilidad a Resultados Acumulados y lo deja bajo candado. Se cierran en orden,
          del más antiguo al más reciente.
        </p>
      </div>
      <Table
        headers={[
          'Año',
          <span key="i" className="block text-right">
            Ingresos
          </span>,
          <span key="g" className="block text-right">
            Gastos
          </span>,
          <span key="r" className="block text-right">
            Resultado
          </span>,
          'Estado',
          '',
        ]}
        secondary={[2, 3]}
      >
        {(data ?? []).map((item) => (
          <tr key={item.year} className="hover:bg-surface-2/50">
            <td className="figures px-4 py-2.5 font-medium">{item.year}</td>
            <td className="figures px-4 py-2.5 text-right text-muted">{formatMoney(item.revenue)}</td>
            <td className="figures px-4 py-2.5 text-right text-muted">{formatMoney(item.expenses)}</td>
            <td className={`figures px-4 py-2.5 text-right font-medium ${Number(item.result) < 0 ? 'text-neg' : ''}`}>
              {formatMoney(item.result)}
            </td>
            <td className="px-4 py-2.5">
              <span
                className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                  item.closed ? 'bg-pos/10 text-pos' : 'bg-surface-2 text-muted'
                }`}
              >
                {item.closed ? 'Cerrado' : 'Abierto'}
              </span>
            </td>
            <td className="whitespace-nowrap px-4 py-2.5 text-right">
              {item.closed ? (
                <>
                  {item.closing_entry_id && item.closing_folio && onShowEntry ? (
                    <Button
                      variant="ghost"
                      className="mr-1 !px-2 !py-1 text-xs"
                      title={item.closing_folio}
                      onClick={() => onShowEntry(item.closing_entry_id!)}
                    >
                      Ver póliza
                    </Button>
                  ) : null}
                  <Button variant="ghost" className="!px-2 !py-1 text-xs" onClick={() => setReopening(item)}>
                    Reabrir
                  </Button>
                </>
              ) : item.can_close ? (
                <Button
                  variant="secondary"
                  className="!px-2.5 !py-1 text-xs"
                  disabled={close.isPending}
                  onClick={() => {
                    if (
                      window.confirm(
                        `¿Cerrar el ejercicio ${item.year}? Ingresos y gastos pasan a Resultados Acumulados y el año queda bajo candado.`,
                      )
                    )
                      close.mutate(item.year)
                  }}
                >
                  Cerrar ejercicio
                </Button>
              ) : item.year >= currentYear ? (
                <span className="text-xs text-muted">Aún en curso</span>
              ) : item.blocked_by ? (
                <span className="text-xs text-muted">Cierra {item.blocked_by} primero</span>
              ) : null}
            </td>
          </tr>
        ))}
      </Table>

      <Modal
        title={`Reabrir el ejercicio ${reopening?.year ?? ''}`}
        open={reopening !== null}
        onClose={() => setReopening(null)}
      >
        <form
          onSubmit={(event) => {
            event.preventDefault()
            reopen.mutate()
          }}
          className="space-y-3"
        >
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <p className="text-sm text-muted">
            Reabrir revierte la póliza de cierre al 31 de diciembre: ingresos y gastos del año vuelven a quedar
            abiertos. Explica por qué; el motivo queda guardado junto con tu nombre.
          </p>
          <TextInput
            label="Motivo"
            placeholder="Faltó registrar una factura de diciembre"
            value={reason}
            minLength={3}
            maxLength={500}
            onChange={(event) => setReason(event.target.value)}
            required
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setReopening(null)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={reopen.isPending}>
              Reabrir ejercicio
            </Button>
          </div>
        </form>
      </Modal>
    </section>
  )
}

```

En el `return` de `PeriodsPanel`, debajo de la tarjeta:

```tsx
      <OpeningBalanceCard onShowEntry={onShowEntry} />

      <FiscalYears onShowEntry={onShowEntry} />
```

- [ ] **Step 2: Diario**

En `frontend/src/features/accounting/JournalDiary.tsx`, agregar al final de `SOURCE_LABELS` (después de `manual: 'Póliza manual',`) y declarar los orígenes reversibles:

```tsx
  manual: 'Póliza manual',
  opening: 'Apertura',
  year_close: 'Cierre anual',
}

/** Orígenes que se revierten a mano desde aquí (rules.HAND_REVERSIBLE_SOURCES). */
const HAND_REVERSIBLE = new Set(['manual', 'opening'])
```

Reemplazar la línea de `canReverse` por:

```tsx
  const canReverse =
    entry.source_type !== null && HAND_REVERSIBLE.has(entry.source_type) && !entry.reversed && !entry.reversal_of
```

(La póliza de cierre no se revierte desde aquí: se reabre el ejercicio.)

- [ ] **Step 3: Typecheck y build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: sin errores.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/accounting/PeriodsPanel.tsx frontend/src/features/accounting/JournalDiary.tsx
git commit -m "feat(periodos): tabla de ejercicios con cierre y reapertura"
```

---

### Task 7: Demo, documentación y verificación final

**Files:**
- Modify: `scripts/demo_despacho.py` (docstring; `operate`)
- Modify: `AGENTS.md` (invariante 16; invariante 20 nueva)
- Modify: `docs/MVP_STATUS.md` (fecha, Done, Next)
- Modify: `docs/MEGA_PLAN_MVP.md` (sección C2)

**Interfaces:**
- Consumes: todo lo anterior integrado (backend de Tasks 1–4, frontend de Tasks 5–6).
- Produces: demo con ejercicio anterior cerrable; invariantes escritos.

- [ ] **Step 1: Demo**

En el docstring de `scripts/demo_despacho.py`, después de la línea `    D  Clínica Dental Sonríe   propuestas de agentes por revisar`:

```text

Todas traen además una venta en junio y una renta en julio del año pasado: el
ejercicio anterior queda listo para cerrarse en Contabilidad → Cierre de periodo.
```

En `operate`, reemplazar el `return expense` final por:

```python
        # El año pasado: una venta en junio y una renta en julio. Así el contador
        # puede cerrar ese ejercicio en la demo y ver 3200 abrir en enero.
        sale_description, sale_category, sale_amount = profile["incomes"][0]
        post("/income", {
            "date": date(today.year - 1, 6, 15).isoformat(),
            "description": f"{sale_description} (junio {today.year - 1})",
            "amount": sale_amount,
            "tax_rate": "0.16",
            "category_id": income[sale_category]["id"],
            "financial_account_id": bank["id"],
            "status": "PAID",
        }, headers)
        rent_description, rent_category, rent_amount, rent_tax = next(
            row for row in profile["expenses"] if row[1] == "Renta"
        )
        post("/expenses", {
            "date": date(today.year - 1, 7, 20).isoformat(),
            "description": f"{rent_description} (julio {today.year - 1})",
            "amount": rent_amount,
            "tax_rate": rent_tax,
            "category_id": expense[rent_category]["id"],
            "financial_account_id": bank["id"],
            "status": "PAID",
        }, headers)
        return expense
```

(El script no es idempotente por diseño: cada corrida crea cuentas nuevas con correo fechado. Los cuatro perfiles tienen un gasto de categoría "Renta".)

- [ ] **Step 2: Probar la demo contra una base local**

Run (desde la raíz, con una base SQLite desechable):

```bash
source .venv/bin/activate
export DATABASE_URL=sqlite:///./demo-c2.db ENV=development SECRET_KEY=demo-c2-secret-key-0123456789abcdef
alembic upgrade head
uvicorn app.main:app --port 8765 &
python scripts/demo_despacho.py --url http://localhost:8765
```

Expected: imprime "Cartera lista" con las cuatro empresas. Entrar con el contador en `http://localhost:8765` (o con `npm run dev` apuntando a ese puerto), Contabilidad → Cierre de periodo: la tabla "Ejercicios" muestra el año pasado con ingresos, gastos y "Cerrar ejercicio"; cerrarlo muestra "Cerrado" y "Ver póliza" lleva al diario con la póliza "Cierre anual". "Capturar saldos iniciales" abre el formulario; capturar 1191 = 1600 y 2410 = 400 deja "Va a 3200 Resultados Acumulados: +$1,200.00 abono"; guardar lleva al diario y la tarjeta cambia a "Saldos iniciales al …". En el detalle de la apertura aparece "Revertir". Al terminar: `kill %1 && rm demo-c2.db`.

- [ ] **Step 3: `AGENTS.md`**

Reemplazar el invariante 16 por:

```markdown
16. **Un mes cerrado no acepta pólizas, ni un ejercicio cerrado.** El candado se
    valida dentro de `post_journal_entry()`, nunca en los routers: es el único
    punto por el que pasa toda la contabilidad. Reabrir exige un motivo y queda
    registrado. La póliza de cierre y su reverso son las únicas que entran a un
    mes cerrado, vía `bypass_period_lock`, porque el módulo de periodos es dueño
    del candado.
```

Después del invariante 19 agregar:

```markdown
20. **Los estados de resultados y el dashboard excluyen las pólizas de cierre**
    (`source_type="year_close"`); balance, balanza, diario, CONTPAQi y SAT las
    incluyen.
```

- [ ] **Step 4: `docs/MVP_STATUS.md`**

Cambiar la línea de fecha por:

```markdown
_Actualizado: 2026-10-13 (C-2 apertura y cierre anual)_
```

Agregar en "Done", después de la entrada de C-1:

```markdown
- **C-2 Apertura y cierre anual** (spec 2026-10-12): póliza de apertura por cuenta cuadrada contra 3200 o 3100 (`GET/POST /api/accounting/opening-balance`, una viva por empresa, se corrige revirtiéndola desde el diario); cierre de ejercicio que traspasa 4xxx/5xxx a 3200 con candado anual `fiscal_year_locks` validado en el motor y reapertura con motivo que revierte la póliza (`GET /api/periods/years`, `POST /years/{año}/close`, `POST /years/{año}/reopen`); el estado de resultados y el dashboard ignoran el cierre, el balance lo incluye y la balanza SAT abre enero con la póliza real. UI: tarjeta de saldos iniciales, tabla de ejercicios en Cierre de periodo y etiquetas "Apertura"/"Cierre anual" en el diario. Demo con venta y renta del año anterior.
```

En "Next", cambiar la línea de la fase 1 por:

```markdown
- Fase 1 · B estados financieros NIF (C1 y C2 ya en producción).
```

- [ ] **Step 5: `docs/MEGA_PLAN_MVP.md`**

En la sección `### C2 · Apertura y cierre anual`, después de la línea `- **Hecho cuando:** ...`:

```markdown
- **Estado:** en producción (spec `docs/superpowers/specs/2026-10-12-apertura-cierre-anual-design.md`, plan `docs/superpowers/plans/2026-10-13-apertura-cierre-anual.md`).
```

- [ ] **Step 6: Verificación completa**

Run: `source .venv/bin/activate && pytest -q && ruff check . && alembic heads && cd frontend && npm run typecheck && npm run build`
Expected: 385 passed; ruff sin errores; un solo head `20261012_01`; frontend sin errores.

- [ ] **Step 7: Commit**

```bash
git add scripts/demo_despacho.py AGENTS.md docs/MVP_STATUS.md docs/MEGA_PLAN_MVP.md
git commit -m "docs(c2): invariantes de cierre anual y demo con el año anterior"
```
