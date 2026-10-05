# Portal de despacho Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que un contador vea todas sus empresas en una pantalla con un semáforo de pendientes, entre a cualquiera con un clic y dé de alta una nueva sin cerrar sesión.

**Architecture:** La cartera de un usuario son las empresas donde tiene membresía; no hay tablas ni migraciones nuevas. Un dominio nuevo `portfolio` calcula una fila por empresa reutilizando los cálculos del dashboard, y una función pura decide el semáforo. El frontend guarda la lista de empresas en `authStore`, cambia la empresa activa reiniciando la caché de TanStack Query y agrega la página `/despacho`.

**Tech Stack:** FastAPI + SQLAlchemy 2 + Pydantic v2 · pytest (SQLite en memoria) · React 18 + TypeScript + TanStack Query v5 + Zustand + Tailwind.

**Spec:** `docs/superpowers/specs/2026-10-05-portal-despacho-design.md`

## Global Constraints

- Lee `AGENTS.md` antes de empezar: partida doble, aislamiento por empresa, `Decimal` para dinero, saldos sólo vía `record_transaction`, reglas contables sólo en `app/services/accounting/rules.py`.
- Sin tablas ni migraciones nuevas.
- Ninguna consulta de la cartera acepta un `organization_id` que venga del cliente: las empresas salen de las membresías del usuario de la sesión.
- API: `/api/<dominio>` plural sin slash final; sobre `{items,total,limit,offset}`; errores `{"detail":"mensaje en español"}`; nunca ORM crudo en la respuesta.
- Montos: `Decimal`; en schemas de entrada `Field(ge=0, allow_inf_nan=False)` o `Field(gt=0, allow_inf_nan=False)`; el front manda y recibe strings.
- UI: tokens semánticos de Tailwind (`bg-surface`, `text-muted`, `text-pos`, `text-warn`, `text-neg`), cero colores crudos; cifras con clase `.figures`; copy en español. El semáforo usa pos/warn/neg, nunca el acento teal.
- Commits: Conventional Commits en español, terminados con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Rama de trabajo: `feat/portal-despacho`. No se hace push: push a `main` despliega a producción y lo decide Emmanuel.
- Comandos: `source .venv/bin/activate`, `pytest`, `ruff check .`, `cd frontend && npm run typecheck && npm run build`.
- El frontend no tiene runner de pruebas: se verifica con `typecheck`, `build` y la revisión en navegador de la Task 7.

## Review Focus

1. **Nombre de empresa sólo con espacios** en `POST /api/organizations`: debe responder 422 y no crear una empresa sin nombre. Prueba en Task 3.
2. **Mes cerrado y luego reabierto:** cuenta como sin cerrar y `last_closed_period` no lo reporta. Prueba en Task 2.
3. **Enero:** el mes anterior es diciembre del año previo. Prueba en Task 1.
4. **Cuenta por pagar vencida con pago parcial o cancelada:** la cartera reporta sólo el saldo pendiente, y una cancelada no pinta rojo. Pruebas en Task 2.
5. **Empresa activa guardada en el navegador que ya no es del usuario** (lo sacaron del equipo): la app activa otra empresa en vez de responder 403 en todas las pantallas. Sin runner de pruebas en el frontend; se verifica a mano en Task 7, paso 6.

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `app/domains/portfolio/__init__.py` (nuevo, vacío) | Paquete del dominio |
| `app/domains/portfolio/status.py` (nuevo) | Regla pura del semáforo |
| `app/domains/portfolio/service.py` (nuevo) | Una fila por empresa del usuario |
| `app/domains/portfolio/schemas.py` (nuevo) | Forma de la respuesta |
| `app/domains/portfolio/router.py` (nuevo) | `GET /api/portfolio` |
| `app/domains/dashboard/service.py` (modificar) | Expone `available_cash` y `outstanding` |
| `app/domains/organizations/router.py` (modificar) | `POST /api/organizations` |
| `app/routers.py` (modificar) | Registra el router de cartera |
| `tests/test_semaforo.py`, `tests/test_cartera.py`, `tests/test_nueva_empresa.py` (nuevos) | Pruebas |
| `frontend/src/types/api.ts` (modificar) | Tipos `Membership`, `MeResponse`, `PortfolioItem` |
| `frontend/src/stores/authStore.ts` (modificar) | Empresas y membresías en sesión |
| `frontend/src/lib/companies.ts` (nuevo) | Cargar empresas, cambiar de empresa, rol activo |
| `frontend/src/lib/hooks.ts` (modificar) | Recibe `useDismiss` |
| `frontend/src/components/layout/CompanySwitcher.tsx` (nuevo) | Selector de empresa |
| `frontend/src/components/layout/AppHeader.tsx`, `AppLayout.tsx` (modificar) | Selector, rol real, navegación |
| `frontend/src/features/auth/LoginPage.tsx` (modificar) | Aterrizaje en `/despacho` |
| `frontend/src/features/portfolio/PortfolioPage.tsx` (nuevo) | Página "Mis empresas" |
| `frontend/src/App.tsx`, `components/ui/CommandPalette.tsx` (modificar) | Ruta y entrada en la paleta |
| `scripts/demo_despacho.py` (nuevo) | Siembra de la demo |
| `docs/MVP_STATUS.md` (modificar) | Estado |

---

### Task 1: Semáforo de la cartera

**Files:**
- Create: `app/domains/portfolio/__init__.py` (vacío)
- Create: `app/domains/portfolio/status.py`
- Test: `tests/test_semaforo.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `previous_month(today: date) -> tuple[int, int]` (año, mes).
  - `portfolio_status(*, today: date, previous_month_active: bool, previous_month_closed: bool, payable_overdue: Decimal, pending_proposals: int) -> tuple[str, list[str]]`: devuelve `("red" | "amber" | "green", razones)`.
  - `STATUS_ORDER: dict[str, int]` con `{"red": 0, "amber": 1, "green": 2}`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_semaforo.py`:

```python
"""Semáforo de la cartera: regla pura, sin base de datos."""

from datetime import date
from decimal import Decimal

from app.domains.portfolio.status import portfolio_status, previous_month


def _status(**overrides):
    params = {
        "today": date(2026, 10, 5),
        "previous_month_active": True,
        "previous_month_closed": True,
        "payable_overdue": Decimal("0"),
        "pending_proposals": 0,
    }
    params.update(overrides)
    return portfolio_status(**params)


def test_everything_in_order_is_green():
    assert _status() == ("green", [])


def test_open_previous_month_is_amber_until_the_17th():
    status, reasons = _status(previous_month_closed=False)
    assert status == "amber"
    assert reasons == ["Septiembre sigue sin cerrar"]


def test_day_17_is_still_amber():
    status, _reasons = _status(today=date(2026, 10, 17), previous_month_closed=False)
    assert status == "amber"


def test_open_previous_month_turns_red_after_the_17th():
    status, _reasons = _status(today=date(2026, 10, 18), previous_month_closed=False)
    assert status == "red"


def test_a_month_without_entries_has_nothing_to_close():
    result = _status(
        today=date(2026, 10, 25), previous_month_active=False, previous_month_closed=False
    )
    assert result == ("green", [])


def test_overdue_payables_are_red():
    status, reasons = _status(payable_overdue=Decimal("12400"))
    assert status == "red"
    assert reasons == ["$12,400.00 por pagar vencidos"]


def test_pending_proposals_are_amber():
    assert _status(pending_proposals=3) == ("amber", ["3 propuestas por revisar"])


def test_one_proposal_reads_in_singular():
    assert _status(pending_proposals=1) == ("amber", ["1 propuesta por revisar"])


def test_reasons_list_every_cause_not_only_the_deciding_one():
    status, reasons = _status(
        previous_month_closed=False, payable_overdue=Decimal("500"), pending_proposals=2
    )
    assert status == "red"
    assert reasons == [
        "Septiembre sigue sin cerrar",
        "$500.00 por pagar vencidos",
        "2 propuestas por revisar",
    ]


def test_january_looks_back_to_december_of_the_previous_year():
    assert previous_month(date(2027, 1, 10)) == (2026, 12)
    _status_value, reasons = _status(today=date(2027, 1, 10), previous_month_closed=False)
    assert reasons == ["Diciembre sigue sin cerrar"]
```

- [ ] **Step 2: Correr y confirmar que fallan**

Run: `pytest tests/test_semaforo.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.domains.portfolio'`.

- [ ] **Step 3: Implementar**

Crear `app/domains/portfolio/__init__.py` vacío.

`app/domains/portfolio/status.py`:

```python
"""Semáforo de la cartera: qué tan urgente es voltear a ver una empresa.

Es una función pura a propósito: recibe los datos y la fecha, y no toca la base.
Así la regla del día 17 se prueba sin esperar al día 17.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

STATUS_RED = "red"
STATUS_AMBER = "amber"
STATUS_GREEN = "green"
# Orden de la cartera: lo urgente arriba.
STATUS_ORDER = {STATUS_RED: 0, STATUS_AMBER: 1, STATUS_GREEN: 2}

# Las declaraciones mensuales se presentan a más tardar el 17: pasado ese día,
# un mes sin cerrar ya no es un pendiente, es un retraso.
CLOSE_DEADLINE_DAY = 17

_MONTHS = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)  # fmt: skip


def previous_month(today: date) -> tuple[int, int]:
    index = today.year * 12 + (today.month - 1) - 1
    year, month = divmod(index, 12)
    return year, month + 1


def portfolio_status(
    *,
    today: date,
    previous_month_active: bool,
    previous_month_closed: bool,
    payable_overdue: Decimal,
    pending_proposals: int,
) -> tuple[str, list[str]]:
    """Color y TODAS las causas que aplican, no sólo la que decidió el color."""
    # Un mes sin pólizas no tiene nada que cerrar.
    close_pending = previous_month_active and not previous_month_closed

    reasons: list[str] = []
    if close_pending:
        _year, month = previous_month(today)
        reasons.append(f"{_MONTHS[month - 1]} sigue sin cerrar")
    if payable_overdue > 0:
        reasons.append(f"${payable_overdue:,.2f} por pagar vencidos")
    if pending_proposals == 1:
        reasons.append("1 propuesta por revisar")
    elif pending_proposals > 1:
        reasons.append(f"{pending_proposals} propuestas por revisar")

    if (close_pending and today.day > CLOSE_DEADLINE_DAY) or payable_overdue > 0:
        return STATUS_RED, reasons
    if close_pending or pending_proposals > 0:
        return STATUS_AMBER, reasons
    return STATUS_GREEN, reasons
```

- [ ] **Step 4: Correr y confirmar que pasan**

Run: `pytest tests/test_semaforo.py -q && ruff check app/domains/portfolio tests/test_semaforo.py`
Expected: `10 passed` y `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add app/domains/portfolio tests/test_semaforo.py
git commit -m "feat(despacho): semáforo de la cartera como regla pura

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Cartera — `GET /api/portfolio`

**Files:**
- Modify: `app/domains/dashboard/service.py` (función `_outstanding`, bloque `cash` de `summary`)
- Create: `app/domains/portfolio/service.py`, `app/domains/portfolio/schemas.py`, `app/domains/portfolio/router.py`
- Modify: `app/routers.py`
- Test: `tests/test_cartera.py`

**Interfaces:**
- Consumes: de Task 1, `portfolio_status`, `previous_month`, `STATUS_ORDER`. Del repo: `app.domains.periods.service.is_closed(db, organization_id, year, month) -> bool`, `app.security.deps.get_current_user`.
- Produces:
  - `app.domains.dashboard.service.available_cash(db: Session, organization_id: str) -> Decimal`
  - `app.domains.dashboard.service.outstanding(db: Session, organization_id: str, model, overdue_only: bool = False) -> Decimal` (antes `_outstanding`)
  - `app.domains.portfolio.service.portfolio(db: Session, user_id: str) -> list[dict]`
  - `GET /api/portfolio` → `{"items": [PortfolioItem], "total": int, "limit": int, "offset": int}`. Campos de cada item: `organization_id`, `name`, `tax_id`, `business_type`, `role`, `cash`, `receivable`, `payable_overdue` (strings decimales), `last_closed_period` (`"AAAA-MM"` o null), `previous_month_closed` (bool), `pending_proposals` (int), `status` (`"red" | "amber" | "green"`), `reasons` (list[str]).

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_cartera.py`:

```python
"""Cartera: el contador ve todas sus empresas, y sólo las suyas."""

from datetime import date, timedelta
from decimal import Decimal

from tests.helpers import auth_headers, register


def _bearer(auth_body: dict) -> dict:
    """Sólo la sesión, sin empresa activa: la cartera no depende de ella."""
    return {"Authorization": f"Bearer {auth_body['access_token']}"}


def _portfolio(client, auth_body: dict) -> dict:
    response = client.get("/api/portfolio", headers=_bearer(auth_body))
    assert response.status_code == 200, response.text
    return response.json()


def _previous_month() -> tuple[int, int]:
    end = date.today().replace(day=1) - timedelta(days=1)
    return end.year, end.month


def _category(client, headers, kind: str, name: str) -> dict:
    return next(
        c
        for c in client.get(f"/api/categories?kind={kind}", headers=headers).json()
        if c["name"] == name
    )


def _income_last_month(client, headers):
    year, month = _previous_month()
    account = client.get("/api/accounts", headers=headers).json()[0]
    response = client.post(
        "/api/income",
        headers=headers,
        json={
            "date": date(year, month, 15).isoformat(),
            "description": "Venta",
            "amount": "5000",
            "category_id": _category(client, headers, "INCOME", "Ventas")["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    assert response.status_code == 201, response.text


def _overdue_payable(client, headers, amount="4000") -> dict:
    vendor = client.post("/api/vendors", headers=headers, json={"name": "Inmobiliaria Centro"}).json()
    response = client.post(
        "/api/payables",
        headers=headers,
        json={
            "vendor_id": vendor["id"],
            "description": "Renta",
            "amount": amount,
            "due_date": (date.today() - timedelta(days=5)).isoformat(),
            "category_id": _category(client, headers, "EXPENSE", "Renta")["id"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _invite(client, owner_headers, email: str):
    response = client.post(
        "/api/organizations/current/members",
        headers=owner_headers,
        json={"email": email, "name": "Contador", "role": "ACCOUNTANT", "password": "supersegura123"},
    )
    assert response.status_code == 201, response.text


def test_requires_a_session(client):
    assert client.get("/api/portfolio").status_code == 401


def test_lists_only_my_companies(client):
    ana = register(client, email="ana@example.com", business="Ferretería Ana")
    beto = register(client, email="beto@example.com", business="Taller Beto")

    mine = _portfolio(client, ana)
    assert mine["total"] == 1
    assert [item["name"] for item in mine["items"]] == ["Ferretería Ana"]
    assert mine["items"][0]["role"] == "OWNER"

    theirs = _portfolio(client, beto)
    assert [item["name"] for item in theirs["items"]] == ["Taller Beto"]


def test_an_invited_accountant_sees_the_company_with_that_role(client):
    contador = register(client, email="contador@example.com", business="Despacho")
    owner = register(client, email="duena@example.com", business="Clínica")
    _invite(client, auth_headers(owner), "contador@example.com")

    # Con dos empresas y sin encabezado de empresa activa, la cartera responde igual.
    body = _portfolio(client, contador)
    assert body["total"] == 2
    roles = {item["name"]: item["role"] for item in body["items"]}
    assert roles == {"Despacho": "OWNER", "Clínica": "ACCOUNTANT"}


def test_figures_match_the_dashboard(client):
    owner = register(client, initial_cash="10000")
    headers = auth_headers(owner)
    customer = client.post("/api/customers", headers=headers, json={"name": "Cliente Uno"}).json()
    receivable = client.post(
        "/api/receivables",
        headers=headers,
        json={
            "customer_id": customer["id"],
            "description": "Factura F-1",
            "amount": "2320",
            "due_date": (date.today() + timedelta(days=30)).isoformat(),
            "category_id": _category(client, headers, "INCOME", "Ventas")["id"],
        },
    )
    assert receivable.status_code == 201, receivable.text

    item = _portfolio(client, owner)["items"][0]
    summary = client.get("/api/dashboard/summary", headers=headers).json()
    assert Decimal(item["cash"]) == Decimal(str(summary["cash"])) == Decimal("10000")
    assert Decimal(item["receivable"]) == Decimal(str(summary["receivables"])) == Decimal("2320")


def test_a_new_company_is_green(client):
    owner = register(client, initial_cash="10000")
    item = _portfolio(client, owner)["items"][0]
    assert item["status"] == "green"
    assert item["reasons"] == []
    assert item["last_closed_period"] is None


def test_overdue_payables_turn_the_company_red(client):
    owner = register(client, initial_cash="10000")
    _overdue_payable(client, auth_headers(owner))

    item = _portfolio(client, owner)["items"][0]
    assert Decimal(item["payable_overdue"]) == Decimal("4000")
    assert item["status"] == "red"
    assert item["reasons"] == ["$4,000.00 por pagar vencidos"]


def test_a_partial_payment_leaves_only_the_balance_overdue(client):
    owner = register(client, initial_cash="10000")
    headers = auth_headers(owner)
    payable = _overdue_payable(client, headers)
    account = client.get("/api/accounts", headers=headers).json()[0]
    paid = client.post(
        f"/api/payables/{payable['id']}/pay",
        headers=headers,
        json={"amount": "1500", "financial_account_id": account["id"]},
    )
    assert paid.status_code == 200, paid.text

    item = _portfolio(client, owner)["items"][0]
    assert Decimal(item["payable_overdue"]) == Decimal("2500")


def test_a_cancelled_payable_is_not_overdue(client):
    owner = register(client, initial_cash="10000")
    headers = auth_headers(owner)
    payable = _overdue_payable(client, headers)
    cancelled = client.post(
        f"/api/payables/{payable['id']}/cancel", headers=headers, json={"reason": "Duplicada"}
    )
    assert cancelled.status_code == 200, cancelled.text

    item = _portfolio(client, owner)["items"][0]
    assert Decimal(item["payable_overdue"]) == Decimal("0")
    assert item["status"] == "green"


def test_an_open_previous_month_flags_the_company(client):
    owner = register(client, initial_cash="10000")
    _income_last_month(client, auth_headers(owner))

    item = _portfolio(client, owner)["items"][0]
    assert item["previous_month_closed"] is False
    assert item["status"] == ("red" if date.today().day > 17 else "amber")
    assert len(item["reasons"]) == 1
    assert item["reasons"][0].endswith("sigue sin cerrar")


def test_closing_the_month_clears_the_flag(client):
    owner = register(client, initial_cash="10000")
    headers = auth_headers(owner)
    _income_last_month(client, headers)
    year, month = _previous_month()
    closed = client.post("/api/periods/close", headers=headers, json={"year": year, "month": month})
    assert closed.status_code == 200, closed.text

    item = _portfolio(client, owner)["items"][0]
    assert item["previous_month_closed"] is True
    assert item["last_closed_period"] == f"{year}-{month:02d}"
    assert item["status"] == "green"


def test_a_reopened_month_counts_as_open_again(client):
    owner = register(client, initial_cash="10000")
    headers = auth_headers(owner)
    _income_last_month(client, headers)
    year, month = _previous_month()
    client.post("/api/periods/close", headers=headers, json={"year": year, "month": month})
    reopened = client.post(
        "/api/periods/reopen",
        headers=headers,
        json={"year": year, "month": month, "reason": "Faltó una factura"},
    )
    assert reopened.status_code == 200, reopened.text

    item = _portfolio(client, owner)["items"][0]
    assert item["previous_month_closed"] is False
    assert item["last_closed_period"] is None
    assert item["status"] != "green"


def test_pending_proposals_show_up(client):
    owner = register(client, initial_cash="10000")
    headers = auth_headers(owner)
    key = client.post(
        "/api/agent-keys", headers=headers, json={"name": "Agente", "scopes": "READ,PROPOSE"}
    ).json()
    proposed = client.post(
        "/api/agent/invoke",
        headers={"Authorization": f"Bearer {key['token']}"},
        json={
            "tool": "propose_expense",
            "arguments": {
                "date": date.today().isoformat(),
                "description": "Cargo por identificar",
                "amount": "999",
                "category_id": _category(client, headers, "EXPENSE", "Otros")["id"],
                "summary": "Cargo no identificado en el banco",
            },
        },
    ).json()
    assert proposed["ok"] is True, proposed

    item = _portfolio(client, owner)["items"][0]
    assert item["pending_proposals"] == 1
    assert item["status"] == "amber"
    assert item["reasons"] == ["1 propuesta por revisar"]


def test_urgent_companies_come_first(client):
    contador = register(client, email="contador@example.com", business="Abarrotes Al Corriente")
    owner = register(client, email="duena@example.com", business="Zapatería Con Vencidos")
    owner_headers = auth_headers(owner)
    _overdue_payable(client, owner_headers)
    _invite(client, owner_headers, "contador@example.com")

    items = _portfolio(client, contador)["items"]
    assert [(item["name"], item["status"]) for item in items] == [
        ("Zapatería Con Vencidos", "red"),
        ("Abarrotes Al Corriente", "green"),
    ]
```

- [ ] **Step 2: Correr y confirmar que fallan**

Run: `pytest tests/test_cartera.py -q`
Expected: FAIL; todas las pruebas reciben 404 en `/api/portfolio`.

- [ ] **Step 3: Exponer los cálculos del dashboard**

En `app/domains/dashboard/service.py`:

a) Renombrar `_outstanding` a `outstanding` (la definición y sus tres usos dentro de `summary`). Confirmar que no queda ningún otro uso:

Run: `grep -rn "_outstanding" app tests scripts --include="*.py" | grep -v "def test_"`
Expected: sin resultados.

b) Agregar, justo debajo de `outstanding`:

```python
def available_cash(db: Session, organization_id: str) -> Decimal:
    """Efectivo disponible: sólo instrumentos de activo.

    Sumar el saldo de una tarjeta restaría deuda al efectivo y diría que tienes
    menos dinero del que tienes.
    """
    cash = (
        db.query(func.coalesce(func.sum(FinancialAccount.current_balance), 0))
        .filter(
            FinancialAccount.organization_id == organization_id,
            FinancialAccount.deleted_at.is_(None),
            FinancialAccount.active.is_(True),
            FinancialAccount.type.in_(ASSET_ACCOUNT_TYPES),
        )
        .scalar()
    )
    return Decimal(cash or 0)
```

c) En `summary`, reemplazar el bloque que hoy calcula `cash` (el comentario "Sólo instrumentos de activo…" y la consulta `cash = (...)`) por:

```python
    cash = available_cash(db, organization_id)
```

y en el diccionario de retorno cambiar `"cash": Decimal(cash or 0),` por `"cash": cash,`.

Run: `pytest tests/test_dashboard_flujo.py tests/test_instrumentos.py tests/test_receivables.py tests/test_payables.py -q`
Expected: todo pasa (el dashboard no cambió de comportamiento).

- [ ] **Step 4: Implementar el dominio de cartera**

`app/domains/portfolio/schemas.py`:

```python
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class PortfolioItem(BaseModel):
    organization_id: str
    name: str
    tax_id: str | None
    business_type: str | None
    role: str
    cash: Decimal
    receivable: Decimal
    payable_overdue: Decimal
    last_closed_period: str | None  # "AAAA-MM"
    previous_month_closed: bool
    pending_proposals: int
    status: str  # red | amber | green
    reasons: list[str]


class PortfolioResponse(BaseModel):
    items: list[PortfolioItem]
    total: int
    limit: int
    offset: int
```

`app/domains/portfolio/service.py`:

```python
"""Cartera: todas las empresas de un usuario y lo que cada una tiene pendiente.

La única puerta de entrada es el usuario de la sesión: las empresas salen de sus
membresías, nunca de un identificador que mande el cliente.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date

from sqlalchemy.orm import Session

from app.domains.dashboard.service import available_cash, outstanding
from app.domains.periods.service import is_closed
from app.domains.portfolio.status import STATUS_ORDER, portfolio_status, previous_month
from app.models.accounting import JournalEntry
from app.models.agent import AgentProposal
from app.models.organization import Organization, OrganizationMember
from app.models.payable import Payable
from app.models.period import PeriodLock
from app.models.receivable import Receivable


def _has_entries(db: Session, organization_id: str, year: int, month: int) -> bool:
    """¿Hubo pólizas ese mes? Se decide por actividad en el libro, no por la
    fecha de alta: una empresa migrada con historia sí tiene mes que cerrar."""
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    return (
        db.query(JournalEntry.id)
        .filter(
            JournalEntry.organization_id == organization_id,
            JournalEntry.date >= start,
            JournalEntry.date <= end,
        )
        .first()
        is not None
    )


def _last_closed_period(db: Session, organization_id: str) -> str | None:
    lock = (
        db.query(PeriodLock)
        .filter(
            PeriodLock.organization_id == organization_id,
            PeriodLock.reopened_at.is_(None),
        )
        .order_by(PeriodLock.year.desc(), PeriodLock.month.desc())
        .first()
    )
    return f"{lock.year}-{lock.month:02d}" if lock else None


def _pending_proposals(db: Session, organization_id: str) -> int:
    return (
        db.query(AgentProposal)
        .filter(
            AgentProposal.organization_id == organization_id,
            AgentProposal.status == "PROPOSED",
        )
        .count()
    )


def portfolio(db: Session, user_id: str) -> list[dict]:
    """Una fila por empresa del usuario, lo urgente arriba."""
    today = date.today()
    year, month = previous_month(today)

    rows = (
        db.query(OrganizationMember, Organization)
        .join(Organization, Organization.id == OrganizationMember.organization_id)
        .filter(OrganizationMember.user_id == user_id)
        .all()
    )

    items: list[dict] = []
    for membership, organization in rows:
        org_id = organization.id
        closed = is_closed(db, org_id, year, month)
        payable_overdue = outstanding(db, org_id, Payable, overdue_only=True)
        pending = _pending_proposals(db, org_id)
        status, reasons = portfolio_status(
            today=today,
            previous_month_active=_has_entries(db, org_id, year, month),
            previous_month_closed=closed,
            payable_overdue=payable_overdue,
            pending_proposals=pending,
        )
        items.append(
            {
                "organization_id": org_id,
                "name": organization.name,
                "tax_id": organization.tax_id,
                "business_type": organization.business_type,
                "role": membership.role,
                "cash": available_cash(db, org_id),
                "receivable": outstanding(db, org_id, Receivable),
                "payable_overdue": payable_overdue,
                "last_closed_period": _last_closed_period(db, org_id),
                "previous_month_closed": closed,
                "pending_proposals": pending,
                "status": status,
                "reasons": reasons,
            }
        )

    items.sort(key=lambda item: (STATUS_ORDER[item["status"]], item["name"].lower()))
    return items
```

`app/domains/portfolio/router.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.portfolio import service
from app.domains.portfolio.schemas import PortfolioResponse
from app.models.user import User
from app.security.deps import get_current_user

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioResponse)
def get_portfolio(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """La cartera no depende de la empresa activa: recorre las del usuario."""
    items = service.portfolio(db, user.id)
    return {"items": items, "total": len(items), "limit": len(items), "offset": 0}
```

En `app/routers.py`, agregar junto a los demás imports:

```python
from app.domains.portfolio.router import router as portfolio_router
```

y al final del archivo:

```python
api_router.include_router(portfolio_router)
```

- [ ] **Step 5: Correr y confirmar que pasan**

Run: `pytest tests/test_cartera.py tests/test_semaforo.py -q && ruff check app tests`
Expected: `23 passed` y `All checks passed!`

- [ ] **Step 6: Suite completa**

Run: `pytest -q`
Expected: todo en verde, sin pruebas nuevas rotas por el renombre.

- [ ] **Step 7: Commit**

```bash
git add app/domains/portfolio app/domains/dashboard/service.py app/routers.py tests/test_cartera.py
git commit -m "feat(despacho): cartera del usuario en GET /api/portfolio

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Dar de alta otra empresa — `POST /api/organizations`

**Files:**
- Modify: `app/domains/organizations/router.py`
- Test: `tests/test_nueva_empresa.py`

**Interfaces:**
- Consumes: `app.services.onboarding.provision_organization(db, user, business_name, business_type=None, initial_cash=None) -> Organization` (no hace commit; deja al usuario como `OWNER`). `GET /api/portfolio` de Task 2 para las pruebas.
- Produces: `POST /api/organizations` con cuerpo `{"business_name": str, "business_type"?: str, "tax_id"?: str, "initial_cash"?: decimal string}` → 201 con `OrganizationRead` (`id`, `name`, `legal_name`, `tax_id`, `currency`, `country`, `timezone`, `business_type`, `default_tax_rate`).

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_nueva_empresa.py`:

```python
"""Alta de otra empresa: el contador suma un cliente sin cerrar sesión."""

from decimal import Decimal

from tests.helpers import auth_headers, register


def _bearer(auth_body: dict) -> dict:
    return {"Authorization": f"Bearer {auth_body['access_token']}"}


def _create(client, auth_body: dict, **payload):
    payload.setdefault("business_name", "Cliente Nuevo")
    return client.post("/api/organizations", headers=_bearer(auth_body), json=payload)


def _headers_for(auth_body: dict, organization_id: str) -> dict:
    return {**_bearer(auth_body), "X-Organization-ID": organization_id}


def test_requires_a_session(client):
    response = client.post("/api/organizations", json={"business_name": "Sin sesión"})
    assert response.status_code == 401


def test_a_signed_in_user_opens_a_second_company(client):
    contador = register(client, email="contador@example.com", business="Despacho")

    response = _create(client, contador, business_name="  Ferretería El Tornillo ", tax_id=" fet180312ab1 ")
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["name"] == "Ferretería El Tornillo"
    assert created["tax_id"] == "FET180312AB1"

    portfolio = client.get("/api/portfolio", headers=_bearer(contador)).json()
    roles = {item["name"]: item["role"] for item in portfolio["items"]}
    assert roles == {"Despacho": "OWNER", "Ferretería El Tornillo": "OWNER"}


def test_the_new_company_is_born_with_its_books(client):
    contador = register(client, email="contador@example.com", business="Despacho")
    created = _create(client, contador, initial_cash="2500").json()
    headers = _headers_for(contador, created["id"])

    assert len(client.get("/api/accounting/accounts", headers=headers).json()) > 0
    assert len(client.get("/api/categories?kind=EXPENSE", headers=headers).json()) > 0

    accounts = client.get("/api/accounts", headers=headers).json()
    assert [(a["name"], a["current_balance"]) for a in accounts] == [("Caja", "2500.00")]

    # El saldo inicial entró por el motor contable: la balanza cuadra.
    balanza = client.get("/api/accounting/trial-balance", headers=headers).json()
    assert Decimal(str(balanza["total_debit"])) == Decimal(str(balanza["total_credit"])) == Decimal("2500")


def test_the_new_company_does_not_touch_the_first_one(client):
    contador = register(client, email="contador@example.com", business="Despacho", initial_cash="10000")
    created = _create(client, contador, initial_cash="2500").json()

    first = client.get("/api/accounts", headers=auth_headers(contador)).json()
    assert [a["current_balance"] for a in first] == ["10000.00"]

    # Otra persona no entra a la empresa nueva aunque conozca su identificador.
    intruso = register(client, email="intruso@example.com", business="Otra")
    response = client.get("/api/accounts", headers=_headers_for(intruso, created["id"]))
    assert response.status_code == 403


def test_a_blank_name_is_rejected(client):
    contador = register(client, email="contador@example.com", business="Despacho")
    assert _create(client, contador, business_name="   ").status_code == 422
    assert client.get("/api/portfolio", headers=_bearer(contador)).json()["total"] == 1


def test_a_negative_opening_balance_is_rejected(client):
    contador = register(client, email="contador@example.com", business="Despacho")
    assert _create(client, contador, initial_cash="-1").status_code == 422
```

- [ ] **Step 2: Correr y confirmar que fallan**

Run: `pytest tests/test_nueva_empresa.py -q`
Expected: FAIL; `POST /api/organizations` responde 405.

- [ ] **Step 3: Implementar**

En `app/domains/organizations/router.py`:

a) Cambiar el import de pydantic a:

```python
from pydantic import BaseModel, EmailStr, Field, field_validator
```

b) Agregar el import:

```python
from app.services.onboarding import provision_organization
```

c) Debajo de la clase `OrganizationUpdate`, agregar:

```python
class OrganizationCreate(BaseModel):
    business_name: str = Field(min_length=1, max_length=255)
    business_type: str | None = Field(default=None, max_length=50)
    tax_id: str | None = Field(default=None, max_length=20)
    initial_cash: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)

    @field_validator("business_name")
    @classmethod
    def _name_is_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Escribe el nombre de la empresa.")
        return value


@router.post("", response_model=OrganizationRead, status_code=201)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Otra empresa para quien ya tiene sesión: el contador da de alta a un cliente.

    Mismo arranque que el registro (catálogo, categorías, "Caja"); quien la crea
    queda como dueño.
    """
    organization = provision_organization(
        db,
        user,
        business_name=payload.business_name,
        business_type=payload.business_type,
        initial_cash=payload.initial_cash,
    )
    organization.tax_id = (payload.tax_id or "").strip().upper() or None
    db.commit()
    db.refresh(organization)
    return OrganizationRead.model_validate(organization)
```

- [ ] **Step 4: Correr y confirmar que pasan**

Run: `pytest tests/test_nueva_empresa.py -q && ruff check app tests`
Expected: `6 passed` y `All checks passed!`

- [ ] **Step 5: Suite completa y commit**

Run: `pytest -q`
Expected: todo en verde.

```bash
git add app/domains/organizations/router.py tests/test_nueva_empresa.py
git commit -m "feat(despacho): alta de otra empresa en POST /api/organizations

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Frontend — empresas en sesión, cambio de empresa y rol real

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/stores/authStore.ts`
- Create: `frontend/src/lib/companies.ts`
- Modify: `frontend/src/components/layout/AppLayout.tsx`
- Modify: `frontend/src/features/auth/LoginPage.tsx`

**Interfaces:**
- Consumes: `GET /api/me` → `{user, memberships: [{organization_id, role}], organizations: [Organization]}` (ya existe); `GET /api/portfolio` (Task 2).
- Produces:
  - Tipos `Membership`, `MeResponse`, `PortfolioStatus`, `PortfolioItem` en `@/types/api`.
  - En `useAuthStore`: `organizations: Organization[]`, `memberships: Membership[]`, `setCompanies(me: MeResponse)`, `setOrganization(organization: Organization)`.
  - En `@/lib/companies`: `switchCompany(organization: Organization): void`, `loadCompanies(): Promise<MeResponse>`, `useCompanies()`, `useActiveRole(): string | null`.

- [ ] **Step 1: Tipos**

Al final de `frontend/src/types/api.ts`:

```ts
export interface Membership {
  organization_id: string
  role: string
}

export interface MeResponse {
  user: User
  memberships: Membership[]
  organizations: Organization[]
}

export type PortfolioStatus = 'red' | 'amber' | 'green'

/** Una fila de la cartera: una empresa del usuario y lo que tiene pendiente. */
export interface PortfolioItem {
  organization_id: string
  name: string
  tax_id: string | null
  business_type: string | null
  role: string
  cash: string
  receivable: string
  payable_overdue: string
  /** "AAAA-MM" del último mes cerrado, o null si nunca ha cerrado uno. */
  last_closed_period: string | null
  previous_month_closed: boolean
  pending_proposals: number
  status: PortfolioStatus
  reasons: string[]
}
```

- [ ] **Step 2: Store**

Reemplazar `frontend/src/stores/authStore.ts` completo por:

```ts
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { AuthResponse, MeResponse, Membership, Organization, User } from '@/types/api'

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  user: User | null
  /** La empresa activa: la que viaja en X-Organization-ID. */
  organization: Organization | null
  /** Todas las empresas del usuario y su rol en cada una (de /api/me). */
  organizations: Organization[]
  memberships: Membership[]
  isAuthenticated: boolean
  setSession: (auth: AuthResponse) => void
  setCompanies: (me: MeResponse) => void
  setOrganization: (organization: Organization) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      organization: null,
      organizations: [],
      memberships: [],
      isAuthenticated: false,
      setSession: (auth) =>
        set({
          accessToken: auth.access_token,
          refreshToken: auth.refresh_token,
          user: auth.user,
          organization: auth.organization,
          isAuthenticated: true,
        }),
      setCompanies: (me) =>
        set((state) => ({
          organizations: me.organizations,
          memberships: me.memberships,
          // Si la empresa activa ya no es suya (lo sacaron del equipo), se
          // activa otra: quedarse en ella daría 403 en todas las pantallas.
          organization:
            me.organizations.find((company) => company.id === state.organization?.id) ??
            me.organizations[0] ??
            null,
        })),
      setOrganization: (organization) => set({ organization }),
      logout: () =>
        set({
          accessToken: null,
          refreshToken: null,
          user: null,
          organization: null,
          organizations: [],
          memberships: [],
          isAuthenticated: false,
        }),
    }),
    { name: 'arca-auth' },
  ),
)
```

- [ ] **Step 3: Cambio de empresa**

`frontend/src/lib/companies.ts`:

```ts
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { queryClient } from '@/lib/queryClient'
import { useAuthStore } from '@/stores/authStore'
import type { MeResponse, Organization } from '@/types/api'

/** Consultas que son del usuario y no de la empresa activa: sobreviven al cambio. */
const USER_SCOPED = ['me', 'portfolio']

/** Tira todo lo que se pidió para la empresa anterior y vuelve a pedir lo que
 *  esté en pantalla, para que nunca se pinte una cifra de otra empresa. */
function resetCompanyQueries() {
  void queryClient.resetQueries({
    predicate: (query) => !USER_SCOPED.includes(String(query.queryKey[0])),
  })
}

/** Cambia la empresa activa. El orden importa: primero la empresa, para que las
 *  peticiones que dispara el reinicio ya lleven su encabezado. */
export function switchCompany(organization: Organization) {
  useAuthStore.getState().setOrganization(organization)
  resetCompanyQueries()
}

export async function loadCompanies(): Promise<MeResponse> {
  const { data } = await api.get<MeResponse>('/me')
  const before = useAuthStore.getState().organization?.id
  useAuthStore.getState().setCompanies(data)
  const after = useAuthStore.getState().organization?.id
  if (before && after !== before) resetCompanyQueries()
  return data
}

export function useCompanies() {
  return useQuery({ queryKey: ['me'], queryFn: loadCompanies })
}

/** Rol del usuario en la empresa activa; null mientras no se conoce. La
 *  autoridad es el backend: esto sólo decide qué navegación se enseña. */
export function useActiveRole(): string | null {
  return useAuthStore(
    (state) =>
      state.memberships.find((m) => m.organization_id === state.organization?.id)?.role ?? null,
  )
}
```

- [ ] **Step 4: Rol real en la navegación**

En `frontend/src/components/layout/AppLayout.tsx`:

a) Agregar el import:

```ts
import { useActiveRole, useCompanies } from '@/lib/companies'
```

b) Reemplazar:

```ts
  // MVP: el rol se infiere del registro (OWNER). Cuando haya multiusuario real,
  // vendrá de /api/me; la autoridad siempre es el backend.
  const role = 'OWNER'
```

por:

```ts
  // Mantiene al día las empresas y el rol del usuario. La autoridad siempre es
  // el backend: el rol aquí sólo decide qué navegación se enseña.
  useCompanies()
  const role = useActiveRole()
```

c) Reemplazar el filtro `.filter((item) => !item.roles || item.roles.includes(role))` por:

```ts
                .filter((item) => !item.roles || (role !== null && item.roles.includes(role)))
```

- [ ] **Step 5: Aterrizaje al iniciar sesión**

En `frontend/src/features/auth/LoginPage.tsx`:

a) Agregar el import:

```ts
import { loadCompanies } from '@/lib/companies'
```

b) Dentro de `onSubmit`, reemplazar:

```ts
      setSession(data)
      navigate('/')
```

por:

```ts
      setSession(data)
      // Quien lleva varias empresas llega a su cartera; con una sola, a su
      // tablero. Si /me falla se entra directo: la cartera es un atajo.
      let home = '/'
      try {
        const me = await loadCompanies()
        if (me.organizations.length > 1) home = '/despacho'
      } catch {
        // se entra al tablero de la empresa que devolvió el login
      }
      navigate(home)
```

- [ ] **Step 6: Verificar**

Run: `cd frontend && npm run typecheck`
Expected: sin errores.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/stores/authStore.ts frontend/src/lib/companies.ts frontend/src/components/layout/AppLayout.tsx frontend/src/features/auth/LoginPage.tsx
git commit -m "feat(despacho): empresas en sesión, cambio de empresa y rol real en la navegación

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Frontend — selector de empresa en el encabezado

**Files:**
- Modify: `frontend/src/lib/hooks.ts`
- Create: `frontend/src/components/layout/CompanySwitcher.tsx`
- Modify: `frontend/src/components/layout/AppHeader.tsx`

**Interfaces:**
- Consumes: de Task 4, `switchCompany(organization)` y `useAuthStore` con `organization` y `organizations`.
- Produces: `useDismiss(onDismiss: () => void)` exportado desde `@/lib/hooks` (devuelve un `ref` para un `<div>`); componente `CompanySwitcher` sin props.

- [ ] **Step 1: Mover `useDismiss` a los hooks compartidos**

En `frontend/src/lib/hooks.ts`, agregar al inicio el import:

```ts
import { useEffect, useRef } from 'react'
```

y al final del archivo:

```ts
/** Cierra un menú al hacer clic fuera o con Escape. */
export function useDismiss(onDismiss: () => void) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) onDismiss()
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onDismiss()
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [onDismiss])
  return ref
}
```

En `frontend/src/components/layout/AppHeader.tsx`: borrar la función local `useDismiss` con su comentario, cambiar `import { useEffect, useRef, useState } from 'react'` por `import { useState } from 'react'` y agregar `import { useDismiss } from '@/lib/hooks'`.

- [ ] **Step 2: El selector**

`frontend/src/components/layout/CompanySwitcher.tsx`:

```tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, ChevronsUpDown } from 'lucide-react'
import { switchCompany } from '@/lib/companies'
import { useDismiss } from '@/lib/hooks'
import { useAuthStore } from '@/stores/authStore'

const ITEM =
  'flex w-full items-center gap-2.5 px-3.5 py-2 text-left text-sm text-ink transition-colors hover:bg-surface-2'

/** Empresa activa y, para quien lleva varias, el cambio entre ellas. Con una
 *  sola empresa es sólo el nombre: un desplegable de una opción estorba. */
export function CompanySwitcher() {
  const navigate = useNavigate()
  const organization = useAuthStore((state) => state.organization)
  const organizations = useAuthStore((state) => state.organizations)
  const [open, setOpen] = useState(false)
  const ref = useDismiss(() => setOpen(false))

  if (organizations.length < 2) {
    return <div className="min-w-0 flex-1 truncate text-sm font-semibold">{organization?.name}</div>
  }

  const sorted = [...organizations].sort((a, b) => a.name.localeCompare(b.name, 'es'))

  return (
    <div className="relative min-w-0 flex-1" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Cambiar de empresa"
        className="-ml-2 flex max-w-full items-center gap-1.5 rounded-lg px-2 py-1 text-sm font-semibold transition-colors hover:bg-surface-2"
      >
        <span className="truncate">{organization?.name}</span>
        <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-muted" />
      </button>
      {open ? (
        <div
          role="menu"
          className="absolute left-0 top-10 max-h-80 w-72 overflow-y-auto rounded-xl border border-border bg-surface py-1 shadow-float"
        >
          {sorted.map((company) => (
            <button
              key={company.id}
              type="button"
              role="menuitem"
              className={ITEM}
              onClick={() => {
                setOpen(false)
                if (company.id === organization?.id) return
                switchCompany(company)
                navigate('/')
              }}
            >
              <span className="min-w-0 flex-1 truncate">{company.name}</span>
              {company.id === organization?.id ? (
                <Check className="h-4 w-4 shrink-0 text-accent" />
              ) : null}
            </button>
          ))}
          <button
            type="button"
            role="menuitem"
            className={`${ITEM} border-t border-border text-muted`}
            onClick={() => {
              setOpen(false)
              navigate('/despacho')
            }}
          >
            Ver todas mis empresas
          </button>
        </div>
      ) : null}
    </div>
  )
}
```

- [ ] **Step 3: Montarlo en el encabezado**

En `frontend/src/components/layout/AppHeader.tsx`:

a) Agregar `import { CompanySwitcher } from '@/components/layout/CompanySwitcher'`.

b) Reemplazar la línea

```tsx
      <div className="min-w-0 flex-1 truncate text-sm font-semibold">{organization?.name}</div>
```

por

```tsx
      <CompanySwitcher />
```

c) Cambiar `const { user, organization, logout } = useAuthStore()` por `const { user, logout } = useAuthStore()`.

- [ ] **Step 4: Verificar**

Run: `cd frontend && npm run typecheck`
Expected: sin errores (en particular, ninguna variable sin usar en `AppHeader.tsx`).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/hooks.ts frontend/src/components/layout/CompanySwitcher.tsx frontend/src/components/layout/AppHeader.tsx
git commit -m "feat(despacho): selector de empresa en el encabezado

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Frontend — página "Mis empresas"

**Files:**
- Create: `frontend/src/features/portfolio/PortfolioPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`
- Modify: `frontend/src/components/ui/CommandPalette.tsx`

**Interfaces:**
- Consumes: `GET /api/portfolio` (Task 2), `POST /api/organizations` (Task 3); de Task 4, `switchCompany`, `loadCompanies`, los tipos `PortfolioItem` y `PortfolioStatus`, y `useAuthStore` con `organization` y `organizations`.
- Produces: componente `PortfolioPage` (export nombrado) y la ruta `/despacho`.

- [ ] **Step 1: La página**

`frontend/src/features/portfolio/PortfolioPage.tsx`:

```tsx
/** Mis empresas: la cartera de quien lleva varias contabilidades. Una fila por
 *  empresa, lo urgente arriba, y el porqué del semáforo escrito en la fila. */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { TextInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { Money } from '@/components/ui/Money'
import { PageHeader } from '@/components/ui/PageHeader'
import { Table } from '@/components/ui/Table'
import { loadCompanies, switchCompany } from '@/lib/companies'
import { useAuthStore } from '@/stores/authStore'
import type { Organization, Page, PortfolioItem, PortfolioStatus } from '@/types/api'

const STATUS: Record<PortfolioStatus, { label: string; dot: string; text: string }> = {
  red: { label: 'Urgente', dot: 'bg-neg', text: 'text-neg' },
  amber: { label: 'Por atender', dot: 'bg-warn', text: 'text-warn' },
  green: { label: 'Al corriente', dot: 'bg-pos', text: 'text-pos' },
}

const ROLE_LABELS: Record<string, string> = {
  OWNER: 'Dueño',
  ADMIN: 'Administrador',
  ACCOUNTANT: 'Contador',
  MEMBER: 'Captura',
  VIEWER: 'Consulta',
}

const EMPTY_FORM = { business_name: '', tax_id: '', initial_cash: '' }

function formatPeriod(period: string | null): string {
  if (!period) return 'Ninguno'
  const [year, month] = period.split('-').map(Number)
  return new Date(year, month - 1, 1).toLocaleDateString('es-MX', {
    month: 'short',
    year: 'numeric',
  })
}

/** "1 urgente · 2 por atender · 1 al corriente": el resumen que se lee de un vistazo. */
function summarize(items: PortfolioItem[]): string {
  const count = (status: PortfolioStatus) => items.filter((item) => item.status === status).length
  const red = count('red')
  const amber = count('amber')
  const green = count('green')
  return [
    red ? `${red} ${red === 1 ? 'urgente' : 'urgentes'}` : null,
    amber ? `${amber} por atender` : null,
    green ? `${green} al corriente` : null,
  ]
    .filter(Boolean)
    .join(' · ')
}

const right = (label: string) => <span className="block text-right">{label}</span>

export function PortfolioPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const active = useAuthStore((state) => state.organization)
  const organizations = useAuthStore((state) => state.organizations)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [formError, setFormError] = useState<string | null>(null)

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['portfolio'],
    queryFn: async () => (await api.get<Page<PortfolioItem>>('/portfolio')).data.items,
  })

  const create = useMutation({
    mutationFn: async () => {
      const payload: Record<string, string> = { business_name: form.business_name }
      if (form.tax_id.trim()) payload.tax_id = form.tax_id.trim()
      if (form.initial_cash) payload.initial_cash = form.initial_cash
      return (await api.post<Organization>('/organizations', payload)).data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['portfolio'] })
      void queryClient.invalidateQueries({ queryKey: ['me'] })
      setCreating(false)
      setForm(EMPTY_FORM)
      setFormError(null)
    },
    onError: (err) => setFormError(errorMessage(err)),
  })

  async function open(item: PortfolioItem) {
    // La lista de la sesión puede ir un paso atrás de la cartera (empresa recién
    // creada): si no está, se vuelve a pedir antes de entrar.
    const company =
      organizations.find((candidate) => candidate.id === item.organization_id) ??
      (await loadCompanies()).organizations.find(
        (candidate) => candidate.id === item.organization_id,
      )
    if (!company) return
    if (company.id !== active?.id) switchCompany(company)
    navigate('/')
  }

  const items = data ?? []

  return (
    <>
      <PageHeader
        title="Mis empresas"
        description={
          items.length > 0
            ? `${items.length} ${items.length === 1 ? 'empresa' : 'empresas'} · ${summarize(items)}`
            : 'Todas las empresas que llevas, en un solo lugar.'
        }
        actions={<Button onClick={() => setCreating(true)}>+ Nueva empresa</Button>}
      />

      {isLoading ? (
        <div className="h-48 animate-pulse rounded-xl bg-surface-2" />
      ) : error ? (
        <EmptyState
          title="No pudimos cargar tus empresas"
          message={errorMessage(error)}
          action={<Button onClick={() => void refetch()}>Reintentar</Button>}
        />
      ) : (
        <Table
          headers={[
            'Empresa',
            'Estado',
            'Tu rol',
            right('Caja'),
            right('Por cobrar'),
            right('Vencido por pagar'),
            'Último cierre',
            right('Propuestas'),
          ]}
          secondary={[3, 5, 7, 8]}
        >
          {items.map((item) => {
            const status = STATUS[item.status]
            const overdue = Number(item.payable_overdue) > 0
            return (
              <tr
                key={item.organization_id}
                className="cursor-pointer align-top transition-colors hover:bg-surface-2/60"
                onClick={() => void open(item)}
              >
                <td className="px-4 py-3">
                  {/* El botón hace la fila alcanzable con teclado; el clic en
                      cualquier otra celda es un atajo de ratón. */}
                  <button
                    type="button"
                    className="text-left font-medium hover:text-accent"
                    onClick={(event) => {
                      event.stopPropagation()
                      void open(item)
                    }}
                  >
                    {item.name}
                  </button>
                  {item.organization_id === active?.id ? (
                    <span className="ml-2 text-xs text-muted">(abierta)</span>
                  ) : null}
                  <div className="figures mt-0.5 text-xs text-muted">{item.tax_id ?? 'Sin RFC'}</div>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-semibold ${status.text}`}
                  >
                    <span className={`h-2 w-2 rounded-full ${status.dot}`} aria-hidden />
                    {status.label}
                  </span>
                  {item.reasons.map((reason) => (
                    <div key={reason} className="mt-0.5 text-xs text-muted">
                      {reason}
                    </div>
                  ))}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-muted">
                  {ROLE_LABELS[item.role] ?? item.role}
                </td>
                <td className="px-4 py-3 text-right">
                  <Money value={item.cash} size="sm" />
                </td>
                <td className="px-4 py-3 text-right">
                  <Money value={item.receivable} size="sm" />
                </td>
                <td className="px-4 py-3 text-right">
                  <Money value={item.payable_overdue} size="sm" tone={overdue ? 'neg' : 'muted'} />
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-muted">
                  {formatPeriod(item.last_closed_period)}
                </td>
                <td className="figures px-4 py-3 text-right">
                  {item.pending_proposals > 0 ? item.pending_proposals : '—'}
                </td>
              </tr>
            )
          })}
        </Table>
      )}

      {!isLoading && !error && items.length === 1 ? (
        <p className="mt-4 text-sm text-muted">
          Hoy llevas una sola empresa. Si llevas la contabilidad de otras, agrégalas aquí y cambia
          entre ellas sin cerrar sesión.
        </p>
      ) : null}

      <Modal title="Nueva empresa" open={creating} onClose={() => setCreating(false)}>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            create.mutate()
          }}
        >
          <TextInput
            label="Nombre de la empresa"
            required
            autoFocus
            placeholder="Ferretería El Tornillo"
            value={form.business_name}
            onChange={(event) => setForm({ ...form, business_name: event.target.value })}
          />
          <TextInput
            label="RFC (opcional)"
            placeholder="FET180312AB1"
            maxLength={13}
            value={form.tax_id}
            onChange={(event) => setForm({ ...form, tax_id: event.target.value.toUpperCase() })}
          />
          <TextInput
            label="Dinero en caja al empezar (opcional)"
            type="number"
            min="0"
            step="0.01"
            inputMode="decimal"
            placeholder="0.00"
            hint="ARCA crea su catálogo contable, sus categorías y la cuenta Caja con este saldo."
            value={form.initial_cash}
            onChange={(event) => setForm({ ...form, initial_cash: event.target.value })}
          />
          {formError ? (
            <p role="alert" className="rounded border-l-2 border-neg bg-neg/10 px-3 py-2 text-sm text-neg">
              {formError}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setCreating(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? 'Creando…' : 'Crear empresa'}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  )
}
```

- [ ] **Step 2: Ruta**

En `frontend/src/App.tsx`, agregar junto a las demás rutas diferidas:

```tsx
const PortfolioPage = lazyRoute(
  () => import('@/features/portfolio/PortfolioPage'),
  (m) => m.PortfolioPage,
)
```

y dentro de `<Route element={<SuspenseOutlet />}>`, después de la ruta `/agentes`:

```tsx
              <Route path="/despacho" element={<PortfolioPage />} />
```

- [ ] **Step 3: Navegación y paleta**

En `frontend/src/components/layout/AppLayout.tsx`: agregar `Briefcase` al import de `lucide-react` y, en la primera sección de `NAV_SECTIONS`, después de Agentes:

```ts
      { to: '/despacho', label: 'Mis empresas', icon: Briefcase },
```

En `frontend/src/components/ui/CommandPalette.tsx`, después de la entrada `{ label: 'Agentes', … }`:

```ts
  { label: 'Mis empresas', hint: 'Ir a', to: '/despacho', keywords: 'despacho cartera clientes cambiar empresa contador' },
```

- [ ] **Step 4: Verificar**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: sin errores; el build termina y lista un chunk `PortfolioPage-*.js`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/portfolio frontend/src/App.tsx frontend/src/components/layout/AppLayout.tsx frontend/src/components/ui/CommandPalette.tsx
git commit -m "feat(despacho): página Mis empresas con semáforo y alta de empresa

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Siembra de la demo y verificación de punta a punta

**Files:**
- Create: `scripts/demo_despacho.py`
- Modify: `docs/MVP_STATUS.md`

**Interfaces:**
- Consumes: toda la API anterior por HTTP: `/auth/register`, `/organizations`, `/organizations/current`, `/organizations/current/members`, `/accounts`, `/categories`, `/income`, `/expenses`, `/vendors`, `/payables`, `/periods/close`, `/agent-keys`, `/agent/invoke`, `/portfolio`.
- Produces: `python scripts/demo_despacho.py --url <base>` crea un contador con cuatro empresas (una por estado del semáforo) e imprime credenciales y la cartera resultante.

- [ ] **Step 1: El script**

`scripts/demo_despacho.py`:

```python
"""Prepara la cartera de un despacho contable para enseñársela a un contador.

Crea un contador con cuatro empresas, una por cada estado del semáforo:

    A  su propio despacho      al corriente (mes anterior cerrado)
    B  Ferretería El Tornillo  mes anterior sin cerrar
    C  Restaurante La Milpa    cuentas por pagar vencidas
    D  Clínica Dental Sonríe   propuestas de agentes por revisar

B y C las dio de alta el contador (él lleva al cliente). En D la dueña ya usaba
ARCA y lo invitó como contador (el cliente lo trae a él).

    python scripts/demo_despacho.py --url https://arca-production-d769.up.railway.app

Cada corrida crea cuentas NUEVAS (correo con marca de tiempo): se puede ensayar
las veces que haga falta sin pisar la anterior.

OJO con el día 17: hasta ese día B se ve "Por atender"; después, "Urgente".
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta

import httpx

# Ventas: (concepto, categoría, monto). Gastos: (concepto, categoría, monto, tasa de IVA).
DESPACHO = {
    "opening": "120000",
    "incomes": (
        ("Igualas contables del mes", "Servicios", "86000"),
        ("Declaraciones anuales", "Servicios", "24000"),
    ),
    "expenses": (
        ("Nómina del despacho", "Nómina", "42000", "0"),
        ("Renta de oficina", "Renta", "13920", "0.16"),
        ("Licencias de software", "Software", "5800", "0.16"),
    ),
}
FERRETERIA = {
    "name": "Ferretería El Tornillo",
    "business_type": "commerce",
    "tax_id": "FET180312AB1",
    "opening": "95000",
    "incomes": (
        ("Ventas de mostrador, primera quincena", "Ventas", "148000"),
        ("Ventas de mostrador, segunda quincena", "Ventas", "163500"),
    ),
    "expenses": (
        ("Compra de mercancía", "Inventario", "121800", "0.16"),
        ("Nómina quincenal", "Nómina", "38000", "0"),
        ("Renta del local", "Renta", "17400", "0.16"),
    ),
}
RESTAURANTE = {
    "name": "Restaurante La Milpa",
    "business_type": "restaurant",
    "tax_id": "RLM200915KL4",
    "opening": "60000",
    "incomes": (
        ("Ventas de salón", "Ventas", "212000"),
        ("Banquetes y eventos", "Servicios", "58000"),
    ),
    "expenses": (
        ("Insumos y abarrotes", "Inventario", "96000", "0"),
        ("Nómina quincenal", "Nómina", "54000", "0"),
        ("Renta del local", "Renta", "29000", "0.16"),
    ),
}
CLINICA = {
    "name": "Clínica Dental Sonríe",
    "business_type": "services",
    "tax_id": "CDS190227QX8",
    "opening": "140000",
    "incomes": (
        ("Consultas y limpiezas", "Servicios", "98000"),
        ("Ortodoncia", "Servicios", "126000"),
    ),
    "expenses": (
        ("Material dental", "Inventario", "41760", "0.16"),
        ("Nómina quincenal", "Nómina", "62000", "0"),
        ("Renta del consultorio", "Renta", "20880", "0.16"),
    ),
}
# Lo que un agente encontró en el banco de la clínica y dejó por aprobar.
PROPUESTAS = (
    ("Cargo recurrente de laboratorio dental", "Inventario", "8700", "Cargo mensual del laboratorio; coincide con los tres meses anteriores."),
    ("Mantenimiento del compresor", "Otros", "3480", "Transferencia a un proveedor nuevo; falta la factura."),
    ("Publicidad en redes", "Marketing", "2900", "Cargo con tarjeta; no hay gasto registrado ese día."),
)  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description="Cartera de un despacho para la demo")
    parser.add_argument("--url", default="http://localhost:8000", help="ARCA base URL")
    parser.add_argument("--password", default="demodespacho2026")
    parser.add_argument("--contador", default="C.P. Demo", help="Nombre del contador")
    parser.add_argument("--despacho", default="Despacho Contable del Valle")
    args = parser.parse_args()

    # El correo lleva la hora para que dos ensayos del mismo día no choquen.
    stamp = datetime.now().strftime("%m%d%H%M")
    contador_email = f"contador{stamp}@atlas.mx"
    duena_email = f"duena{stamp}@atlas.mx"
    http = httpx.Client(base_url=f"{args.url.rstrip('/')}/api", timeout=60)

    def call(method: str, path: str, headers: dict, **kwargs):
        response = http.request(method, path, headers=headers, **kwargs)
        if response.status_code >= 400:
            sys.exit(f"{method} {path}: {response.status_code} {response.text}")
        return response.json()

    def post(path: str, payload: dict, headers: dict):
        return call("POST", path, headers, json=payload)

    def session(auth: dict, organization_id: str) -> dict:
        return {
            "Authorization": f"Bearer {auth['access_token']}",
            "X-Organization-ID": organization_id,
        }

    today = date.today()
    last_month_end = today.replace(day=1) - timedelta(days=1)
    year, month = last_month_end.year, last_month_end.month

    def last_month(day: int) -> str:
        return date(year, month, day).isoformat()

    def operate(headers: dict, profile: dict) -> dict:
        """Un mes anterior creíble: ventas cobradas y gastos pagados desde el banco."""
        bank = post(
            "/accounts",
            {"name": "BBVA Empresarial", "type": "BANK",
             "opening_balance": profile["opening"], "institution": "BBVA"},
            headers,
        )
        income = {c["name"]: c for c in call("GET", "/categories", headers, params={"kind": "INCOME"})}
        expense = {c["name"]: c for c in call("GET", "/categories", headers, params={"kind": "EXPENSE"})}
        for day, (description, category, amount) in zip((9, 23), profile["incomes"]):
            post("/income", {
                "date": last_month(day),
                "description": description,
                "amount": amount,
                "tax_rate": "0.16",
                "category_id": income[category]["id"],
                "financial_account_id": bank["id"],
                "status": "PAID",
            }, headers)
        for day, (description, category, amount, tax_rate) in zip((5, 14, 20), profile["expenses"]):
            post("/expenses", {
                "date": last_month(day),
                "description": description,
                "amount": amount,
                "tax_rate": tax_rate,
                "category_id": expense[category]["id"],
                "financial_account_id": bank["id"],
                "status": "PAID",
            }, headers)
        return expense

    def close_last_month(headers: dict) -> None:
        post("/periods/close", {"year": year, "month": month}, headers)

    def register(email: str, name: str, business: str, business_type: str) -> dict:
        return post("/auth/register", {
            "email": email,
            "password": args.password,
            "name": name,
            "business_name": business,
            "business_type": business_type,
            "initial_cash": "5000",
        }, {})

    def new_company(auth: dict, profile: dict) -> dict:
        organization = post("/organizations", {
            "business_name": profile["name"],
            "business_type": profile["business_type"],
            "tax_id": profile["tax_id"],
            "initial_cash": "5000",
        }, {"Authorization": f"Bearer {auth['access_token']}"})
        return session(auth, organization["id"])

    # --- A · El despacho: la casa del contador, al corriente ---
    contador = register(contador_email, args.contador, args.despacho, "services")
    despacho = session(contador, contador["organization"]["id"])
    call("PATCH", "/organizations/current", despacho, json={"tax_id": "DCV150604MN2"})
    operate(despacho, DESPACHO)
    close_last_month(despacho)

    # --- B · Ferretería: operó el mes pasado y nadie lo ha cerrado ---
    ferreteria = new_company(contador, FERRETERIA)
    operate(ferreteria, FERRETERIA)

    # --- C · Restaurante: mes cerrado, pero le debe a un proveedor desde hace días ---
    restaurante = new_company(contador, RESTAURANTE)
    categorias = operate(restaurante, RESTAURANTE)
    proveedor = post("/vendors", {"name": "Carnes Selectas del Bajío"}, restaurante)
    # La cuenta por pagar se registra ANTES de cerrar el mes: su fecha de
    # registro puede caer en el mes anterior y un mes cerrado la rechazaría.
    post("/payables", {
        "vendor_id": proveedor["id"],
        "description": "Factura de cárnicos",
        "amount": "38400",
        "tax_rate": "0",
        "date": (today - timedelta(days=40)).isoformat(),
        "due_date": (today - timedelta(days=10)).isoformat(),
        "category_id": categorias["Inventario"]["id"],
    }, restaurante)
    close_last_month(restaurante)

    # --- D · Clínica: la dueña ya usaba ARCA e invita a su contador ---
    duena = register(duena_email, "Dra. Sofía Rangel", CLINICA["name"], CLINICA["business_type"])
    clinica = session(duena, duena["organization"]["id"])
    call("PATCH", "/organizations/current", clinica, json={"tax_id": CLINICA["tax_id"]})
    categorias = operate(clinica, CLINICA)
    close_last_month(clinica)
    post("/organizations/current/members", {
        "email": contador_email,
        "name": args.contador,
        "role": "ACCOUNTANT",
        "password": args.password,
    }, clinica)
    llave = post("/agent-keys", {"name": "Agente de conciliación", "scopes": "READ,PROPOSE"}, clinica)
    for description, category, amount, summary in PROPUESTAS:
        resultado = post("/agent/invoke", {
            "tool": "propose_expense",
            "arguments": {
                "date": today.isoformat(),
                "description": description,
                "amount": amount,
                "category_id": categorias[category]["id"],
                "summary": summary,
            },
        }, {"Authorization": f"Bearer {llave['token']}"})
        if not resultado.get("ok"):
            sys.exit(f"El agente no pudo proponer: {resultado}")

    cartera = call("GET", "/portfolio", {"Authorization": f"Bearer {contador['access_token']}"})

    print("\n╭─ Cartera lista ────────────────────────────────────────")
    print(f"│ URL        {args.url}")
    print(f"│ Contador   {contador_email}")
    print(f"│ Dueña (D)  {duena_email}")
    print(f"│ Contraseña {args.password}")
    print("│")
    for item in cartera["items"]:
        motivos = "; ".join(item["reasons"]) or "sin pendientes"
        print(f"│ {item['status']:<6} {item['name']:<28} {item['role']:<10} {motivos}")
    print("╰────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Suite, lint y build**

Run: `pytest -q && ruff check . && (cd frontend && npm run typecheck && npm run build)`
Expected: todo en verde.

- [ ] **Step 3: Levantar ARCA en local con una base desechable**

`S` es el directorio scratchpad de la sesión.

```bash
export DATABASE_URL="sqlite:///$S/despacho.db"
alembic upgrade head
uvicorn app.main:app --port 8000 &
```

Si `alembic upgrade head` falla en SQLite, crear las tablas de la base desechable con:
`python -c "import app.models; from app.database import Base, engine; Base.metadata.create_all(engine)"`

Run: `curl -s http://localhost:8000/api/health`
Expected: respuesta 200.

- [ ] **Step 4: Sembrar y revisar la cartera impresa**

Run: `python scripts/demo_despacho.py --url http://localhost:8000`
Expected: cuatro filas en este orden: `red` Restaurante La Milpa (`OWNER`, "$38,400.00 por pagar vencidos"); `amber` Clínica Dental Sonríe (`ACCOUNTANT`, "3 propuestas por revisar"); `amber` Ferretería El Tornillo (`OWNER`, "… sigue sin cerrar"; `red` y primera en la lista si hoy es después del día 17); `green` Despacho Contable del Valle (`OWNER`, "sin pendientes").

- [ ] **Step 5: Capturas de `/despacho`**

Playwright no corre en esta WSL: se usa Edge de Windows en modo headless. Como la página pide sesión, una página puente del mismo origen la deja en `localStorage` y redirige.

```bash
cd frontend
cat > dist/__seed.html <<'EOF'
<script>
localStorage.setItem('arca-auth', decodeURIComponent(location.hash.slice(1)))
location.replace('/despacho')
</script>
EOF
(npx vite preview --port 4174 &) && sleep 6

URL=$(DEMO_EMAIL="<correo del contador que imprimió el Step 4>" python - <<'EOF'
import json, os, urllib.parse
import httpx
base = "http://localhost:8000/api"
auth = httpx.post(f"{base}/auth/login", json={"email": os.environ["DEMO_EMAIL"], "password": "demodespacho2026"}).json()
me = httpx.get(f"{base}/me", headers={"Authorization": f"Bearer {auth['access_token']}"}).json()
state = {
    "accessToken": auth["access_token"], "refreshToken": auth["refresh_token"],
    "user": auth["user"], "organization": auth["organization"],
    "organizations": me["organizations"], "memberships": me["memberships"],
    "isAuthenticated": True,
}
print("http://localhost:4174/__seed.html#" + urllib.parse.quote(json.dumps({"state": state, "version": 0})))
EOF
)
W=$(wslpath -w "$S")
EDGE="/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
"$EDGE" --headless=new --disable-gpu --virtual-time-budget=8000 \
  --force-device-scale-factor=2 --window-size=1280,860 \
  --screenshot="$W\\despacho.png" "$URL"
"$EDGE" --headless=new --disable-gpu --virtual-time-budget=8000 \
  --force-device-scale-factor=2 --window-size=430,860 \
  --screenshot="$W\\despacho-movil.png" "$URL"
```

Leer `despacho.png` y `despacho-movil.png` y confirmar: cuatro filas en el orden del Step 4; punto y etiqueta del semáforo en rojo, ámbar y verde con sus causas escritas; cifras alineadas a la derecha con `.figures`; el encabezado muestra el selector de empresa con el icono de cambio; "Mis empresas" aparece en la barra lateral; en móvil no hay scroll lateral. Si la captura muestra el login, subir `--virtual-time-budget` a 15000 y repetir.

- [ ] **Step 6: Recorrido a mano de lo que las capturas no prueban**

Con `npm run dev` (o el preview) y el contador sembrado:

1. Iniciar sesión como el contador: aterriza en `/despacho`.
2. Clic en "Restaurante La Milpa": abre su tablero y el encabezado cambia de nombre; Por pagar muestra la factura vencida. Ninguna cifra del despacho queda en pantalla.
3. Con el selector del encabezado cambiar a "Clínica Dental Sonríe": el contador de Propuestas en la barra lateral marca 3 y la sección Contabilidad sigue visible (rol `ACCOUNTANT`).
4. En `/despacho`, "+ Nueva empresa" con nombre en blanco no se envía; con un nombre válido aparece una quinta fila verde y se puede entrar a ella.
5. Iniciar sesión como la dueña (una sola empresa): aterriza en el tablero y el encabezado muestra el nombre sin desplegable.
6. Review Focus 5: como la dueña, en Configuración → Equipo, quitar al contador. En la sesión del contador, con la clínica abierta, recargar la página: debe quedar en otra de sus empresas, sin pantallas de error 403.

Cualquier fallo aquí se corrige antes de continuar y se vuelve a correr el Step 2.

- [ ] **Step 7: Apagar lo que se levantó**

```bash
kill %1 2>/dev/null; pkill -f "vite preview" ; pkill -f "uvicorn app.main:app --port 8000"
rm -f frontend/dist/__seed.html
```

- [ ] **Step 8: Estado y commit**

En `docs/MVP_STATUS.md`, cambiar la fecha de la cabecera a `2026-10-05`, agregar al final de la lista bajo "In Progress" (donde viven los bloques ya terminados más recientes):

```markdown
- **Portal de despacho** (spec 2026-10-05): cartera del usuario en `GET /api/portfolio` con semáforo (mes sin cerrar, vencidos por pagar, propuestas pendientes), alta de otra empresa en `POST /api/organizations`, selector de empresa en el encabezado, página "Mis empresas" (`/despacho`), rol real desde `/api/me`. Demo: `scripts/demo_despacho.py`.
```

y borrar de "Next" las dos líneas que esto resuelve: "Selector de organización multi-empresa en UI…" y "Rol real desde /api/me en el frontend…", además de la mención "selector multi-empresa en UI" en la línea de M3/M4.

```bash
git add scripts/demo_despacho.py docs/MVP_STATUS.md
git commit -m "feat(despacho): siembra de la demo para el contador y estado actualizado

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Después de este plan

- **Despliegue:** merge a `main` y push despliegan a producción (Railway). Lo decide Emmanuel; después se corre `python scripts/demo_despacho.py --url https://arca-production-d769.up.railway.app --contador "<nombre del contador>"` y se guardan las credenciales.
- **Sub-proyecto 2:** puente a CONTPAQi, con su propia spec.
- **Guion de la demo** sobre lo que quede construido.
