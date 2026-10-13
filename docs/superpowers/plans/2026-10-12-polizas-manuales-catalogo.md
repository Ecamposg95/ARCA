# Pólizas manuales y catálogo editable (C-1) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el contador capture pólizas de diario a mano, las revierta, y dé de alta, renombre y desactive cuentas de detalle del catálogo, todo por el motor existente.

**Architecture:** Dos reglas nuevas en `rules.py` (`manual_entry`, `reverse_manual_entry`) que validan lo propio de una captura manual y delegan en `post_journal_entry` y `reversal_of`; funciones de catálogo en `coa.py`; endpoints en el router de contabilidad que traducen `LookupError` a 404 y `ValueError` a 400. En el frontend, dos modales (`JournalEntryForm`, `AccountForm`) y cambios en la página de Contabilidad y el diario. Sin migración.

**Tech Stack:** FastAPI 0.127, SQLAlchemy 2, Pydantic v2, pytest (SQLite en memoria) · React 18, TypeScript, TanStack Query v5, Tailwind.

**Spec:** `docs/superpowers/specs/2026-10-12-polizas-manuales-catalogo-design.md`

## Global Constraints

- Nunca crear `JournalEntry`/`JournalEntryLine` fuera de `post_journal_entry` (AGENTS.md §1).
- Dinero: `Decimal` en Python, strings en JSON; schemas con `allow_inf_nan=False`.
- Errores de API: `{"detail": "mensaje en español"}`; 400 regla de negocio, 404 recurso ajeno o inexistente.
- Copy en español, tokens semánticos de Tailwind (`bg-surface`, `text-muted`, `text-neg`, `text-pos`), cifras con clase `figures`.
- `ruff check .` con `line-length = 120`; commits en Conventional Commits en español.
- Las cuentas 1100, 1200, 2100, 2200 nunca reciben pólizas manuales (mantienen saldos espejo).
- El catálogo se queda en dos niveles: toda cuenta nueva cuelga de una mayor (sin `parent_id`).
- Sin migración: C-1 no cambia el esquema.

## Review Focus

1. Montos con más de dos decimales (`"10.005"`): el motor cuantiza a centavos; una póliza que cuadra en tres decimales y descuadra en dos debe rechazarse con "no está balanceado" (prueba en Task 1).
2. Línea con cargo y abono en cero (`debit=0, credit=0`): debe rechazarse por el motor con "Cada línea debe tener cargo o abono"; el frontend la omite antes de enviar (pruebas en Task 1 y Task 4).
3. Misma cuenta en dos líneas (cargo en una, abono en otra): es válido contablemente y debe aceptarse (prueba en Task 1).
4. Código de cuenta con ceros a la izquierda o espacios (`" 05210 "`): se recorta; "05210" no empieza con 5 → 400 (prueba en Task 3).
5. Reverso con fecha en un mes ya cerrado: el motor lo rechaza con "cerrado" y la póliza original queda sin revertir (prueba en Task 2).

---

### Task 1: Regla `manual_entry` y `POST /api/accounting/journal-entries`

**Files:**
- Modify: `app/services/accounting/rules.py` (imports arriba; funciones nuevas al final)
- Modify: `app/domains/accounting/router.py` (imports, schemas, helper `_entry_read`, endpoint)
- Test: `tests/test_polizas_manuales.py`

**Interfaces:**
- Consumes: `post_journal_entry(db, organization_id, date, description, lines, source_type, source_id, reference, created_by, kind)` y `LineSpec` de `engine.py`; `AccountingError` de `engine.py`.
- Produces: `ManualLine(account_id, debit, credit, description)`, `MODULE_CONTROLLED_CODES: dict[str, str]`, `manual_entry(db, organization_id, date, description, lines, reference=None, created_by=None) -> JournalEntry` (lanza `LookupError` si una cuenta no es de la empresa, `AccountingError` en reglas); en el router, `_entry_read(db, entry) -> JournalEntryRead`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_polizas_manuales.py`:

```python
"""Pólizas manuales: el contador captura lo que los módulos no saben hacer."""

from datetime import date, timedelta
from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client, email="contador@example.com"):
    body = register(client, email=email, initial_cash="50000")
    headers = auth_headers(body)
    accounts = client.get("/api/accounting/accounts", headers=headers).json()
    by_code = {account["code"]: account for account in accounts}
    return headers, by_code


def _entry(client, headers, lines, when=None, description="Provisión de nómina", reference=None):
    return client.post(
        "/api/accounting/journal-entries",
        headers=headers,
        json={
            "date": (when or date.today()).isoformat(),
            "description": description,
            "reference": reference,
            "lines": lines,
        },
    )


def _line(account, debit="0", credit="0", description=None):
    return {"account_id": account["id"], "debit": debit, "credit": credit, "description": description}


def test_balanced_entry_is_posted_as_diario(client):
    headers, acc = _setup(client)
    response = _entry(
        client,
        headers,
        [
            _line(acc["5200"], debit="1000", description="Sueldos"),
            _line(acc["2400"], credit="100"),
            _line(acc["3100"], credit="900"),
        ],
        reference="NOM-10",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["folio"].startswith("Dr-")
    assert body["kind"] == "DIARIO"
    assert body["source_type"] == "manual"
    assert body["source_id"] == body["id"]
    assert body["reference"] == "NOM-10"
    assert body["reversed"] is False
    assert body["reversal_of"] is None
    assert len(body["lines"]) == 3

    diary = client.get("/api/accounting/journal-entries", headers=headers).json()
    assert any(item["id"] == body["id"] for item in diary["items"])
    balance = client.get("/api/accounting/trial-balance", headers=headers).json()
    nomina = next(row for row in balance["rows"] if row["code"] == "5200")
    assert Decimal(str(nomina["debit"])) == Decimal("1000")


def test_same_account_on_both_sides_is_fine(client):
    headers, acc = _setup(client)
    response = _entry(
        client,
        headers,
        [_line(acc["5100"], debit="300"), _line(acc["5100"], credit="100"), _line(acc["3100"], credit="200")],
    )
    assert response.status_code == 201, response.text


def test_unbalanced_entry_is_rejected(client):
    headers, acc = _setup(client)
    response = _entry(client, headers, [_line(acc["5200"], debit="1000"), _line(acc["3100"], credit="900")])
    assert response.status_code == 400
    assert "balanceado" in response.json()["detail"]


def test_three_decimals_that_only_balance_before_rounding_are_rejected(client):
    headers, acc = _setup(client)
    response = _entry(
        client,
        headers,
        [_line(acc["5200"], debit="10.005"), _line(acc["3100"], credit="10.004"), _line(acc["3200"], credit="0.001")],
    )
    assert response.status_code == 400


def test_single_line_and_empty_line_are_rejected(client):
    headers, acc = _setup(client)
    assert _entry(client, headers, [_line(acc["5200"], debit="10")]).status_code == 422
    response = _entry(client, headers, [_line(acc["5200"], debit="10", credit="10"), _line(acc["3100"])])
    assert response.status_code == 400
    assert "cargo o abono" in response.json()["detail"]


def test_major_account_is_rejected(client):
    headers, acc = _setup(client)
    response = _entry(client, headers, [_line(acc["5000"], debit="10"), _line(acc["3100"], credit="10")])
    assert response.status_code == 400
    assert "cuenta mayor" in response.json()["detail"]


def test_module_controlled_accounts_are_rejected(client):
    headers, acc = _setup(client)
    for code in ("1100", "1200", "2100", "2200"):
        response = _entry(client, headers, [_line(acc[code], debit="10"), _line(acc["3100"], credit="10")])
        assert response.status_code == 400, code
        assert "Movimientos" in response.json()["detail"]


def test_future_date_is_rejected(client):
    headers, acc = _setup(client)
    response = _entry(
        client,
        headers,
        [_line(acc["5200"], debit="10"), _line(acc["3100"], credit="10")],
        when=date.today() + timedelta(days=1),
    )
    assert response.status_code == 400
    assert "futura" in response.json()["detail"]


def test_closed_month_is_rejected(client):
    headers, acc = _setup(client)
    end = date.today().replace(day=1) - timedelta(days=1)
    assert (
        client.post("/api/periods/close", headers=headers, json={"year": end.year, "month": end.month}).status_code
        == 200
    )
    response = _entry(
        client, headers, [_line(acc["5200"], debit="10"), _line(acc["3100"], credit="10")], when=end
    )
    assert response.status_code == 400
    assert "cerrado" in response.json()["detail"]


def test_other_company_account_is_not_found(client):
    headers, acc = _setup(client)
    other_headers, other_acc = _setup(client, email="otra@example.com")
    response = _entry(client, headers, [_line(other_acc["5200"], debit="10"), _line(acc["3100"], credit="10")])
    assert response.status_code == 404


def test_instrument_balances_do_not_move(client):
    headers, acc = _setup(client)
    before = client.get("/api/accounts", headers=headers).json()[0]["current_balance"]
    assert _entry(client, headers, [_line(acc["5200"], debit="10"), _line(acc["3100"], credit="10")]).status_code == 201
    after = client.get("/api/accounts", headers=headers).json()[0]["current_balance"]
    assert before == after
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `source .venv/bin/activate && pytest tests/test_polizas_manuales.py -q`
Expected: todas FAIL con 405 o 404 (el endpoint no existe).

- [ ] **Step 3: Agregar la regla en `rules.py`**

Arriba del archivo, junto a los imports existentes, agregar:

```python
from dataclasses import dataclass
from app.services.accounting.coa import CODE_ACCOUNTS_PAYABLE, CODE_ACCOUNTS_RECEIVABLE, CODE_CASH_BANK, CODE_CREDIT_CARDS
from app.services.accounting.engine import AccountingError, LineSpec, post_journal_entry
```

(`CODE_ACCOUNTS_PAYABLE`, `CODE_ACCOUNTS_RECEIVABLE`, `CODE_CASH_BANK` y `CODE_CREDIT_CARDS` ya están en el bloque `from app.services.accounting.coa import (...)`: sólo hay que añadir `CODE_CREDIT_CARDS` si falta y cambiar la línea del engine para traer también `AccountingError`.)

Al final del archivo:

```python
# --- Pólizas manuales (C-1) ---

# Cuentas que mantienen un saldo espejo fuera del ledger (instrumentos y
# cartera). Una póliza manual contra ellas descuadraría ese espejo, así que se
# capturan desde su módulo.
MODULE_CONTROLLED_CODES = {
    CODE_CASH_BANK: "Movimientos",
    CODE_CREDIT_CARDS: "Movimientos",
    CODE_ACCOUNTS_RECEIVABLE: "Por cobrar",
    CODE_ACCOUNTS_PAYABLE: "Por pagar",
}

MANUAL_SOURCE = "manual"
MAX_MANUAL_LINES = 100


@dataclass(frozen=True)
class ManualLine:
    """Línea capturada por el contador: la cuenta viene por id, no por código."""

    account_id: str
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    description: str | None = None


def manual_entry(
    db: Session,
    organization_id: str,
    date: date_type,
    description: str,
    lines: list[ManualLine],
    reference: str | None = None,
    created_by: str | None = None,
) -> JournalEntry:
    """Póliza de diario capturada a mano.

    Valida lo propio de una captura manual (fecha, cuentas permitidas) y deja
    al motor lo demás: cuadre, montos, mes cerrado y folio. No hace commit.
    """
    if date > date_type.today():
        raise AccountingError("No se puede asentar una póliza con fecha futura.")
    description = (description or "").strip()
    if not description:
        raise AccountingError("La póliza necesita un concepto.")
    if not 2 <= len(lines) <= MAX_MANUAL_LINES:
        raise AccountingError(f"Una póliza lleva entre 2 y {MAX_MANUAL_LINES} líneas.")

    wanted = {line.account_id for line in lines}
    accounts = {
        account.id: account
        for account in db.query(Account)
        .filter(Account.organization_id == organization_id, Account.id.in_(wanted))
        .all()
    }
    specs: list[LineSpec] = []
    for line in lines:
        account = accounts.get(line.account_id)
        if account is None:
            raise LookupError("Esa cuenta no existe.")
        if not account.active:
            raise AccountingError(f"La cuenta {account.code} está inactiva.")
        if account.parent_id is None:
            raise AccountingError(
                f"Las pólizas van a cuentas de detalle, no a la cuenta mayor {account.code}."
            )
        if account.code in MODULE_CONTROLLED_CODES:
            raise AccountingError(
                f"La cuenta {account.code} la mueven los módulos. Para bancos y tarjetas usa "
                "Movimientos; para cartera, Por cobrar y Por pagar."
            )
        specs.append(
            LineSpec(account.code, debit=line.debit, credit=line.credit, description=line.description)
        )

    entry = post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=specs,
        source_type=MANUAL_SOURCE,
        reference=reference,
        created_by=created_by,
        kind="DIARIO",
    )
    # El reverso la busca por (source_type, source_id) como a cualquier operación.
    entry.source_id = entry.id
    db.flush()
    return entry
```

- [ ] **Step 4: Agregar schemas, helper y endpoint en el router**

Imports (reemplazar las líneas correspondientes):

```python
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from app.models.user import User
from app.security.deps import get_current_org_id, get_current_user, require_role
from app.services.accounting.rules import ManualLine, manual_entry
```

En `JournalEntryRead` agregar dos campos:

```python
    reversed: bool = False
    reversal_of: str | None = None
```

Después de `JournalEntryRead` agregar:

```python
REVERSAL_PREFIX = "reversal:"


def _entries_read(db: Session, entries: list[JournalEntry]) -> list[JournalEntryRead]:
    """Pólizas con sus líneas y su estado de reverso, en dos consultas."""
    entry_ids = [entry.id for entry in entries]
    lines_by_entry: dict[str, list[JournalLineRead]] = {}
    reversed_ids: set[str] = set()
    if entry_ids:
        for line in db.query(JournalEntryLine).filter(JournalEntryLine.journal_entry_id.in_(entry_ids)).all():
            lines_by_entry.setdefault(line.journal_entry_id, []).append(JournalLineRead.model_validate(line))
        reversals = (
            db.query(JournalEntry.reference)
            .filter(JournalEntry.reference.in_([f"{REVERSAL_PREFIX}{entry_id}" for entry_id in entry_ids]))
            .all()
        )
        reversed_ids = {reference[len(REVERSAL_PREFIX):] for (reference,) in reversals}
    items = []
    for entry in entries:
        item = JournalEntryRead.model_validate(entry)
        item.lines = lines_by_entry.get(entry.id, [])
        item.reversed = entry.id in reversed_ids
        if entry.reference and entry.reference.startswith(REVERSAL_PREFIX):
            item.reversal_of = entry.reference[len(REVERSAL_PREFIX):]
        items.append(item)
    return items


def _entry_read(db: Session, entry: JournalEntry) -> JournalEntryRead:
    return _entries_read(db, [entry])[0]
```

Reemplazar en `list_journal_entries` el bloque que arma `lines_by_entry` e `items` (desde `entry_ids = [...]` hasta `items.append(item)`) por:

```python
    items = _entries_read(db, entries)
```

Agregar, después de `list_journal_entries`:

```python
class JournalLineCreate(BaseModel):
    account_id: str = Field(min_length=1)
    debit: Decimal = Field(default=Decimal("0"), ge=0, allow_inf_nan=False)
    credit: Decimal = Field(default=Decimal("0"), ge=0, allow_inf_nan=False)
    description: str | None = Field(default=None, max_length=500)


class JournalEntryCreate(BaseModel):
    date: date_type
    description: str = Field(min_length=1, max_length=500)
    reference: str | None = Field(default=None, max_length=100)
    lines: list[JournalLineCreate] = Field(min_length=2, max_length=100)


@router.post("/journal-entries", response_model=JournalEntryRead, status_code=201)
def create_journal_entry(
    payload: JournalEntryCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
):
    """Póliza de diario capturada a mano. Las reglas viven en rules.manual_entry."""
    try:
        entry = manual_entry(
            db,
            org_id,
            date=payload.date,
            description=payload.description,
            lines=[ManualLine(l.account_id, l.debit, l.credit, l.description) for l in payload.lines],
            reference=payload.reference,
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
    return _entry_read(db, entry)
```

- [ ] **Step 5: Correr las pruebas y ruff**

Run: `source .venv/bin/activate && pytest tests/test_polizas_manuales.py -q && ruff check app tests`
Expected: 11 passed; ruff sin errores.

- [ ] **Step 6: Correr la suite completa**

Run: `pytest -q`
Expected: todo verde (310 + 11).

- [ ] **Step 7: Commit**

```bash
git add app/services/accounting/rules.py app/domains/accounting/router.py tests/test_polizas_manuales.py
git commit -m "feat(contabilidad): pólizas de diario capturadas a mano"
```

---

### Task 2: Regla `reverse_manual_entry` y `POST /api/accounting/journal-entries/{id}/reverse`

**Files:**
- Modify: `app/services/accounting/rules.py` (al final)
- Modify: `app/domains/accounting/router.py` (schema y endpoint después de `create_journal_entry`)
- Test: `tests/test_polizas_manuales.py` (agregar al final)

**Interfaces:**
- Consumes: `reversal_of(db, organization_id, entry, description, date, created_by)` de `rules.py`; `_entry_read` de Task 1.
- Produces: `reverse_manual_entry(db, organization_id, entry, date, description=None, created_by=None) -> JournalEntry`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar al final de `tests/test_polizas_manuales.py`:

```python
def _posted(client, headers, acc, when=None):
    response = _entry(client, headers, [_line(acc["5200"], debit="1000"), _line(acc["3100"], credit="1000")], when=when)
    assert response.status_code == 201, response.text
    return response.json()


def _reverse(client, headers, entry_id, when=None, description=None):
    return client.post(
        f"/api/accounting/journal-entries/{entry_id}/reverse",
        headers=headers,
        json={"date": (when or date.today()).isoformat(), "description": description},
    )


def test_reverse_mirrors_the_lines_once(client):
    headers, acc = _setup(client)
    original = _posted(client, headers, acc)

    response = _reverse(client, headers, original["id"])
    assert response.status_code == 201, response.text
    reversal = response.json()
    assert reversal["reference"] == f"reversal:{original['id']}"
    assert reversal["reversal_of"] == original["id"]
    assert reversal["description"].startswith(f"Reverso de {original['folio']}")
    by_account = {line["account_id"]: line for line in reversal["lines"]}
    assert by_account[acc["5200"]["id"]]["credit"] == "1000.00"
    assert by_account[acc["3100"]["id"]]["debit"] == "1000.00"

    listed = client.get("/api/accounting/journal-entries", headers=headers).json()["items"]
    assert next(item for item in listed if item["id"] == original["id"])["reversed"] is True

    again = _reverse(client, headers, original["id"])
    assert again.status_code == 400
    assert "ya fue revertida" in again.json()["detail"]

    nested = _reverse(client, headers, reversal["id"])
    assert nested.status_code == 400
    assert "no se revierte" in nested.json()["detail"]


def test_reverse_keeps_custom_description_and_rejects_earlier_dates(client):
    headers, acc = _setup(client)
    original = _posted(client, headers, acc)
    earlier = _reverse(client, headers, original["id"], when=date.today() - timedelta(days=1))
    assert earlier.status_code == 400
    assert "anterior" in earlier.json()["detail"]
    custom = _reverse(client, headers, original["id"], description="Se duplicó la provisión")
    assert custom.status_code == 201
    assert custom.json()["description"] == "Se duplicó la provisión"


def test_reverse_into_closed_month_leaves_original_untouched(client):
    headers, acc = _setup(client)
    end = date.today().replace(day=1) - timedelta(days=1)
    original = _posted(client, headers, acc, when=end)
    assert client.post("/api/periods/close", headers=headers, json={"year": end.year, "month": end.month}).status_code == 200
    response = _reverse(client, headers, original["id"], when=end)
    assert response.status_code == 400
    assert "cerrado" in response.json()["detail"]
    listed = client.get("/api/accounting/journal-entries", headers=headers).json()["items"]
    assert next(item for item in listed if item["id"] == original["id"])["reversed"] is False


def test_operation_entries_are_reversed_from_their_module(client):
    headers, acc = _setup(client)
    account = client.get("/api/accounts", headers=headers).json()[0]
    ventas = next(
        c for c in client.get("/api/categories?kind=INCOME", headers=headers).json() if c["name"] == "Ventas"
    )
    income = client.post(
        "/api/income",
        headers=headers,
        json={
            "date": date.today().isoformat(),
            "description": "Venta",
            "amount": "5000",
            "category_id": ventas["id"],
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    assert income.status_code == 201, income.text
    entry = client.get(
        "/api/accounting/journal-entries",
        headers=headers,
        params={"source_type": "income", "source_id": income.json()["id"]},
    ).json()["items"][0]
    response = _reverse(client, headers, entry["id"])
    assert response.status_code == 400
    assert "operación" in response.json()["detail"]


def test_other_company_cannot_reverse(client):
    headers, acc = _setup(client)
    original = _posted(client, headers, acc)
    other_headers, _ = _setup(client, email="otra@example.com")
    assert _reverse(client, other_headers, original["id"]).status_code == 404
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `pytest tests/test_polizas_manuales.py -q -k reverse`
Expected: FAIL con 404/405.

- [ ] **Step 3: Agregar la regla en `rules.py`**

Al final del archivo:

```python
def reverse_manual_entry(
    db: Session,
    organization_id: str,
    entry: JournalEntry,
    date: date_type,
    description: str | None = None,
    created_by: str | None = None,
) -> JournalEntry:
    """Reverso de una póliza manual: espejo, una sola vez, nunca sobre un reverso."""
    if entry.source_type != MANUAL_SOURCE:
        raise AccountingError("Esta póliza nació de una operación; cancélala desde su módulo.")
    if entry.reference and entry.reference.startswith("reversal:"):
        raise AccountingError("Un reverso no se revierte; captura una póliza nueva.")
    if entry.status != "POSTED":
        raise AccountingError("Esta póliza no está contabilizada.")
    if date < entry.date:
        raise AccountingError("El reverso no puede ser anterior a la póliza original.")
    if date > date_type.today():
        raise AccountingError("No se puede asentar una póliza con fecha futura.")
    already = (
        db.query(JournalEntry.id)
        .filter(JournalEntry.organization_id == organization_id, JournalEntry.reference == f"reversal:{entry.id}")
        .first()
    )
    if already is not None:
        raise AccountingError("Esta póliza ya fue revertida.")
    text = (description or "").strip() or f"Reverso de {entry.folio}: {entry.description}"
    return reversal_of(db, organization_id, entry, text[:500], date, created_by=created_by)
```

- [ ] **Step 4: Agregar schema y endpoint en el router**

Import: añadir `reverse_manual_entry` a `from app.services.accounting.rules import ManualLine, manual_entry`.

Después de `create_journal_entry`:

```python
class ReverseRequest(BaseModel):
    date: date_type
    description: str | None = Field(default=None, max_length=500)


@router.post("/journal-entries/{entry_id}/reverse", response_model=JournalEntryRead, status_code=201)
def reverse_journal_entry(
    entry_id: str,
    payload: ReverseRequest,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
):
    """Deshacer es revertir: la póliza espejo se emite y la original queda."""
    entry = (
        db.query(JournalEntry).filter(JournalEntry.id == entry_id, JournalEntry.organization_id == org_id).first()
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Esa póliza no existe.")
    try:
        reversal = reverse_manual_entry(
            db, org_id, entry, date=payload.date, description=payload.description, created_by=user.id
        )
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error
    db.commit()
    db.refresh(reversal)
    return _entry_read(db, reversal)
```

- [ ] **Step 5: Correr las pruebas, ruff y la suite**

Run: `pytest tests/test_polizas_manuales.py -q && ruff check app tests && pytest -q`
Expected: 16 passed en el archivo; suite verde.

- [ ] **Step 6: Commit**

```bash
git add app/services/accounting/rules.py app/domains/accounting/router.py tests/test_polizas_manuales.py
git commit -m "feat(contabilidad): reverso de pólizas manuales, una sola vez"
```

---

### Task 3: Catálogo editable: alta, renombrar, desactivar, `has_movements`

**Files:**
- Modify: `app/services/accounting/coa.py` (imports y funciones al final)
- Modify: `app/domains/accounting/router.py` (`AccountRead`, `list_accounts`, `AccountUpdate`, `update_account`, nuevo `create_account`)
- Test: `tests/test_catalogo.py`

**Interfaces:**
- Consumes: `sat_code_names()` de `sat.py`; `Account`, `JournalEntryLine`.
- Produces en `coa.py` (y `AccountRead.system: bool` en el router): `CatalogError(ValueError)`, `validate_detail_code(code, parent_code) -> str`, `create_account(db, organization_id, parent_id, code, name, sat_code=None, contpaqi_code=None) -> Account` (lanza `LookupError` si el padre no es de la empresa), `rename_account(account, name) -> Account`, `set_account_active(db, account, active) -> Account`, `account_has_movements(db, account_id) -> bool`, `accounts_with_movements(db, organization_id) -> set[str]`. En el router: `AccountRead.has_movements: bool`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_catalogo.py`:

```python
"""Catálogo editable: cuentas de detalle bajo una mayor, dos niveles, sin borrar nada."""

from datetime import date
from decimal import Decimal

from tests.helpers import auth_headers, register


def _setup(client, email="contador@example.com"):
    body = register(client, email=email, initial_cash="50000")
    headers = auth_headers(body)
    accounts = client.get("/api/accounting/accounts", headers=headers).json()
    return headers, {account["code"]: account for account in accounts}


def _create(client, headers, parent, code="5210", name="Cuotas patronales", **extra):
    return client.post(
        "/api/accounting/accounts",
        headers=headers,
        json={"parent_id": parent["id"], "code": code, "name": name, **extra},
    )


def _manual(client, headers, debit_account, credit_account, amount="100"):
    return client.post(
        "/api/accounting/journal-entries",
        headers=headers,
        json={
            "date": date.today().isoformat(),
            "description": "Ajuste",
            "lines": [
                {"account_id": debit_account["id"], "debit": amount, "credit": "0"},
                {"account_id": credit_account["id"], "debit": "0", "credit": amount},
            ],
        },
    )


def test_create_detail_account_inherits_type_and_sat_code(client):
    headers, acc = _setup(client)
    response = _create(client, headers, acc["5000"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["type"] == "EXPENSE"
    assert body["parent_id"] == acc["5000"]["id"]
    assert body["active"] is True
    assert body["has_movements"] is False
    assert body["sat_code"] == acc["5000"]["sat_code"]
    listed = client.get("/api/accounting/accounts", headers=headers).json()
    assert any(item["code"] == "5210" for item in listed)


def test_create_with_explicit_sat_and_contpaqi_codes(client):
    headers, acc = _setup(client)
    response = _create(client, headers, acc["5000"], sat_code="601.01", contpaqi_code="5210-000-000")
    assert response.status_code == 201, response.text
    assert response.json()["sat_code"] == "601.01"
    assert response.json()["contpaqi_code"] == "5210000000"
    bad = _create(client, headers, acc["5000"], code="5211", sat_code="999.99")
    assert bad.status_code == 400


def test_code_rules(client):
    headers, acc = _setup(client)
    assert _create(client, headers, acc["5000"], code="5200").status_code == 400  # duplicado
    assert _create(client, headers, acc["5000"], code="52A0").status_code == 400  # letras
    assert _create(client, headers, acc["5000"], code="520").status_code == 422  # corto (schema)
    assert _create(client, headers, acc["5000"], code="4210").status_code == 400  # dígito del padre
    assert _create(client, headers, acc["5000"], code=" 05210 ").status_code == 400  # ceros a la izquierda
    assert _create(client, headers, acc["5000"], code="5210000000").status_code == 201  # 10 dígitos


def test_parent_must_be_a_major_account_of_this_company(client):
    headers, acc = _setup(client)
    assert _create(client, headers, acc["5200"]).status_code == 400
    other_headers, other_acc = _setup(client, email="otra@example.com")
    assert _create(client, headers, other_acc["5000"]).status_code == 404


def test_rename_any_account(client):
    headers, acc = _setup(client)
    response = client.patch(
        f"/api/accounting/accounts/{acc['5400']['id']}", headers=headers, json={"name": "Sistemas y licencias"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Sistemas y licencias"
    blank = client.patch(f"/api/accounting/accounts/{acc['5400']['id']}", headers=headers, json={"name": "   "})
    assert blank.status_code == 400


def test_deactivate_rules(client):
    headers, acc = _setup(client)
    seeded = client.patch(f"/api/accounting/accounts/{acc['5400']['id']}", headers=headers, json={"active": False})
    assert seeded.status_code == 400
    assert "sembró" in seeded.json()["detail"]

    new = _create(client, headers, acc["5000"]).json()
    off = client.patch(f"/api/accounting/accounts/{new['id']}", headers=headers, json={"active": False})
    assert off.status_code == 200
    assert off.json()["active"] is False
    rejected = _manual(client, headers, new, acc["3100"])
    assert rejected.status_code == 400
    assert "inactiva" in rejected.json()["detail"]

    on = client.patch(f"/api/accounting/accounts/{new['id']}", headers=headers, json={"active": True})
    assert on.status_code == 200
    assert _manual(client, headers, new, acc["3100"]).status_code == 201

    with_moves = client.patch(f"/api/accounting/accounts/{new['id']}", headers=headers, json={"active": False})
    assert with_moves.status_code == 400
    assert "movimientos" in with_moves.json()["detail"]
    listed = client.get("/api/accounting/accounts", headers=headers).json()
    assert next(item for item in listed if item["id"] == new["id"])["has_movements"] is True


def test_new_account_reaches_balance_sat_and_contpaqi(client):
    headers, acc = _setup(client)
    new = _create(client, headers, acc["5000"], contpaqi_code="5210000").json()
    assert _manual(client, headers, new, acc["3100"]).status_code == 201
    today = date.today()

    balance = client.get("/api/accounting/trial-balance", headers=headers).json()
    assert any(row["code"] == "5210" and Decimal(str(row["debit"])) == Decimal("100") for row in balance["rows"])

    assert client.patch("/api/organizations/current", headers=headers, json={"tax_id": "DCV150604MN2"}).status_code == 200
    catalog = client.get(
        "/api/accounting/sat/catalogo", headers=headers, params={"year": today.year, "month": today.month}
    )
    assert catalog.status_code == 200, catalog.text
    assert 'NumCta="5210"' in catalog.text

    export = client.get("/api/accounting/contpaqi", headers=headers, params={"year": today.year, "month": today.month})
    assert export.status_code == 200, export.text
    assert "5210000" in export.text
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `pytest tests/test_catalogo.py -q`
Expected: FAIL (405 en POST, `has_movements` ausente, `name` ignorado).

- [ ] **Step 3: Agregar las funciones en `coa.py`**

Imports: `from app.models.accounting import Account, JournalEntryLine`.

Al final del archivo:

```python
# --- Catálogo editable (C-1) ---


class CatalogError(ValueError):
    """Regla del catálogo violada. Mensaje apto para el usuario."""


def validate_detail_code(code: str, parent_code: str) -> str:
    """Sólo dígitos, de 4 a 10, y el primero igual al de la cuenta mayor."""
    code = (code or "").strip()
    if not (code.isascii() and code.isdigit()) or not 4 <= len(code) <= 10:
        raise CatalogError("El código de la cuenta lleva sólo dígitos, de 4 a 10.")
    if code[0] != parent_code[0]:
        raise CatalogError(f"Una cuenta bajo {parent_code} debe empezar con {parent_code[0]}.")
    return code


def create_account(
    db: Session,
    organization_id: str,
    parent_id: str,
    code: str,
    name: str,
    sat_code: str | None = None,
    contpaqi_code: str | None = None,
) -> Account:
    """Cuenta de detalle bajo una mayor. El tipo se hereda; el código SAT también si no viene. No hace commit."""
    parent = db.query(Account).filter(Account.id == parent_id, Account.organization_id == organization_id).first()
    if parent is None:
        raise LookupError("Esa cuenta mayor no existe.")
    if parent.parent_id is not None:
        raise CatalogError(
            f"{parent.code} no es una cuenta mayor; las cuentas nuevas van bajo 1000, 2000, 3000, 4000 o 5000."
        )
    code = validate_detail_code(code, parent.code)
    name = (name or "").strip()
    if not 1 <= len(name) <= 255:
        raise CatalogError("La cuenta necesita un nombre.")
    taken = db.query(Account.id).filter(Account.organization_id == organization_id, Account.code == code).first()
    if taken is not None:
        raise CatalogError(f"Ya existe la cuenta {code}.")
    account = Account(
        organization_id=organization_id,
        code=code,
        name=name,
        type=parent.type,
        parent_id=parent.id,
        active=True,
        system=False,
        sat_code=sat_code or parent.sat_code,
        contpaqi_code=contpaqi_code,
    )
    db.add(account)
    db.flush()
    return account


def rename_account(account: Account, name: str) -> Account:
    name = (name or "").strip()
    if not 1 <= len(name) <= 255:
        raise CatalogError("La cuenta necesita un nombre.")
    account.name = name
    return account


def account_has_movements(db: Session, account_id: str) -> bool:
    return db.query(JournalEntryLine.id).filter(JournalEntryLine.account_id == account_id).first() is not None


def accounts_with_movements(db: Session, organization_id: str) -> set[str]:
    """Ids de las cuentas de la empresa con al menos una línea en el ledger (una consulta)."""
    rows = (
        db.query(JournalEntryLine.account_id)
        .join(Account, Account.id == JournalEntryLine.account_id)
        .filter(Account.organization_id == organization_id)
        .distinct()
        .all()
    )
    return {account_id for (account_id,) in rows}


def set_account_active(db: Session, account: Account, active: bool) -> Account:
    """Reactivar siempre; desactivar sólo cuentas propias sin movimientos (las sembradas las usan las reglas)."""
    if active:
        account.active = True
        return account
    if account.system:
        raise CatalogError("Las cuentas que ARCA sembró no se desactivan.")
    if account_has_movements(db, account.id):
        raise CatalogError(f"La cuenta {account.code} tiene movimientos; no se puede desactivar.")
    account.active = False
    return account
```

- [ ] **Step 4: Cambios en el router**

Import: `from app.services.accounting.coa import accounts_with_movements, create_account as create_catalog_account, rename_account, set_account_active`.

En `AccountRead` agregar `system: bool` (después de `active`) y `has_movements: bool = False`.

Reemplazar `list_accounts` por:

```python
@router.get("/accounts", response_model=list[AccountRead])
def list_accounts(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    accounts = db.query(Account).filter(Account.organization_id == org_id).order_by(Account.code).all()
    with_movements = accounts_with_movements(db, org_id)
    items = []
    for account in accounts:
        item = AccountRead.model_validate(account)
        item.has_movements = account.id in with_movements
        items.append(item)
    return items
```

Extraer de `update_account` la normalización de CONTPAQi a una función de módulo (antes de `AccountUpdate`):

```python
def _normalize_contpaqi_code(raw: str | None) -> str | None:
    # Se guarda como la escribe el layout de CONTPAQi: sin guiones, puntos ni espacios.
    code = re.sub(r"[\s.\-]", "", raw or "")
    if code and not (code.isascii() and code.isalnum()):
        raise HTTPException(status_code=400, detail="El número de cuenta sólo puede llevar letras, números y guiones.")
    if len(code) > 30:
        raise HTTPException(status_code=400, detail="El número de cuenta no puede pasar de 30 caracteres.")
    return code or None


def _validated_sat_code(raw: str | None) -> str | None:
    sat_code = (raw or "").strip()
    if sat_code and sat_code not in sat_code_names():
        raise HTTPException(status_code=400, detail="Ese código agrupador no existe en el catálogo del SAT.")
    return sat_code or None
```

`AccountUpdate` y `update_account` quedan así:

```python
class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    active: bool | None = None
    contpaqi_code: str | None = None
    sat_code: str | None = None


@router.patch("/accounts/{account_id}", response_model=AccountRead)
def update_account(
    account_id: str,
    payload: AccountUpdate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Lo editable de una cuenta: nombre, activa, equivalente en CONTPAQi y código agrupador.
    Sólo cambia lo que viene en el cuerpo; un campo ausente no borra nada."""
    account = db.query(Account).filter(Account.id == account_id, Account.organization_id == org_id).first()
    if account is None:
        raise HTTPException(status_code=404, detail="Esa cuenta no existe.")
    try:
        if "name" in payload.model_fields_set:
            rename_account(account, payload.name or "")
        if "active" in payload.model_fields_set and payload.active is not None:
            set_account_active(db, account, payload.active)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if "contpaqi_code" in payload.model_fields_set:
        account.contpaqi_code = _normalize_contpaqi_code(payload.contpaqi_code)
    if "sat_code" in payload.model_fields_set:
        account.sat_code = _validated_sat_code(payload.sat_code)
    db.commit()
    db.refresh(account)
    item = AccountRead.model_validate(account)
    item.has_movements = account_has_movements(db, account.id)
    return item
```

(Importar también `account_has_movements` de `coa`.)

Agregar después de `update_account`:

```python
class AccountCreate(BaseModel):
    parent_id: str = Field(min_length=1)
    code: str = Field(min_length=4, max_length=12)
    name: str = Field(min_length=1, max_length=255)
    sat_code: str | None = None
    contpaqi_code: str | None = None


@router.post("/accounts", response_model=AccountRead, status_code=201)
def create_account(
    payload: AccountCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Cuenta de detalle nueva bajo una cuenta mayor. El tipo lo fija la mayor."""
    sat_code = _validated_sat_code(payload.sat_code)
    contpaqi_code = _normalize_contpaqi_code(payload.contpaqi_code)
    try:
        account = create_catalog_account(
            db, org_id, payload.parent_id, payload.code, payload.name, sat_code=sat_code, contpaqi_code=contpaqi_code
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    db.commit()
    db.refresh(account)
    return AccountRead.model_validate(account)
```

Nota: `max_length=12` en el schema deja pasar `" 05210 "` para que la regla de `coa.py` responda 400 (ceros a la izquierda), mientras `"520"` cae en 422 por `min_length=4`.

- [ ] **Step 5: Correr las pruebas, ruff y la suite**

Run: `pytest tests/test_catalogo.py tests/test_polizas_manuales.py tests/test_sat_export.py tests/test_contpaqi_export.py -q && ruff check app tests && pytest -q`
Expected: todo verde.

- [ ] **Step 6: Commit**

```bash
git add app/services/accounting/coa.py app/domains/accounting/router.py tests/test_catalogo.py
git commit -m "feat(catalogo): alta, renombrar y desactivar cuentas de detalle"
```

---

### Task 4: Frontend: tipos, `Modal` ancho y formulario de póliza

**Files:**
- Modify: `frontend/src/types/api.ts` (`JournalEntry`, `LedgerAccount`)
- Modify: `frontend/src/components/ui/Modal.tsx` (prop `size`)
- Create: `frontend/src/features/accounting/JournalEntryForm.tsx`
- Modify: `frontend/src/features/accounting/AccountingPage.tsx` (botón, apertura por `?nueva=poliza`, selección de la póliza creada)

**Interfaces:**
- Consumes: `POST /accounting/journal-entries` (Task 1), `LedgerAccount[]` de `accountsQuery`.
- Produces: `JournalEntryForm({ open, onClose, accounts, onCreated })`; `Modal` acepta `size?: 'md' | 'lg'`.

- [ ] **Step 1: Tipos**

En `frontend/src/types/api.ts`, en `JournalEntry` agregar:

```ts
  /** Ya tiene póliza espejo. */
  reversed: boolean
  /** Id de la póliza que este reverso deshace, o null. */
  reversal_of: string | null
```

En `LedgerAccount` agregar:

```ts
  /** La sembró ARCA al crear la empresa; las reglas la usan y no se desactiva. */
  system: boolean
  /** Tiene al menos una línea en el ledger; una cuenta así no se desactiva. */
  has_movements: boolean
```

- [ ] **Step 2: `Modal` con tamaño**

En `Modal.tsx`, agregar `size?: 'md' | 'lg'` a `Props`, desestructurar `size = 'md'` y cambiar la clase del diálogo:

```tsx
        className={`w-full ${size === 'lg' ? 'max-w-3xl' : 'max-w-lg'} rounded-xl bg-surface p-6 shadow-float`}
```

- [ ] **Step 3: Crear `JournalEntryForm.tsx`**

```tsx
/** Captura de una póliza de diario: la rejilla que un contador espera, con
 *  totales vivos y sin botón de guardar hasta que cuadre. El backend vuelve a
 *  validar todo; aquí sólo evitamos viajes inútiles. */

import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { TextInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { formatMoney, today } from '@/lib/format'
import type { JournalEntry, LedgerAccount } from '@/types/api'

/** Cuentas con saldo espejo fuera del ledger: se mueven desde su módulo. */
const MODULE_CONTROLLED = new Set(['1100', '1200', '2100', '2200'])

interface Line {
  account_id: string
  debit: string
  credit: string
  description: string
}

const emptyLine = (): Line => ({ account_id: '', debit: '', credit: '', description: '' })

function toNumber(value: string): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0
}

const cents = (value: number) => Math.round(value * 100) / 100

const cellInput =
  'w-full rounded border border-border bg-surface px-2 py-1.5 text-sm text-ink placeholder:text-muted/50 hover:border-muted/40'

export function JournalEntryForm({
  open,
  onClose,
  accounts,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  accounts: LedgerAccount[]
  onCreated: (entry: JournalEntry) => void
}) {
  const queryClient = useQueryClient()
  const [date, setDate] = useState(today())
  const [description, setDescription] = useState('')
  const [reference, setReference] = useState('')
  const [lines, setLines] = useState<Line[]>([emptyLine(), emptyLine()])
  const [error, setError] = useState<string | null>(null)

  const options = useMemo(
    () => accounts.filter((a) => a.parent_id && a.active && !MODULE_CONTROLLED.has(a.code)),
    [accounts],
  )

  const totalDebit = cents(lines.reduce((sum, line) => sum + toNumber(line.debit), 0))
  const totalCredit = cents(lines.reduce((sum, line) => sum + toNumber(line.credit), 0))
  const difference = cents(totalDebit - totalCredit)
  const filled = lines.filter((line) => line.account_id && (toNumber(line.debit) > 0 || toNumber(line.credit) > 0))
  const canSave = description.trim().length > 0 && filled.length >= 2 && difference === 0 && totalDebit > 0

  function reset() {
    setDate(today())
    setDescription('')
    setReference('')
    setLines([emptyLine(), emptyLine()])
    setError(null)
  }

  const save = useMutation({
    mutationFn: async () =>
      (
        await api.post<JournalEntry>('/accounting/journal-entries', {
          date,
          description: description.trim(),
          reference: reference.trim() || null,
          lines: filled.map((line) => ({
            account_id: line.account_id,
            debit: toNumber(line.debit).toFixed(2),
            credit: toNumber(line.credit).toFixed(2),
            description: line.description.trim() || null,
          })),
        })
      ).data,
    onSuccess: (entry) => {
      void queryClient.invalidateQueries({ queryKey: ['accounting'] })
      reset()
      onCreated(entry)
    },
    onError: (err) => setError(errorMessage(err)),
  })

  function updateLine(index: number, patch: Partial<Line>) {
    setLines((prev) => {
      const next = prev.map((line, i) => (i === index ? { ...line, ...patch } : line))
      // Teclear en la última línea abre otra: capturar diez líneas no debe pedir diez clics.
      if (index === prev.length - 1 && next.length < 100) next.push(emptyLine())
      return next
    })
  }

  function removeLine(index: number) {
    setLines((prev) => (prev.length > 2 ? prev.filter((_, i) => i !== index) : prev))
  }

  function close() {
    reset()
    onClose()
  }

  return (
    <Modal title="Nueva póliza de diario" open={open} onClose={close} size="lg">
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault()
          if (canSave) save.mutate()
        }}
      >
        <div className="grid gap-3 sm:grid-cols-[10rem_1fr_10rem]">
          <TextInput label="Fecha" type="date" value={date} max={today()} onChange={(e) => setDate(e.target.value)} required />
          <TextInput
            label="Concepto"
            value={description}
            maxLength={500}
            placeholder="Provisión de nómina de la 2a quincena"
            onChange={(e) => setDescription(e.target.value)}
            required
          />
          <TextInput
            label="Referencia (opcional)"
            value={reference}
            maxLength={100}
            placeholder="NOM-10"
            onChange={(e) => setReference(e.target.value)}
          />
        </div>

        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-[11px] uppercase tracking-wider text-muted">
                <th className="px-2 py-2 font-semibold">Cuenta</th>
                <th className="w-32 px-2 py-2 text-right font-semibold">Cargo</th>
                <th className="w-32 px-2 py-2 text-right font-semibold">Abono</th>
                <th className="px-2 py-2 font-semibold">Concepto de la línea</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {lines.map((line, index) => (
                <tr key={index}>
                  <td className="px-2 py-1.5">
                    <select
                      aria-label={`Cuenta de la línea ${index + 1}`}
                      className={cellInput}
                      value={line.account_id}
                      onChange={(e) => updateLine(index, { account_id: e.target.value })}
                    >
                      <option value="">Elige una cuenta</option>
                      {options.map((account) => (
                        <option key={account.id} value={account.id}>
                          {account.code} · {account.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      aria-label={`Cargo de la línea ${index + 1}`}
                      className={`${cellInput} figures text-right`}
                      inputMode="decimal"
                      placeholder="0.00"
                      value={line.debit}
                      onChange={(e) => updateLine(index, { debit: e.target.value, credit: e.target.value ? '' : line.credit })}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      aria-label={`Abono de la línea ${index + 1}`}
                      className={`${cellInput} figures text-right`}
                      inputMode="decimal"
                      placeholder="0.00"
                      value={line.credit}
                      onChange={(e) => updateLine(index, { credit: e.target.value, debit: e.target.value ? '' : line.debit })}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      aria-label={`Concepto de la línea ${index + 1}`}
                      className={cellInput}
                      maxLength={500}
                      value={line.description}
                      onChange={(e) => updateLine(index, { description: e.target.value })}
                    />
                  </td>
                  <td className="px-1 py-1.5 text-center">
                    <button
                      type="button"
                      aria-label={`Quitar la línea ${index + 1}`}
                      className="rounded p-1 text-muted hover:bg-surface-2 hover:text-ink disabled:opacity-30"
                      disabled={lines.length <= 2}
                      onClick={() => removeLine(index)}
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-ink/70 font-semibold">
                <td className="px-2 py-2">Totales</td>
                <td className="figures px-2 py-2 text-right">{formatMoney(totalDebit)}</td>
                <td className="figures px-2 py-2 text-right">{formatMoney(totalCredit)}</td>
                <td className="px-2 py-2 text-xs" colSpan={2}>
                  {difference === 0 && totalDebit > 0 ? (
                    <span className="text-pos">cargos = abonos ✓</span>
                  ) : (
                    <span className="text-muted">
                      Diferencia <span className="figures text-neg">{formatMoney(Math.abs(difference))}</span>
                    </span>
                  )}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>

        <div className="flex items-center justify-between gap-3">
          <Button type="button" variant="ghost" onClick={() => setLines((prev) => [...prev, emptyLine()])}>
            + Agregar línea
          </Button>
          <div className="flex items-center gap-3">
            {error ? <p className="text-sm text-neg">{error}</p> : null}
            <Button type="button" variant="secondary" onClick={close}>
              Cancelar
            </Button>
            <Button type="submit" disabled={!canSave || save.isPending}>
              {save.isPending ? 'Guardando…' : 'Guardar póliza'}
            </Button>
          </div>
        </div>
      </form>
    </Modal>
  )
}
```

- [ ] **Step 4: Conectar el formulario en `AccountingPage.tsx`**

Imports nuevos:

```tsx
import { Button } from '@/components/ui/Button'
import { JournalEntryForm } from '@/features/accounting/JournalEntryForm'
```

Dentro de `AccountingPage`, después de `const range = rangeForPeriod(period)`:

```tsx
  // ?nueva=poliza abre el formulario (lo usa la paleta de comandos).
  const newEntryOpen = searchParams.get('nueva') === 'poliza'
  function setNewEntryOpen(open: boolean) {
    const params = new URLSearchParams(searchParams)
    if (open) params.set('nueva', 'poliza')
    else params.delete('nueva')
    setSearchParams(params, { replace: true })
  }
  function selectCreated(entry: JournalEntry) {
    setPeriod('current')
    setOffset(0)
    setSearchParams({ poliza: entry.id }, { replace: true })
  }
```

En el `PageHeader`, cambiar el bloque de controles para que el botón aparezca en la pestaña Diario:

```tsx
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Segmented options={TABS} value={tab} onChange={setTab} />
          <div className="flex items-center gap-2">
            {tab !== 'catalogo' ? (
              <Segmented options={PERIOD_OPTIONS} value={period} onChange={changePeriod} size="sm" />
            ) : null}
            {tab === 'diario' ? (
              <Button onClick={() => setNewEntryOpen(true)}>Nueva póliza</Button>
            ) : null}
          </div>
        </div>
```

Antes del cierre del `<div>` raíz del componente (después del bloque `{tab === 'periodos' ? ... }`):

```tsx
      <JournalEntryForm
        open={newEntryOpen}
        onClose={() => setNewEntryOpen(false)}
        accounts={accountsQuery.data ?? []}
        onCreated={selectCreated}
      />
```

El empty state del diario debe ofrecer el botón: cambiar el `<EmptyState ...>` del diario a:

```tsx
          <EmptyState
            title="Sin pólizas en este periodo"
            message="Cada ingreso, gasto, cobro o pago que registres genera aquí su asiento contable automáticamente. También puedes capturar una póliza de diario a mano."
            action={<Button onClick={() => setNewEntryOpen(true)}>Nueva póliza</Button>}
          />
```

- [ ] **Step 5: Typecheck y build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: sin errores.

- [ ] **Step 6: Prueba manual**

Con backend (`uvicorn app.main:app --reload`) y `npm run dev`, entrar a `/contabilidad`, pulsar "Nueva póliza", capturar 5200 cargo 1000 / 3100 abono 1000 y guardar: la póliza aparece seleccionada en el diario con folio `Dr-`. Probar que con diferencia ≠ 0 el botón queda deshabilitado y que elegir 1100 no es posible (no está en el selector).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/components/ui/Modal.tsx frontend/src/features/accounting/JournalEntryForm.tsx frontend/src/features/accounting/AccountingPage.tsx
git commit -m "feat(contabilidad): formulario de póliza de diario"
```

---

### Task 5: Frontend: revertir desde el detalle y etiquetas de reverso

**Files:**
- Modify: `frontend/src/features/accounting/JournalDiary.tsx`

**Interfaces:**
- Consumes: `POST /accounting/journal-entries/{id}/reverse` (Task 2); campos `reversed`, `reversal_of` (Task 4).

- [ ] **Step 1: Imports y etiqueta**

Agregar imports:

```tsx
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { today } from '@/lib/format'
```

(`formatDate` y `formatMoney` ya se importan de `@/lib/format`; unir en una sola línea.)

En `SOURCE_LABELS` agregar `manual: 'Póliza manual',`.

- [ ] **Step 2: Panel de reverso dentro de `EntryDetail`**

Reemplazar la firma y el inicio de `EntryDetail` por:

```tsx
function EntryDetail({
  entry,
  accountLabel,
  onClose,
  onReversed,
}: {
  entry: JournalEntry
  accountLabel: (id: string) => string
  onClose?: () => void
  onReversed?: (reversal: JournalEntry) => void
}) {
  const queryClient = useQueryClient()
  const [reversing, setReversing] = useState(false)
  const [date, setDate] = useState(today())
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const total = entry.lines.reduce((sum, line) => sum + Number(line.debit), 0)
  const canReverse = entry.source_type === 'manual' && !entry.reversed && !entry.reversal_of

  const reverse = useMutation({
    mutationFn: async () =>
      (
        await api.post<JournalEntry>(`/accounting/journal-entries/${entry.id}/reverse`, {
          date,
          description: reason.trim() || null,
        })
      ).data,
    onSuccess: (reversal) => {
      void queryClient.invalidateQueries({ queryKey: ['accounting'] })
      setReversing(false)
      setReason('')
      setError(null)
      onReversed?.(reversal)
    },
    onError: (err) => setError(errorMessage(err)),
  })
```

En el encabezado del detalle, debajo de la línea con la fecha y el origen, agregar las etiquetas:

```tsx
          {entry.reversed ? (
            <p className="mt-1 text-xs font-medium text-neg">Revertida</p>
          ) : entry.reversal_of ? (
            <p className="mt-1 text-xs font-medium text-muted">Reverso de otra póliza</p>
          ) : null}
```

Después del `</table>` dentro del `<div className="flex-1 overflow-y-auto px-5 py-4">`, agregar:

```tsx
        {canReverse ? (
          <div className="mt-4 border-t border-border pt-3">
            {reversing ? (
              <div className="space-y-2">
                <div className="grid gap-2 sm:grid-cols-[9rem_1fr]">
                  <input
                    type="date"
                    aria-label="Fecha del reverso"
                    className="rounded border border-border bg-surface px-2 py-1.5 text-sm"
                    value={date}
                    min={entry.date}
                    max={today()}
                    onChange={(e) => setDate(e.target.value)}
                  />
                  <input
                    aria-label="Motivo del reverso"
                    className="rounded border border-border bg-surface px-2 py-1.5 text-sm"
                    placeholder={`Reverso de ${entry.folio}`}
                    value={reason}
                    maxLength={500}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </div>
                {error ? <p className="text-xs text-neg">{error}</p> : null}
                <div className="flex justify-end gap-2">
                  <Button variant="ghost" onClick={() => setReversing(false)}>
                    Cancelar
                  </Button>
                  <Button variant="danger" disabled={reverse.isPending} onClick={() => reverse.mutate()}>
                    {reverse.isPending ? 'Revirtiendo…' : 'Confirmar reverso'}
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs text-muted">Deshacer es revertir: la original queda y se emite su espejo.</p>
                <Button variant="secondary" onClick={() => setReversing(true)}>
                  Revertir
                </Button>
              </div>
            )}
          </div>
        ) : null}
```

- [ ] **Step 3: Seleccionar el reverso recién creado**

En `JournalDiary`, pasar `onReversed` a ambos `EntryDetail`:

```tsx
onReversed={(reversal) => select(reversal)}
```

- [ ] **Step 4: Typecheck, build y prueba manual**

Run: `cd frontend && npm run typecheck && npm run build`
Manual: abrir una póliza manual, "Revertir", confirmar: el diario selecciona el reverso, la original muestra "Revertida" y ya no ofrece el botón.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/accounting/JournalDiary.tsx
git commit -m "feat(contabilidad): revertir una póliza manual desde el diario"
```

---

### Task 6: Frontend: catálogo editable (alta, nombre, desactivar, inactivas)

**Files:**
- Create: `frontend/src/features/accounting/AccountForm.tsx`
- Modify: `frontend/src/features/accounting/AccountFieldCell.tsx` (campo `name`, ancho)
- Modify: `frontend/src/features/accounting/AccountingPage.tsx` (pestaña catálogo)

**Interfaces:**
- Consumes: `POST /accounting/accounts`, `PATCH /accounting/accounts/{id}` con `name`/`active` (Task 3); `has_movements` (Task 4).
- Produces: `AccountForm({ open, onClose, majors })`; `AccountFieldCell` acepta `field: 'contpaqi_code' | 'sat_code' | 'name'`.

- [ ] **Step 1: `AccountFieldCell` con nombre**

Cambiar `type Field = 'contpaqi_code' | 'sat_code'` por `type Field = 'contpaqi_code' | 'sat_code' | 'name'` y el `<input>`:

```tsx
        className={`${field === 'name' ? 'w-full min-w-[14rem]' : 'figures w-40'} rounded border border-border bg-surface px-2 py-1 text-sm placeholder:text-muted/50 hover:border-muted/40 disabled:opacity-60`}
        maxLength={field === 'name' ? 255 : 40}
```

El `aria-label` queda igual (`${placeholder} de ${account.code} ${account.name}`).

- [ ] **Step 2: Crear `AccountForm.tsx`**

```tsx
/** Alta de una cuenta de detalle: cuelga de una mayor, que fija el tipo. El
 *  código SAT se hereda de la mayor si no se captura. */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { SelectInput, TextInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import type { LedgerAccount } from '@/types/api'

export function AccountForm({
  open,
  onClose,
  majors,
}: {
  open: boolean
  onClose: () => void
  /** Cuentas mayores (sin padre) de la empresa. */
  majors: LedgerAccount[]
}) {
  const queryClient = useQueryClient()
  const [parentId, setParentId] = useState(majors[0]?.id ?? '')
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [satCode, setSatCode] = useState('')
  const [contpaqiCode, setContpaqiCode] = useState('')
  const [error, setError] = useState<string | null>(null)

  const parent = majors.find((item) => item.id === parentId)

  function reset() {
    setParentId(majors[0]?.id ?? '')
    setCode('')
    setName('')
    setSatCode('')
    setContpaqiCode('')
    setError(null)
  }

  const save = useMutation({
    mutationFn: async () =>
      (
        await api.post<LedgerAccount>('/accounting/accounts', {
          parent_id: parentId,
          code: code.trim(),
          name: name.trim(),
          sat_code: satCode.trim() || null,
          contpaqi_code: contpaqiCode.trim() || null,
        })
      ).data,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['accounting', 'accounts'] })
      reset()
      onClose()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  function close() {
    reset()
    onClose()
  }

  return (
    <Modal title="Nueva cuenta" open={open} onClose={close}>
      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault()
          save.mutate()
        }}
      >
        <SelectInput
          label="Cuenta mayor"
          value={parentId}
          options={majors.map((item) => ({ value: item.id, label: `${item.code} · ${item.name}` }))}
          onChange={(e) => {
            setParentId(e.target.value)
            const major = majors.find((item) => item.id === e.target.value)
            if (major && !code) setCode(major.code.charAt(0))
          }}
          required
        />
        <div className="grid gap-3 sm:grid-cols-[9rem_1fr]">
          <TextInput
            label="Código"
            value={code}
            inputMode="numeric"
            maxLength={10}
            placeholder={parent ? `${parent.code.charAt(0)}210` : '5210'}
            hint={parent ? `Empieza con ${parent.code.charAt(0)}, de 4 a 10 dígitos` : undefined}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
            required
          />
          <TextInput
            label="Nombre"
            value={name}
            maxLength={255}
            placeholder="Cuotas patronales IMSS"
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <TextInput
            label="Código SAT (opcional)"
            value={satCode}
            list="sat-codes"
            placeholder={parent?.sat_code ? `Hereda ${parent.sat_code}` : 'Sin código'}
            onChange={(e) => setSatCode(e.target.value)}
          />
          <TextInput
            label="Cuenta en CONTPAQi (opcional)"
            value={contpaqiCode}
            maxLength={40}
            placeholder="5210-000-000"
            onChange={(e) => setContpaqiCode(e.target.value)}
          />
        </div>
        {error ? <p className="text-sm text-neg">{error}</p> : null}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={close}>
            Cancelar
          </Button>
          <Button type="submit" disabled={save.isPending || !parentId || code.length < 4 || !name.trim()}>
            {save.isPending ? 'Guardando…' : 'Crear cuenta'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
```

- [ ] **Step 3: Pestaña Catálogo en `AccountingPage.tsx`**

Imports: `import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'`, `import { errorMessage } from '@/api/client'` (junto a `api`), `import { AccountForm } from '@/features/accounting/AccountForm'`.

Estado y mutación, junto a los otros `useState`:

```tsx
  const queryClient = useQueryClient()
  const [newAccountOpen, setNewAccountOpen] = useState(false)
  const [showInactive, setShowInactive] = useState(false)
  const toggleActive = useMutation({
    mutationFn: async (account: LedgerAccount) =>
      (await api.patch<LedgerAccount>(`/accounting/accounts/${account.id}`, { active: !account.active })).data,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['accounting', 'accounts'] }),
    onError: (err) => window.alert(errorMessage(err)),
  })
  const majors = useMemo(() => (accountsQuery.data ?? []).filter((account) => !account.parent_id), [accountsQuery.data])
  const catalogRows = useMemo(
    () => (accountsQuery.data ?? []).filter((account) => showInactive || account.active),
    [accountsQuery.data, showInactive],
  )
```

En el encabezado, dentro del `<div className="flex items-center gap-2">` de Task 4, agregar el botón de la pestaña catálogo:

```tsx
            {tab === 'catalogo' ? (
              <>
                <label className="flex items-center gap-1.5 text-xs text-muted">
                  <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
                  Mostrar inactivas
                </label>
                <Button onClick={() => setNewAccountOpen(true)}>Nueva cuenta</Button>
              </>
            ) : null}
```

Reemplazar la tabla del catálogo por:

```tsx
          <Table headers={['Código', 'Cuenta', 'Tipo', 'Código SAT', 'Cuenta en CONTPAQi', '']} secondary={[3, 5]}>
            {catalogRows.map((account) => (
              <tr
                key={account.id}
                className={`${account.parent_id ? '' : 'bg-surface-2/40 font-medium'} ${account.active ? '' : 'text-muted'}`}
              >
                <td className="figures px-4 py-2">{account.code}</td>
                <td className={`px-4 py-1.5 ${account.parent_id ? 'pl-8' : ''}`}>
                  <AccountFieldCell account={account} field="name" placeholder="Nombre" />
                </td>
                {/* El tipo sólo en la cuenta mayor: repetirlo en cada hija es ruido. */}
                <td className="px-4 py-2 text-muted">
                  {account.parent_id ? '' : (ACCOUNT_TYPE_LABELS[account.type] ?? account.type)}
                </td>
                {/* El SAT clasifica todos los niveles; CONTPAQi sólo recibe movimientos. */}
                <td className="px-4 py-1.5">
                  <AccountFieldCell
                    account={account}
                    field="sat_code"
                    placeholder="Sin código SAT"
                    list="sat-codes"
                    caption={satName(account.sat_code)}
                  />
                </td>
                <td className="px-4 py-1.5">
                  {account.parent_id ? (
                    <AccountFieldCell account={account} field="contpaqi_code" placeholder="Sin equivalente" />
                  ) : null}
                </td>
                <td className="px-4 py-1.5 text-right">
                  {account.parent_id && !account.system ? (
                    account.active ? (
                      <Button
                        variant="ghost"
                        disabled={account.has_movements || toggleActive.isPending}
                        title={account.has_movements ? 'Tiene movimientos; no se puede desactivar' : undefined}
                        onClick={() => toggleActive.mutate(account)}
                      >
                        Desactivar
                      </Button>
                    ) : (
                      <Button variant="ghost" disabled={toggleActive.isPending} onClick={() => toggleActive.mutate(account)}>
                        Reactivar
                      </Button>
                    )
                  ) : null}
                </td>
              </tr>
            ))}
          </Table>
```

Montar el modal junto al de póliza:

```tsx
      <AccountForm open={newAccountOpen} onClose={() => setNewAccountOpen(false)} majors={majors} />
```

El `<datalist id="sat-codes">` ya se renderiza en la pestaña catálogo; el modal se monta en la misma pestaña, así que la lista está disponible.

- [ ] **Step 4: Typecheck, build y prueba manual**

Run: `cd frontend && npm run typecheck && npm run build`
Manual: crear 5210 bajo 5000 → aparece con tipo heredado; renombrar en línea; desactivar y reactivar; "Mostrar inactivas" la oculta y la muestra; en "Nueva póliza" la cuenta inactiva no aparece.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/accounting/AccountForm.tsx frontend/src/features/accounting/AccountFieldCell.tsx frontend/src/features/accounting/AccountingPage.tsx
git commit -m "feat(catalogo): alta, nombre y activación de cuentas desde la UI"
```

---

### Task 7: Paleta de comandos, documentación y verificación final

**Files:**
- Modify: `frontend/src/components/ui/CommandPalette.tsx` (array `CREATE`)
- Modify: `docs/MVP_STATUS.md` (sección Done)
- Modify: `AGENTS.md` (una línea en "Reglas para features nuevas")

- [ ] **Step 1: Comando "Nueva póliza"**

En `CREATE`, después de `Traspaso entre cuentas`:

```ts
  { label: 'Nueva póliza de diario', hint: 'Crear', to: '/contabilidad?nueva=poliza', keywords: 'asiento manual contador' },
```

- [ ] **Step 2: Documentación**

En `docs/MVP_STATUS.md`, agregar al final de "Done":

```markdown
- **C-1 Pólizas manuales y catálogo editable** (spec 2026-10-12): `POST /api/accounting/journal-entries` (sólo Diario, cuentas de detalle, nunca 1100/1200/2100/2200), reverso único por `/reverse`, alta de cuentas de detalle bajo una mayor (`POST /api/accounting/accounts`), renombrar y desactivar sin movimientos; UI con formulario de póliza, reverso desde el diario y catálogo editable.
```

y quitar C1 de la lista de "Next" (dejar "C2 apertura y cierre anual, B estados financieros NIF").

En `AGENTS.md`, en "Reglas para features nuevas", agregar:

```markdown
- Las cuentas 1100, 1200, 2100 y 2200 mantienen saldos espejo (instrumentos y cartera): nunca aceptan pólizas manuales; `rules.MODULE_CONTROLLED_CODES` es la lista.
```

- [ ] **Step 3: Verificación completa**

Run: `source .venv/bin/activate && pytest -q && ruff check . && cd frontend && npm run typecheck && npm run build`
Expected: todo verde.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ui/CommandPalette.tsx docs/MVP_STATUS.md AGENTS.md
git commit -m "docs(c1): estado y regla de cuentas controladas por módulos"
```
