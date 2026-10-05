# Puente a CONTPAQi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el contador descargue las pólizas de un mes en el layout de texto de CONTPAQi Contabilidad, con cada cuenta de ARCA traducida a su cuenta en CONTPAQi.

**Architecture:** Una función pura convierte pólizas a renglones de ancho fijo a partir de una tabla declarativa de campos (el formato no está verificado contra el CONTPAQi del contador; ajustarlo es cambiar la tabla). Cada cuenta guarda su equivalente en una columna nueva. Dos endpoints en el dominio de contabilidad: vista previa y archivo. El frontend descarga con la sesión del usuario.

**Tech Stack:** FastAPI + SQLAlchemy 2 + Alembic · pytest · React 18 + TS + TanStack Query v5.

**Spec:** `docs/superpowers/specs/2026-10-05-puente-contpaqi-design.md`

## Global Constraints

- `AGENTS.md`: partida doble, aislamiento por empresa, `Decimal` para dinero (nunca `float`), nunca ORM crudo en respuestas.
- El export no escribe nada: sólo lee pólizas `POSTED` de la empresa activa.
- Archivo: Windows-1252, fin de línea CRLF, campos separados por un espacio, importes con dos decimales y punto.
- Si una póliza no cuadra, el export falla completo (409); nunca un archivo a medias.
- Migración `20261005_01_cuenta_contpaqi.py` con `revision = "20261005_01"`, `down_revision = "20260827_01"`; un solo head; aditiva.
- Endpoints bajo `/api/accounting`, que ya exige `ACCOUNTING_ROLES`. Errores `{"detail": "mensaje en español"}`.
- UI: tokens semánticos de Tailwind, `.figures` para cifras y códigos, copy en español.
- Commits: Conventional Commits en español, con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Rama `feat/puente-contpaqi`. Comandos: `pytest`, `ruff check .`, `cd frontend && npm run typecheck && npm run build`.
- El frontend no tiene runner de pruebas: se verifica con typecheck, build y navegador (Task 5).

## Review Focus

1. **Texto que rompe el ancho fijo:** concepto con salto de línea, tabulador o más largo que el campo; el renglón debe medir siempre lo mismo. Prueba en Task 1.
2. **Carácter fuera de Windows-1252** (emoji, flecha): se sustituye por `?` y el archivo sigue codificable. Prueba en Task 1 y Task 3.
3. **Importe grande o con centavos:** `1234567.80` sale exacto, sin notación científica ni redondeo de `float`. Prueba en Task 1.
4. **Cuenta de otra empresa en el PATCH:** responde 404, no la modifica. Prueba en Task 2.
5. **Mes con pólizas de dos empresas:** sólo salen las de la empresa activa. Prueba en Task 3.

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `app/services/accounting/contpaqi.py` (nuevo) | Tabla del layout y `render` puro |
| `app/models/accounting.py` (modificar) | Columna `Account.contpaqi_code` |
| `alembic/versions/20261005_01_cuenta_contpaqi.py` (nuevo) | Migración |
| `app/domains/accounting/service.py` (nuevo) | Pólizas del mes listas para exportar |
| `app/domains/accounting/router.py` (modificar) | PATCH de cuenta, preview y archivo |
| `tests/test_contpaqi_layout.py`, `tests/test_contpaqi_cuentas.py`, `tests/test_contpaqi_export.py` (nuevos) | Pruebas |
| `frontend/src/lib/download.ts` (nuevo) | Descarga con sesión |
| `frontend/src/features/accounting/ContpaqiCodeCell.tsx` (nuevo) | Celda editable del catálogo |
| `frontend/src/features/accounting/ContpaqiExport.tsx` (nuevo) | Modal de exportación |
| `frontend/src/features/accounting/AccountingPage.tsx`, `PeriodsPanel.tsx` (modificar) | Columna y botón |
| `frontend/src/features/reports/ReportsPage.tsx` (modificar) | "Descargar Excel" con sesión |
| `frontend/src/types/api.ts` (modificar) | `LedgerAccount.contpaqi_code` |

---

### Task 1: Layout de pólizas

**Files:**
- Create: `app/services/accounting/contpaqi.py`
- Test: `tests/test_contpaqi_layout.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `Movement(account: str, debit: Decimal, credit: Decimal, concept: str)` y `Voucher(folio: str, kind: str, date: date, concept: str, movements: tuple[Movement, ...])`, dataclasses congeladas.
  - `render(vouchers: Iterable[Voucher]) -> str` (texto con CRLF); lanza `UnbalancedVoucher(ValueError)`.
  - Constantes `ENCODING = "cp1252"`, `HEADER_WIDTH = 147`, `MOVEMENT_WIDTH = 200`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_contpaqi_layout.py`:

```python
"""Layout de pólizas para CONTPAQi: renglones de ancho fijo, sin base de datos."""

from datetime import date
from decimal import Decimal

import pytest

from app.services.accounting.contpaqi import (
    ENCODING,
    HEADER_WIDTH,
    MOVEMENT_WIDTH,
    Movement,
    UnbalancedVoucher,
    Voucher,
    render,
)


def _voucher(**overrides) -> Voucher:
    params = {
        "folio": "Ig-2010-11-0002",
        "kind": "INGRESO",
        "date": date(2010, 11, 4),
        "concept": "ventas del dia",
        "movements": (
            Movement("1020000", Decimal("5500"), Decimal("0"), "ventas del dia"),
            Movement("4000000", Decimal("0"), Decimal("5000"), "ventas del dia"),
            Movement("2040000", Decimal("0"), Decimal("500"), "ventas del dia"),
        ),
    }
    params.update(overrides)
    return Voucher(**params)


def _lines(text: str) -> list[str]:
    assert text.endswith("\r\n")
    return text[:-2].split("\r\n")


def test_header_matches_the_reference_example():
    header = _lines(render([_voucher()]))[0]
    # Renglón P del ejemplo público del layout, carácter por carácter.
    expected = "P  20101104    1         2 1 0          " + "ventas del dia".ljust(100) + " 11 0 0"
    assert header == expected
    assert len(header) == HEADER_WIDTH


def test_movements_are_fixed_width_with_side_and_amount():
    lines = _lines(render([_voucher()]))
    assert len(lines) == 4
    cargo = lines[1]
    expected = " ".join(
        [
            "M ",
            "1020000".ljust(30),
            "Ig-11-0002",
            "0",
            "5500.00".ljust(20),
            "0".ljust(10),
            "0.0".ljust(20),
            "ventas del dia".ljust(100),
        ]
    )
    assert cargo == expected
    assert all(len(line) == MOVEMENT_WIDTH for line in lines[1:])
    # Los abonos llevan 1 en el tipo de movimiento.
    assert [line[45] for line in lines[1:]] == ["0", "1", "1"]


def test_each_kind_maps_to_its_contpaqi_type():
    def tipo(kind: str) -> str:
        return _lines(render([_voucher(kind=kind)]))[0][12:16].strip()

    assert (tipo("INGRESO"), tipo("EGRESO"), tipo("DIARIO")) == ("1", "2", "3")


def test_an_unbalanced_voucher_stops_the_whole_export():
    broken = _voucher(
        folio="Eg-2026-09-0003",
        movements=(
            Movement("5100", Decimal("100"), Decimal("0"), "x"),
            Movement("1100", Decimal("0"), Decimal("90"), "x"),
        ),
    )
    with pytest.raises(UnbalancedVoucher) as error:
        render([_voucher(), broken])
    assert "Eg-2026-09-0003" in str(error.value)


def test_text_that_would_break_the_fixed_width_is_flattened_and_cut():
    concept = "Renta\nde oficina\tcon salto " + "x" * 200
    lines = _lines(render([_voucher(concept=concept)]))
    assert len(lines[0]) == HEADER_WIDTH
    assert "\n" not in lines[0] and "\t" not in lines[0]
    assert "Renta de oficina con salto" in lines[0]


def test_characters_outside_windows_1252_become_question_marks():
    text = render([_voucher(concept="Café señor Ñandú ✓ →")])
    assert "Café señor Ñandú ? ?" in text
    assert text.encode(ENCODING)  # el archivo completo es codificable


def test_large_amounts_keep_their_cents():
    big = _voucher(
        movements=(
            Movement("1100", Decimal("1234567.80"), Decimal("0"), "x"),
            Movement("4100", Decimal("0"), Decimal("1234567.80"), "x"),
        )
    )
    cargo = _lines(render([big]))[1]
    assert cargo[47:67].strip() == "1234567.80"


def test_a_movement_without_amount_is_skipped():
    voucher = _voucher(
        movements=(
            Movement("1100", Decimal("100"), Decimal("0"), "x"),
            Movement("9999", Decimal("0"), Decimal("0"), "vacío"),
            Movement("4100", Decimal("0"), Decimal("100"), "x"),
        )
    )
    assert len(_lines(render([voucher]))) == 3


def test_no_vouchers_renders_an_empty_file():
    assert render([]) == ""
```

- [ ] **Step 2: Correr y confirmar que fallan**

Run: `pytest tests/test_contpaqi_layout.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.accounting.contpaqi'`.

- [ ] **Step 3: Implementar**

`app/services/accounting/contpaqi.py`:

```python
"""Pólizas en el layout de texto de CONTPAQi Contabilidad ("Cargado de pólizas").

Un renglón P por póliza y un renglón M por movimiento, de ancho fijo y con los
campos separados por un espacio.

OJO: CONTPAQi no publica este formato. Los anchos salen de una referencia
pública de una versión antigua y NO están verificados contra el CONTPAQi de un
contador real (las versiones recientes usan renglones M1). Por eso el layout es
una tabla: ajustarlo a una muestra real ("bajado de pólizas") es editar
HEADER_LAYOUT y MOVEMENT_LAYOUT, no la lógica.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

ENCODING = "cp1252"  # Windows-1252: lo que lee un programa de Windows
NEWLINE = "\r\n"

KIND_CODES = {"INGRESO": "1", "EGRESO": "2", "DIARIO": "3"}
SIDE_DEBIT = "0"
SIDE_CREDIT = "1"
ORIGIN_SYSTEM = "11"


@dataclass(frozen=True)
class Field:
    name: str
    width: int
    align: str = "left"  # left | right


HEADER_LAYOUT = (
    Field("mark", 2),
    Field("date", 8),
    Field("kind", 4, "right"),
    Field("folio", 9, "right"),
    Field("clase", 1),
    Field("diario", 10),
    Field("concept", 100),
    Field("origin", 2, "right"),
    Field("printed", 1),
    Field("adjust", 1),
)
MOVEMENT_LAYOUT = (
    Field("mark", 2),
    Field("account", 30),
    Field("reference", 10),
    Field("side", 1),
    Field("amount", 20),
    Field("diario", 10),
    Field("foreign", 20),
    Field("concept", 100),
)


def _width(layout: tuple[Field, ...]) -> int:
    return sum(field.width for field in layout) + len(layout) - 1


HEADER_WIDTH = _width(HEADER_LAYOUT)
MOVEMENT_WIDTH = _width(MOVEMENT_LAYOUT)


@dataclass(frozen=True)
class Movement:
    account: str
    debit: Decimal
    credit: Decimal
    concept: str


@dataclass(frozen=True)
class Voucher:
    folio: str  # folio de ARCA: Ig-2026-09-0007
    kind: str  # INGRESO | EGRESO | DIARIO
    date: date
    concept: str
    movements: tuple[Movement, ...]


class UnbalancedVoucher(ValueError):
    """Una póliza que no cuadra detiene el export completo."""


def _text(value: str | None) -> str:
    """Una sola línea y sólo caracteres que Windows-1252 puede representar."""
    flat = " ".join((value or "").split())
    return flat.encode(ENCODING, errors="replace").decode(ENCODING)


def _line(layout: tuple[Field, ...], values: dict[str, str]) -> str:
    cells = []
    for field in layout:
        value = _text(values[field.name])[: field.width]
        cells.append(value.rjust(field.width) if field.align == "right" else value.ljust(field.width))
    return " ".join(cells)


def _folio_number(folio: str) -> str:
    """Ig-2026-09-0007 → 7: CONTPAQi quiere el consecutivo, no el folio completo."""
    match = re.search(r"(\d+)$", folio)
    return str(int(match.group(1))) if match else "0"


def _reference(folio: str) -> str:
    """El folio de ARCA sin el año, para que quepa en 10: Ig-2026-09-0007 → Ig-09-0007."""
    parts = folio.split("-")
    return "-".join((parts[0], *parts[2:])) if len(parts) == 4 else folio


def render(vouchers: Iterable[Voucher]) -> str:
    lines: list[str] = []
    for voucher in vouchers:
        debit = sum((m.debit for m in voucher.movements), Decimal("0"))
        credit = sum((m.credit for m in voucher.movements), Decimal("0"))
        if debit != credit:
            raise UnbalancedVoucher(
                f"La póliza {voucher.folio} no cuadra: cargos {debit:.2f}, abonos {credit:.2f}."
            )
        lines.append(
            _line(
                HEADER_LAYOUT,
                {
                    "mark": "P",
                    "date": voucher.date.strftime("%Y%m%d"),
                    "kind": KIND_CODES.get(voucher.kind, KIND_CODES["DIARIO"]),
                    "folio": _folio_number(voucher.folio),
                    "clase": "1",
                    "diario": "0",
                    "concept": voucher.concept,
                    "origin": ORIGIN_SYSTEM,
                    "printed": "0",
                    "adjust": "0",
                },
            )
        )
        reference = _reference(voucher.folio)
        for movement in voucher.movements:
            for side, amount in ((SIDE_DEBIT, movement.debit), (SIDE_CREDIT, movement.credit)):
                if amount <= 0:
                    continue
                lines.append(
                    _line(
                        MOVEMENT_LAYOUT,
                        {
                            "mark": "M",
                            "account": movement.account,
                            "reference": reference,
                            "side": side,
                            "amount": f"{amount:.2f}",
                            "diario": "0",
                            "foreign": "0.0",
                            "concept": movement.concept,
                        },
                    )
                )
    return "".join(line + NEWLINE for line in lines)
```

- [ ] **Step 4: Correr y confirmar que pasan**

Run: `pytest tests/test_contpaqi_layout.py -q && ruff check app/services/accounting/contpaqi.py tests/test_contpaqi_layout.py`
Expected: `9 passed` y `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add app/services/accounting/contpaqi.py tests/test_contpaqi_layout.py
git commit -m "feat(contpaqi): layout de pólizas de ancho fijo como función pura

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Cuenta equivalente en CONTPAQi

**Files:**
- Modify: `app/models/accounting.py` (clase `Account`)
- Create: `alembic/versions/20261005_01_cuenta_contpaqi.py`
- Modify: `app/domains/accounting/router.py`
- Test: `tests/test_contpaqi_cuentas.py`

**Interfaces:**
- Consumes: nada de Task 1.
- Produces:
  - Columna `Account.contpaqi_code` (`String(30)`, nullable).
  - `GET /api/accounting/accounts` incluye `contpaqi_code` (string o null) en cada cuenta.
  - `PATCH /api/accounting/accounts/{account_id}` con `{"contpaqi_code": "101-01-000" | "" | null}` → 200 con la cuenta; 404 si no es de la empresa; 400 si el código no es válido.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_contpaqi_cuentas.py`:

```python
"""Cuenta equivalente: cada cuenta de ARCA sabe cómo se llama en CONTPAQi."""

from tests.helpers import auth_headers, register


def _account(client, headers, code="1100") -> dict:
    return next(a for a in client.get("/api/accounting/accounts", headers=headers).json() if a["code"] == code)


def _patch(client, headers, account_id, value):
    return client.patch(
        f"/api/accounting/accounts/{account_id}", headers=headers, json={"contpaqi_code": value}
    )


def test_accounts_start_without_an_equivalent(client):
    headers = auth_headers(register(client))
    assert _account(client, headers)["contpaqi_code"] is None


def test_the_equivalent_is_stored_without_separators(client):
    headers = auth_headers(register(client))
    account = _account(client, headers)

    response = _patch(client, headers, account["id"], " 101-01-000 ")
    assert response.status_code == 200, response.text
    assert response.json()["contpaqi_code"] == "10101000"
    assert _account(client, headers)["contpaqi_code"] == "10101000"


def test_an_empty_value_clears_the_equivalent(client):
    headers = auth_headers(register(client))
    account = _account(client, headers)
    _patch(client, headers, account["id"], "10101000")

    assert _patch(client, headers, account["id"], "").json()["contpaqi_code"] is None


def test_invalid_codes_are_rejected(client):
    headers = auth_headers(register(client))
    account = _account(client, headers)

    assert _patch(client, headers, account["id"], "101/01*000").status_code == 400
    assert _patch(client, headers, account["id"], "1" * 31).status_code == 400
    assert _account(client, headers)["contpaqi_code"] is None


def test_another_company_cannot_touch_my_accounts(client):
    mine = auth_headers(register(client, email="yo@example.com", business="Mía"))
    theirs = auth_headers(register(client, email="otro@example.com", business="Ajena"))
    account = _account(client, mine)

    assert _patch(client, theirs, account["id"], "999").status_code == 404
    assert _account(client, mine)["contpaqi_code"] is None


def test_a_viewer_cannot_edit_the_catalog(client):
    owner = auth_headers(register(client))
    account = _account(client, owner)
    client.post(
        "/api/organizations/current/members",
        headers=owner,
        json={"email": "mira@example.com", "name": "Mira", "role": "VIEWER", "password": "supersegura123"},
    )
    viewer = auth_headers(
        client.post(
            "/api/auth/login", json={"email": "mira@example.com", "password": "supersegura123"}
        ).json()
    )
    assert _patch(client, viewer, account["id"], "999").status_code == 403
```

- [ ] **Step 2: Correr y confirmar que fallan**

Run: `pytest tests/test_contpaqi_cuentas.py -q`
Expected: FAIL; `KeyError: 'contpaqi_code'` o 405 en el PATCH.

- [ ] **Step 3: Modelo y migración**

En `app/models/accounting.py`, dentro de `class Account`, después de `system = ...`:

```python
    # Número de la misma cuenta en el CONTPAQi del contador (sin guiones). Con
    # esto las pólizas exportadas caen en SU catálogo, no en el de ARCA.
    contpaqi_code = Column(String(30), nullable=True)
```

`alembic/versions/20261005_01_cuenta_contpaqi.py`:

```python
"""cuenta equivalente en CONTPAQi

Revision ID: 20261005_01
Revises: 20260827_01
Create Date: 2026-10-05

`accounts.contpaqi_code`: el número de la misma cuenta en el CONTPAQi del
contador. Nullable: una cuenta sin equivalente se exporta con su código de ARCA.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261005_01"
down_revision = "20260827_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("contpaqi_code", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("accounts", "contpaqi_code")
```

Run: `alembic heads`
Expected: una sola línea, `20261005_01 (head)`.

- [ ] **Step 4: Endpoint**

En `app/domains/accounting/router.py`:

a) Imports: agregar `import re` al inicio; cambiar `from fastapi import APIRouter, Depends, Query` por `from fastapi import APIRouter, Depends, HTTPException, Query`.

b) En `class AccountRead`, después de `active: bool`:

```python
    contpaqi_code: str | None
```

c) Después de la función `list_accounts`:

```python
class AccountUpdate(BaseModel):
    contpaqi_code: str | None = None


@router.patch("/accounts/{account_id}", response_model=AccountRead)
def update_account(
    account_id: str,
    payload: AccountUpdate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Por ahora lo único editable de una cuenta es su equivalente en CONTPAQi."""
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.organization_id == org_id)
        .first()
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Esa cuenta no existe.")

    # Se guarda como la escribe el layout de CONTPAQi: sin guiones, puntos ni espacios.
    code = re.sub(r"[\s.\-]", "", payload.contpaqi_code or "")
    if code and not (code.isascii() and code.isalnum()):
        raise HTTPException(
            status_code=400, detail="El número de cuenta sólo puede llevar letras, números y guiones."
        )
    if len(code) > 30:
        raise HTTPException(
            status_code=400, detail="El número de cuenta no puede pasar de 30 caracteres."
        )
    account.contpaqi_code = code or None
    db.commit()
    db.refresh(account)
    return AccountRead.model_validate(account)
```

- [ ] **Step 5: Correr y confirmar que pasan**

Run: `pytest tests/test_contpaqi_cuentas.py -q && ruff check app tests alembic`
Expected: `6 passed` y `All checks passed!`

- [ ] **Step 6: Suite completa y commit**

Run: `pytest -q`
Expected: todo en verde.

```bash
git add app/models/accounting.py alembic/versions/20261005_01_cuenta_contpaqi.py app/domains/accounting/router.py tests/test_contpaqi_cuentas.py
git commit -m "feat(contpaqi): cuenta equivalente en CONTPAQi por cuenta del catálogo

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Exportación del mes

**Files:**
- Create: `app/domains/accounting/service.py`
- Modify: `app/domains/accounting/router.py`
- Test: `tests/test_contpaqi_export.py`

**Interfaces:**
- Consumes: de Task 1, `Movement`, `Voucher`, `render`, `UnbalancedVoucher`, `ENCODING`, `HEADER_WIDTH`, `MOVEMENT_WIDTH`; de Task 2, `Account.contpaqi_code` y el PATCH.
- Produces:
  - `app.domains.accounting.service.month_vouchers(db, organization_id, year, month) -> tuple[list[Voucher], list[dict]]`; el segundo elemento son las cuentas usadas ese mes sin equivalente: `[{"id", "code", "name"}]`.
  - `GET /api/accounting/contpaqi/preview?year=&month=` → `{"year", "month", "entries": int, "movements": int, "unmapped_accounts": [{"id","code","name"}]}`.
  - `GET /api/accounting/contpaqi?year=&month=` → archivo `text/plain; charset=windows-1252`, `Content-Disposition: attachment; filename="polizas-contpaqi-AAAA-MM.txt"`; 404 sin pólizas; 409 si alguna no cuadra.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_contpaqi_export.py`:

```python
"""Exportación a CONTPAQi: las pólizas del mes, cuadradas y sólo las de la empresa."""

from datetime import date
from decimal import Decimal

from app.models.accounting import JournalEntry, JournalEntryLine
from app.services.accounting.contpaqi import ENCODING, HEADER_WIDTH, MOVEMENT_WIDTH
from tests.helpers import auth_headers, register

TODAY = date.today()
MONTH = {"year": TODAY.year, "month": TODAY.month}


def _setup(client, email="dueno@example.com", business="Mi Changarro"):
    headers = auth_headers(register(client, email=email, business=business, initial_cash="100000"))
    account = client.get("/api/accounts", headers=headers).json()[0]

    def category(kind: str, name: str) -> str:
        rows = client.get(f"/api/categories?kind={kind}", headers=headers).json()
        return next(c["id"] for c in rows if c["name"] == name)

    return headers, account, category


def _income(client, headers, account, category, description="Venta de mostrador", amount="11600"):
    response = client.post(
        "/api/income",
        headers=headers,
        json={
            "date": TODAY.isoformat(),
            "description": description,
            "amount": amount,
            "tax_rate": "0.16",
            "category_id": category("INCOME", "Ventas"),
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    assert response.status_code == 201, response.text


def _expense(client, headers, account, category):
    response = client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": TODAY.isoformat(),
            "description": "Renta del local",
            "amount": "5800",
            "tax_rate": "0.16",
            "category_id": category("EXPENSE", "Renta"),
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    assert response.status_code == 201, response.text


def _export(client, headers, **params):
    return client.get("/api/accounting/contpaqi", headers=headers, params=params or MONTH)


def _vouchers(text: str) -> list[dict]:
    """Parte el archivo en pólizas con sus movimientos, leyendo por posición."""
    vouchers: list[dict] = []
    for line in text.split("\r\n"):
        if not line:
            continue
        if line.startswith("P "):
            assert len(line) == HEADER_WIDTH
            vouchers.append({"kind": line[12:16].strip(), "concept": line[40:140].strip(), "moves": []})
        else:
            assert line.startswith("M ") and len(line) == MOVEMENT_WIDTH
            vouchers[-1]["moves"].append(
                {
                    "account": line[3:33].strip(),
                    "side": line[45],
                    "amount": Decimal(line[47:67].strip()),
                }
            )
    return vouchers


def test_the_file_downloads_with_its_name_and_encoding(client):
    headers, account, category = _setup(client)
    _income(client, headers, account, category)

    response = _export(client, headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/plain")
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="polizas-contpaqi-{TODAY.year}-{TODAY.month:02d}.txt"'
    )
    assert response.content.decode(ENCODING).endswith("\r\n")


def test_every_voucher_of_the_month_goes_out_balanced(client):
    headers, account, category = _setup(client)
    _income(client, headers, account, category)
    _expense(client, headers, account, category)

    vouchers = _vouchers(_export(client, headers).content.decode(ENCODING))
    total = client.get("/api/accounting/journal-entries", headers=headers).json()["total"]
    assert len(vouchers) == total == 3  # saldo inicial + ingreso + gasto
    for voucher in vouchers:
        cargos = sum(m["amount"] for m in voucher["moves"] if m["side"] == "0")
        abonos = sum(m["amount"] for m in voucher["moves"] if m["side"] == "1")
        assert cargos == abonos > 0
    assert sorted(v["kind"] for v in vouchers) == ["1", "2", "3"]


def test_mapped_accounts_use_the_contpaqi_number_and_the_rest_keep_arcas(client):
    headers, account, category = _setup(client)
    _income(client, headers, account, category)
    accounts = client.get("/api/accounting/accounts", headers=headers).json()
    ventas = next(a for a in accounts if a["code"] == "4100")
    client.patch(
        f"/api/accounting/accounts/{ventas['id']}", headers=headers, json={"contpaqi_code": "401-01-000"}
    )

    vouchers = _vouchers(_export(client, headers).content.decode(ENCODING))
    used = {m["account"] for v in vouchers for m in v["moves"]}
    assert "40101000" in used and "4100" not in used
    assert "1100" in used  # sin equivalente: sale con el código de ARCA

    preview = client.get("/api/accounting/contpaqi/preview", headers=headers, params=MONTH).json()
    assert preview["entries"] == len(vouchers)
    assert preview["movements"] == sum(len(v["moves"]) for v in vouchers)
    unmapped = {a["code"] for a in preview["unmapped_accounts"]}
    assert "1100" in unmapped and "4100" not in unmapped


def test_accents_survive_and_unsupported_characters_do_not_break_the_file(client):
    headers, account, category = _setup(client)
    _income(client, headers, account, category, description="Café para el señor Ñandú ✓")

    raw = _export(client, headers).content
    assert "Café para el señor Ñandú ?".encode(ENCODING) in raw


def test_only_the_active_company_goes_out(client):
    mine, my_account, my_category = _setup(client, email="yo@example.com", business="Mía")
    theirs, their_account, their_category = _setup(client, email="otro@example.com", business="Ajena")
    _income(client, mine, my_account, my_category, description="Venta mía")
    _income(client, theirs, their_account, their_category, description="Venta ajena")

    text = _export(client, mine).content.decode(ENCODING)
    assert "Venta mía" in text and "Venta ajena" not in text


def test_a_month_without_vouchers_is_a_404(client):
    headers, _account, _category = _setup(client)
    response = _export(client, headers, year=2001, month=1)
    assert response.status_code == 404
    assert response.json()["detail"] == "No hay pólizas en ese mes."

    preview = client.get(
        "/api/accounting/contpaqi/preview", headers=headers, params={"year": 2001, "month": 1}
    ).json()
    assert (preview["entries"], preview["movements"], preview["unmapped_accounts"]) == (0, 0, [])


def test_an_unbalanced_voucher_blocks_the_whole_file(client, db):
    headers, account, category = _setup(client)
    _income(client, headers, account, category)
    # Se descuadra una póliza a mano: el motor no lo permite, pero el export no confía.
    entry = db.query(JournalEntry).filter(JournalEntry.kind == "INGRESO").one()
    line = (
        db.query(JournalEntryLine)
        .filter(JournalEntryLine.journal_entry_id == entry.id, JournalEntryLine.debit > 0)
        .first()
    )
    line.debit = line.debit + 1
    db.flush()

    response = _export(client, headers)
    assert response.status_code == 409
    assert entry.folio in response.json()["detail"]


def test_a_viewer_cannot_export(client):
    owner, _account, _category = _setup(client)
    client.post(
        "/api/organizations/current/members",
        headers=owner,
        json={"email": "mira@example.com", "name": "Mira", "role": "VIEWER", "password": "supersegura123"},
    )
    viewer = auth_headers(
        client.post(
            "/api/auth/login", json={"email": "mira@example.com", "password": "supersegura123"}
        ).json()
    )
    assert _export(client, viewer).status_code == 403
```

- [ ] **Step 2: Correr y confirmar que fallan**

Run: `pytest tests/test_contpaqi_export.py -q`
Expected: FAIL; 404 en `/api/accounting/contpaqi`.

- [ ] **Step 3: Servicio**

`app/domains/accounting/service.py`:

```python
"""Pólizas del mes listas para exportar. Sólo lectura."""

from __future__ import annotations

from calendar import monthrange
from datetime import date

from sqlalchemy.orm import Session

from app.models.accounting import Account, JournalEntry, JournalEntryLine
from app.services.accounting.contpaqi import Movement, Voucher


def month_vouchers(
    db: Session, organization_id: str, year: int, month: int
) -> tuple[list[Voucher], list[dict]]:
    """Las pólizas contabilizadas del mes, en el orden del libro, y las cuentas
    usadas ese mes que todavía no tienen equivalente en CONTPAQi."""
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])

    entries = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.organization_id == organization_id,
            JournalEntry.status == "POSTED",
            JournalEntry.date >= start,
            JournalEntry.date <= end,
        )
        .order_by(JournalEntry.date, JournalEntry.folio)
        .all()
    )
    if not entries:
        return [], []

    rows = (
        db.query(JournalEntryLine, Account)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .join(Account, Account.id == JournalEntryLine.account_id)
        .filter(
            JournalEntry.organization_id == organization_id,
            JournalEntry.status == "POSTED",
            JournalEntry.date >= start,
            JournalEntry.date <= end,
        )
        .all()
    )
    lines_by_entry: dict[str, list[tuple[JournalEntryLine, Account]]] = {}
    unmapped: dict[str, dict] = {}
    for line, account in rows:
        lines_by_entry.setdefault(line.journal_entry_id, []).append((line, account))
        if not account.contpaqi_code:
            unmapped[account.id] = {"id": account.id, "code": account.code, "name": account.name}

    vouchers = []
    for entry in entries:
        # Las líneas no guardan orden propio: cargos primero y luego por cuenta,
        # como se lee una póliza en papel.
        pairs = sorted(
            lines_by_entry.get(entry.id, []),
            key=lambda pair: (0 if pair[0].debit > 0 else 1, pair[1].code),
        )
        vouchers.append(
            Voucher(
                folio=entry.folio,
                kind=entry.kind,
                date=entry.date,
                concept=entry.description,
                movements=tuple(
                    Movement(
                        account=account.contpaqi_code or account.code,
                        debit=line.debit,
                        credit=line.credit,
                        concept=line.description or entry.description,
                    )
                    for line, account in pairs
                ),
            )
        )
    return vouchers, sorted(unmapped.values(), key=lambda item: item["code"])
```

- [ ] **Step 4: Endpoints**

En `app/domains/accounting/router.py`:

a) Imports: cambiar `from fastapi import APIRouter, Depends, HTTPException, Query` por `from fastapi import APIRouter, Depends, HTTPException, Query, Response`, y agregar:

```python
from app.domains.accounting import service
from app.services.accounting.contpaqi import ENCODING, UnbalancedVoucher, render
```

b) Al final del archivo:

```python
@router.get("/contpaqi/preview")
def contpaqi_preview(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Qué saldría en el archivo, para avisar antes de descargar."""
    vouchers, unmapped = service.month_vouchers(db, org_id, year, month)
    return {
        "year": year,
        "month": month,
        "entries": len(vouchers),
        "movements": sum(
            1 for voucher in vouchers for m in voucher.movements if m.debit > 0 or m.credit > 0
        ),
        "unmapped_accounts": unmapped,
    }


@router.get("/contpaqi")
def contpaqi_export(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Las pólizas del mes en el layout de "Cargado de pólizas" de CONTPAQi."""
    vouchers, _unmapped = service.month_vouchers(db, org_id, year, month)
    if not vouchers:
        raise HTTPException(status_code=404, detail="No hay pólizas en ese mes.")
    try:
        content = render(vouchers)
    except UnbalancedVoucher as error:
        # Nunca un archivo a medias: una póliza descuadrada detiene todo.
        raise HTTPException(status_code=409, detail=str(error)) from error
    return Response(
        content=content.encode(ENCODING),
        media_type="text/plain; charset=windows-1252",
        headers={
            "Content-Disposition": f'attachment; filename="polizas-contpaqi-{year}-{month:02d}.txt"'
        },
    )
```

- [ ] **Step 5: Correr y confirmar que pasan**

Run: `pytest tests/test_contpaqi_export.py tests/test_contpaqi_layout.py tests/test_contpaqi_cuentas.py -q && ruff check app tests`
Expected: `23 passed` y `All checks passed!`

- [ ] **Step 6: Suite completa y commit**

Run: `pytest -q`
Expected: todo en verde.

```bash
git add app/domains/accounting/service.py app/domains/accounting/router.py tests/test_contpaqi_export.py
git commit -m "feat(contpaqi): exportación de las pólizas del mes y vista previa

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Frontend — equivalencias, exportación y descargas con sesión

**Files:**
- Modify: `frontend/src/types/api.ts` (`LedgerAccount`)
- Create: `frontend/src/lib/download.ts`
- Create: `frontend/src/features/accounting/ContpaqiCodeCell.tsx`
- Create: `frontend/src/features/accounting/ContpaqiExport.tsx`
- Modify: `frontend/src/features/accounting/AccountingPage.tsx` (pestaña catálogo)
- Modify: `frontend/src/features/accounting/PeriodsPanel.tsx`
- Modify: `frontend/src/features/reports/ReportsPage.tsx` (botón "Descargar Excel")

**Interfaces:**
- Consumes: `PATCH /api/accounting/accounts/{id}`, `GET /api/accounting/contpaqi/preview`, `GET /api/accounting/contpaqi` (Tasks 2 y 3); `GET /api/reports/{report}/csv` (ya existe).
- Produces: `downloadFile(path, params, fallbackName): Promise<void>` y `downloadErrorMessage(error): Promise<string>` en `@/lib/download`; componentes `ContpaqiCodeCell` y `ContpaqiExport`.

- [ ] **Step 1: Tipo y descarga con sesión**

En `frontend/src/types/api.ts`, dentro de `LedgerAccount`, después de `active: boolean`:

```ts
  /** Número de la misma cuenta en el CONTPAQi del contador, o null. */
  contpaqi_code: string | null
```

`frontend/src/lib/download.ts`:

```ts
import axios from 'axios'
import { api, errorMessage } from '@/api/client'

/** Descarga un archivo del API con la sesión del usuario. Un <a href> a secas
 *  no manda el token (vive en localStorage, no en una cookie) y el backend
 *  responde 401. */
export async function downloadFile(
  path: string,
  params: Record<string, string | number>,
  fallbackName: string,
): Promise<void> {
  const response = await api.get<Blob>(path, { params, responseType: 'blob' })
  const disposition = String(response.headers['content-disposition'] ?? '')
  const name = /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? fallbackName
  const url = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = url
  link.download = name
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

/** Con responseType 'blob' el error del backend también llega como archivo:
 *  hay que leerlo para rescatar el mensaje en español. */
export async function downloadErrorMessage(error: unknown): Promise<string> {
  if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
    try {
      const detail = JSON.parse(await error.response.data.text()).detail
      if (typeof detail === 'string') return detail
    } catch {
      // no era JSON: cae al mensaje genérico
    }
  }
  return errorMessage(error)
}
```

- [ ] **Step 2: Celda editable del catálogo**

`frontend/src/features/accounting/ContpaqiCodeCell.tsx`:

```tsx
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import type { LedgerAccount } from '@/types/api'

/** El número de esta cuenta en el CONTPAQi del contador. Se guarda al salir del
 *  campo o con Enter; vacío quita la equivalencia. */
export function ContpaqiCodeCell({ account }: { account: LedgerAccount }) {
  const queryClient = useQueryClient()
  const saved = account.contpaqi_code ?? ''
  const [value, setValue] = useState(saved)
  const [error, setError] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: async (next: string) =>
      (
        await api.patch<LedgerAccount>(`/accounting/accounts/${account.id}`, {
          contpaqi_code: next,
        })
      ).data,
    onSuccess: (updated) => {
      setValue(updated.contpaqi_code ?? '')
      setError(null)
      void queryClient.invalidateQueries({ queryKey: ['accounting', 'accounts'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  function commit() {
    if (value.trim() !== saved) save.mutate(value.trim())
  }

  return (
    <div>
      <input
        aria-label={`Cuenta en CONTPAQi de ${account.code} ${account.name}`}
        className="figures w-40 rounded border border-border bg-surface px-2 py-1 text-sm placeholder:text-muted/50 hover:border-muted/40 disabled:opacity-60"
        placeholder="Sin equivalente"
        value={value}
        maxLength={40}
        disabled={save.isPending}
        onChange={(event) => setValue(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === 'Enter') event.currentTarget.blur()
          if (event.key === 'Escape') setValue(saved)
        }}
      />
      {error ? <p className="mt-1 text-xs text-neg">{error}</p> : null}
    </div>
  )
}
```

En `frontend/src/features/accounting/AccountingPage.tsx`:

a) Agregar el import `import { ContpaqiCodeCell } from '@/features/accounting/ContpaqiCodeCell'`.

b) Reemplazar `<Table headers={['Código', 'Cuenta', 'Tipo']}>` por `<Table headers={['Código', 'Cuenta', 'Tipo', 'Cuenta en CONTPAQi']}>`.

c) En el renglón del catálogo, después de la celda del tipo (la `<td className="px-4 py-2 text-muted">…</td>`), agregar:

```tsx
              {/* Sólo las cuentas que reciben movimientos necesitan equivalente. */}
              <td className="px-4 py-1.5">
                {account.parent_id ? <ContpaqiCodeCell account={account} /> : null}
              </td>
```

- [ ] **Step 3: Modal de exportación**

`frontend/src/features/accounting/ContpaqiExport.tsx`:

```tsx
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { downloadErrorMessage, downloadFile } from '@/lib/download'

interface Preview {
  entries: number
  movements: number
  unmapped_accounts: { id: string; code: string; name: string }[]
}

/** Exportar las pólizas de un mes para cargarlas en CONTPAQi Contabilidad. */
export function ContpaqiExport({
  period,
  title,
  onClose,
}: {
  period: { year: number; month: number } | null
  title: string
  onClose: () => void
}) {
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const preview = useQuery({
    queryKey: ['accounting', 'contpaqi-preview', period?.year, period?.month],
    queryFn: async () =>
      (
        await api.get<Preview>('/accounting/contpaqi/preview', {
          params: { year: period!.year, month: period!.month },
        })
      ).data,
    enabled: period !== null,
    // Las equivalencias pueden haber cambiado en el catálogo hace un momento.
    staleTime: 0,
  })

  async function download() {
    if (!period) return
    setDownloading(true)
    setError(null)
    try {
      await downloadFile(
        '/accounting/contpaqi',
        { year: period.year, month: period.month },
        'polizas-contpaqi.txt',
      )
    } catch (err) {
      setError(await downloadErrorMessage(err))
    } finally {
      setDownloading(false)
    }
  }

  const data = preview.data
  const unmapped = data?.unmapped_accounts ?? []

  return (
    <Modal
      title={`Pólizas de ${title} para CONTPAQi`}
      open={period !== null}
      onClose={() => {
        setError(null)
        onClose()
      }}
    >
      {preview.isLoading ? (
        <div className="h-24 animate-pulse rounded-lg bg-surface-2" />
      ) : preview.error ? (
        <p className="text-sm text-neg">{errorMessage(preview.error)}</p>
      ) : data ? (
        <div className="space-y-4">
          <p className="text-sm">
            <span className="figures font-semibold">{data.entries}</span>{' '}
            {data.entries === 1 ? 'póliza' : 'pólizas'} ·{' '}
            <span className="figures font-semibold">{data.movements}</span>{' '}
            {data.movements === 1 ? 'movimiento' : 'movimientos'}
          </p>

          {unmapped.length > 0 ? (
            <div className="rounded-lg border border-warn/30 bg-warn/10 p-3 text-sm">
              <p className="font-medium text-warn">
                {unmapped.length === 1
                  ? '1 cuenta sin equivalente en CONTPAQi'
                  : `${unmapped.length} cuentas sin equivalente en CONTPAQi`}
              </p>
              <p className="mt-1 text-muted">
                Saldrán con su código de ARCA. Si en tu CONTPAQi tienen otro número, captúralo en
                el{' '}
                <Link
                  to="/contabilidad?vista=catalogo"
                  className="font-medium text-accent hover:underline"
                  onClick={onClose}
                >
                  catálogo de cuentas
                </Link>
                .
              </p>
              <ul className="figures mt-2 space-y-0.5 text-xs text-muted">
                {unmapped.map((account) => (
                  <li key={account.id}>
                    {account.code} {account.name}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-sm text-pos">Todas las cuentas del mes tienen su equivalente.</p>
          )}

          <p className="text-xs text-muted">
            Archivo de texto para "Cargado de pólizas" de CONTPAQi Contabilidad. Es un formato de
            referencia: haz la primera carga en una empresa de prueba.
          </p>

          {error ? (
            <p role="alert" className="rounded border-l-2 border-neg bg-neg/10 px-3 py-2 text-sm text-neg">
              {error}
            </p>
          ) : null}

          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cerrar
            </Button>
            <Button onClick={() => void download()} disabled={downloading || data.entries === 0}>
              {downloading ? 'Preparando…' : 'Descargar archivo'}
            </Button>
          </div>
        </div>
      ) : null}
    </Modal>
  )
}
```

En `frontend/src/features/accounting/PeriodsPanel.tsx`:

a) Agregar el import `import { ContpaqiExport } from '@/features/accounting/ContpaqiExport'`.

b) Junto a los demás `useState`, agregar:

```tsx
  const [exporting, setExporting] = useState<Period | null>(null)
```

c) Reemplazar la apertura de la última celda del renglón, `<td className="px-4 py-2.5 text-right">`, por:

```tsx
            <td className="whitespace-nowrap px-4 py-2.5 text-right">
              {period.entries > 0 ? (
                <Button
                  variant="ghost"
                  className="mr-1 !px-2 !py-1 text-xs"
                  onClick={() => setExporting(period)}
                >
                  CONTPAQi
                </Button>
              ) : null}
```

d) Justo antes del `<Modal` de reapertura, agregar:

```tsx
      <ContpaqiExport
        period={exporting}
        title={exporting ? monthName(exporting.label) : ''}
        onClose={() => setExporting(null)}
      />

```

- [ ] **Step 4: "Descargar Excel" de Reportes con sesión**

En `frontend/src/features/reports/ReportsPage.tsx`:

a) Agregar el import `import { downloadErrorMessage, downloadFile } from '@/lib/download'`.

b) Reemplazar el enlace

```tsx
              <a
                href={`/api/reports/${CSV_REPORTS[tab]}/csv?start=${start}&end=${end}`}
                className="rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:text-ink"
                download
              >
                Descargar Excel
              </a>
```

por

```tsx
              <button
                type="button"
                onClick={() => {
                  // Con la sesión del usuario: el enlace directo respondía 401.
                  downloadFile(`/reports/${CSV_REPORTS[tab]}/csv`, { start, end }, 'reporte.csv').catch(
                    async (err) => window.alert(await downloadErrorMessage(err)),
                  )
                }}
                className="rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:text-ink"
              >
                Descargar Excel
              </button>
```

- [ ] **Step 5: Verificar**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: sin errores.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/lib/download.ts frontend/src/features/accounting frontend/src/features/reports/ReportsPage.tsx
git commit -m "feat(contpaqi): equivalencias en el catálogo, exportación por mes y descargas con sesión

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Verificación de punta a punta y estado

**Files:**
- Modify: `docs/MVP_STATUS.md`

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: evidencia en navegador y el estado actualizado.

- [ ] **Step 1: Suite, lint, migración y build**

Run: `pytest -q && ruff check . && alembic heads && (cd frontend && npm run typecheck && npm run build)`
Expected: todo en verde; un solo head `20261005_01`.

- [ ] **Step 2: Levantar ARCA local con base desechable y sembrar**

Con `S` como directorio scratchpad:

```bash
rm -f "$S/contpaqi.db"
DATABASE_URL="sqlite:///$S/contpaqi.db" alembic upgrade head
DATABASE_URL="sqlite:///$S/contpaqi.db" uvicorn app.main:app --port 8000 &
python scripts/demo_despacho.py --url http://localhost:8000
```

Expected: la migración `20261005_01` corre sin error y la siembra imprime la cartera.

- [ ] **Step 3: Archivo real por API**

Iniciar sesión como el contador sembrado, pedir `GET /api/accounting/contpaqi?year=<año>&month=<mes anterior>` con la empresa "Ferretería El Tornillo" y revisar: status 200; decodifica en `cp1252`; todos los renglones `P` miden 147 y los `M` 200; cargos = abonos por póliza; los conceptos con acentos ("Compra de mercancía", "Nómina quincenal") llegan intactos. Imprimir los primeros renglones.

- [ ] **Step 4: Navegador**

Con la página puente y el conductor de clics en Edge headless (ver memoria `ui-screenshots-via-windows-edge`):

1. `/contabilidad?vista=catalogo`: aparece la columna "Cuenta en CONTPAQi"; escribir `401-01-000` en la cuenta 4100 y salir del campo deja `40101000`.
2. `/contabilidad?vista=periodos`: el mes anterior muestra el botón "CONTPAQi"; el modal muestra pólizas, movimientos y las cuentas sin equivalente (sin la 4100).
3. "Descargar archivo" y "Descargar Excel" (Reportes) piden el archivo con sesión: interceptando `URL.createObjectURL` se confirma que llega un archivo y no un 401.

- [ ] **Step 5: Estado y commit**

En `docs/MVP_STATUS.md`, después del renglón "Portal de despacho", agregar:

```markdown
- **Puente a CONTPAQi** (spec 2026-10-05): cuenta equivalente por cuenta (`accounts.contpaqi_code`, editable en el catálogo), exportación de las pólizas del mes en el layout de "Cargado de pólizas" (`GET /api/accounting/contpaqi`, vista previa en `/contpaqi/preview`), botón por mes en Cierre de periodo. **Formato de referencia, sin verificar contra un CONTPAQi real**: falta calcarlo de un "bajado de pólizas". "Descargar Excel" de Reportes ya descarga con sesión (respondía 401).
```

```bash
git add docs/MVP_STATUS.md
git commit -m "docs(contpaqi): estado del puente a CONTPAQi

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```
