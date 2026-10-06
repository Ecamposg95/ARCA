# Contabilidad electrónica SAT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el contador descargue, por mes y por empresa, el catálogo de cuentas y la balanza de comprobación en XML 1.3 del Anexo 24, válidos contra los esquemas oficiales y cuadrados con el libro.

**Architecture:** Cada cuenta guarda su código agrupador (columna nueva, con defaults para el catálogo de ARCA). Un módulo puro conoce la lista oficial de códigos, la naturaleza de cada cuenta y genera los dos XML a partir de filas ya calculadas; el servicio de contabilidad calcula saldos y movimientos por cuenta y agrega los padres; el router expone vista previa y descargas. El frontend agrega la columna "Código SAT" al catálogo y un botón "SAT" por mes.

**Tech Stack:** FastAPI + SQLAlchemy 2 + Alembic · `xml.etree` · `xmlschema` (sólo pruebas) · React 18 + TS + TanStack Query v5.

**Spec:** `docs/superpowers/specs/2026-10-06-contabilidad-electronica-design.md`

## Global Constraints

- `AGENTS.md`: `Decimal` para dinero, aislamiento por empresa, nunca ORM crudo en respuestas; los endpoints no escriben pólizas.
- Migración `20261006_01_codigo_agrupador.py`, `revision = "20261006_01"`, `down_revision = "20261005_01"`, un solo head. El relleno de defaults va dentro de la migración con el diccionario copiado (una migración no depende de constantes vivas del código).
- XML en UTF-8 con declaración, namespaces y `xsi:schemaLocation` oficiales; importes con dos decimales; `Mes` con dos dígitos.
- Si la balanza no cuadra (Σ Debe ≠ Σ Haber en cuentas hoja) → 409 y no se entrega archivo.
- Errores `{"detail": "mensaje en español"}` (texto, no objeto): la lista de cuentas sin código la da la vista previa.
- Endpoints bajo `/api/accounting` (ya exige `ACCOUNTING_ROLES`).
- Copy en español; tokens semánticos de Tailwind; `.figures` para códigos.
- Commits en español con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Rama `feat/contabilidad-electronica`.
- Comandos: `pytest`, `ruff check .`, `alembic heads`, `cd frontend && npm run typecheck && npm run build`. Dependencias Python con `uv pip install --python .venv/bin/python`.
- El frontend no tiene runner de pruebas: typecheck, build y navegador (Task 5).

## Review Focus

1. **Cuenta con saldo contrario a su naturaleza** (un banco sobregirado): `SaldoIni`/`SaldoFin` salen negativos y la ecuación por naturaleza sigue cumpliéndose. Prueba en Task 3.
2. **Contra-activo 1490 dentro de 1000 Activo:** el padre resta la depreciación acumulada en vez de sumarla. Prueba en Task 3.
3. **Saldo inicial que viene de meses anteriores:** un movimiento de agosto aparece en `SaldoIni` de septiembre y no en `Debe`/`Haber`. Prueba en Task 3.
4. **Descripción con `&`, `<` o acentos**: el XML sigue siendo válido y el texto se preserva. Prueba en Task 1.
5. **RFC en minúsculas o con espacios** ya guardado: se normaliza al validar, no se rechaza. Prueba en Task 3.

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `app/services/accounting/sat_codes.json` (nuevo) | Lista oficial de códigos agrupadores con nombre |
| `app/services/accounting/sat.py` (nuevo) | Lista, defaults, naturaleza, RFC, generadores XML puros |
| `tests/fixtures/sat/*.xsd` (nuevos) | Esquemas oficiales para validar en pruebas |
| `requirements-dev.txt` (modificar) | `xmlschema` |
| `app/models/accounting.py`, `app/services/accounting/coa.py` (modificar) | Columna `sat_code` y defaults al sembrar |
| `alembic/versions/20261006_01_codigo_agrupador.py` (nuevo) | Columna y relleno |
| `app/domains/accounting/service.py` (modificar) | Filas de catálogo y balanza, requisitos |
| `app/domains/accounting/router.py` (modificar) | PATCH ampliado, `/sat/codes`, `/sat/preview`, `/sat/catalogo`, `/sat/balanza` |
| `tests/test_sat_xml.py`, `tests/test_sat_cuentas.py`, `tests/test_sat_export.py` (nuevos) | Pruebas |
| `frontend/src/features/accounting/AccountFieldCell.tsx` (nuevo, reemplaza `ContpaqiCodeCell.tsx`) | Celda editable genérica del catálogo |
| `frontend/src/features/accounting/SatExport.tsx` (nuevo) | Modal SAT |
| `frontend/src/features/accounting/AccountingPage.tsx`, `PeriodsPanel.tsx`, `frontend/src/types/api.ts` (modificar) | Columna, botón, tipos |

---

### Task 1: Lista oficial y generadores XML puros

**Files:**
- Create: `app/services/accounting/sat_codes.json` (desde el scratchpad `sat/codigos_agrupadores.json`)
- Create: `app/services/accounting/sat.py`
- Create: `tests/fixtures/sat/CatalogoCuentas_1_3.xsd`, `BalanzaComprobacion_1_3.xsd`, `CatalogosParaEsqContE.xsd`
- Modify: `requirements-dev.txt`
- Test: `tests/test_sat_xml.py`

**Interfaces:**
- Consumes: `app.models.accounting.DEBIT_NORMAL_TYPES`.
- Produces:
  - `sat_codes() -> list[dict]` (`{code, name}`), `sat_code_names() -> dict[str, str]`, `DEFAULT_SAT_CODES: dict[str, str]`, `CONTRA_ACCOUNT_CODES: set[str]`.
  - `is_valid_rfc(rfc: str | None) -> bool`, `normalize_rfc(rfc) -> str`, `nature(account_type: str, code: str) -> str` (`"D"`/`"A"`).
  - `CatalogRow(code, name, sat_code, parent_code: str | None, level: int, nature: str)`, `BalanceRow(code, saldo_ini, debe, haber, saldo_fin)` (Decimal).
  - `render_catalogo(rfc, year, month, rows) -> bytes`, `render_balanza(rfc, year, month, tipo, rows, fecha_mod: date | None = None) -> bytes`, `sat_filename(rfc, year, month, kind) -> str` con `kind` en `CT`, `BN`, `BC`.
  - `class SatError(ValueError)`.

- [ ] **Step 1: Datos y fixtures**

```bash
S=/tmp/claude-1000/-mnt-d-Devs-ARCA/b4f6d9ce-cb98-4683-ad12-3aee6215bab1/scratchpad/sat
mkdir -p tests/fixtures/sat
cp "$S/BalanzaComprobacion_1_3.xsd" "$S/CatalogosParaEsqContE.xsd" tests/fixtures/sat/
# El import del catálogo apunta a internet; en las pruebas se resuelve en local.
sed 's#schemaLocation="http://www.sat.gob.mx/esquemas/ContabilidadE/1_3/CatalogosParaEsqContE/CatalogosParaEsqContE.xsd"#schemaLocation="CatalogosParaEsqContE.xsd"#' "$S/CatalogoCuentas_1_3.xsd" > tests/fixtures/sat/CatalogoCuentas_1_3.xsd
python3 - "$S/codigos_agrupadores.json" <<'EOF'
import json, sys
codes = json.load(open(sys.argv[1]))
fixes = {"160": "Otros activos fijos"}  # el PDF del DOF pegó texto ajeno a este renglón
for c in codes:
    if c["code"] in fixes: c["name"] = fixes[c["code"]]
    if len(c["name"]) > 150 or "bytes" in c["name"]: raise SystemExit(f"nombre sospechoso: {c}")
json.dump(codes, open("app/services/accounting/sat_codes.json", "w"), ensure_ascii=False, indent=0)
print(len(codes), "códigos")
EOF
printf 'xmlschema>=3.4\n' >> requirements-dev.txt
uv pip install --python .venv/bin/python -q xmlschema
```

Expected: `1080 códigos`; tres `.xsd` en `tests/fixtures/sat/`.

- [ ] **Step 2: Escribir las pruebas que fallan**

`tests/test_sat_xml.py`:

```python
"""XML del Anexo 24: válidos contra los esquemas oficiales, sin base de datos."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import xmlschema

from app.services.accounting.sat import (
    DEFAULT_SAT_CODES,
    BalanceRow,
    CatalogRow,
    is_valid_rfc,
    nature,
    normalize_rfc,
    render_balanza,
    render_catalogo,
    sat_code_names,
    sat_codes,
    sat_filename,
)

FIXTURES = Path(__file__).parent / "fixtures" / "sat"
CATALOGO_XSD = xmlschema.XMLSchema(str(FIXTURES / "CatalogoCuentas_1_3.xsd"))
BALANZA_XSD = xmlschema.XMLSchema(str(FIXTURES / "BalanzaComprobacion_1_3.xsd"))
RFC = "FET180312AB1"

ROWS = [
    CatalogRow("1000", "Activo", "100", None, 1, "D"),
    CatalogRow("1100", "Caja & Bancos <principal>", "102.01", "1000", 2, "D"),
    CatalogRow("1490", "Depreciación Acumulada", "171.08", "1000", 2, "A"),
]


def test_the_official_list_has_every_code_with_a_name():
    codes = sat_codes()
    assert len(codes) == 1080
    names = sat_code_names()
    assert names["101.01"] == "Caja y efectivo"
    assert names["601.84"] == "Otros gastos generales"
    assert names["160"] == "Otros activos fijos"
    # Los cinco sin nombre en el DOF conservan el código como etiqueta.
    assert sum(1 for c in codes if not c["name"]) <= 5


def test_every_default_exists_in_the_official_list():
    names = sat_code_names()
    assert set(DEFAULT_SAT_CODES.values()) <= set(names)
    assert DEFAULT_SAT_CODES["1100"] == "102.01"
    assert DEFAULT_SAT_CODES["5800"] == "613.08"


def test_nature_follows_the_account_type_except_for_contra_accounts():
    assert nature("ASSET", "1100") == "D"
    assert nature("EXPENSE", "5100") == "D"
    assert nature("LIABILITY", "2100") == "A"
    assert nature("EQUITY", "3100") == "A"
    assert nature("REVENUE", "4100") == "A"
    assert nature("ASSET", "1490") == "A"


def test_rfc_validation_and_normalization():
    assert normalize_rfc(" fet180312ab1 ") == "FET180312AB1"
    assert is_valid_rfc("FET180312AB1")  # moral, 12
    assert is_valid_rfc("GARC850101H23")  # física, 13
    assert is_valid_rfc("ÑAÑ010101AB1")
    assert not is_valid_rfc(None)
    assert not is_valid_rfc("")
    assert not is_valid_rfc("FET18031")
    assert not is_valid_rfc("FET18031-AB1")


def test_catalog_is_valid_against_the_official_schema_and_keeps_special_characters():
    xml = render_catalogo(RFC, 2026, 9, ROWS)
    assert xml.startswith(b"<?xml version='1.0' encoding='UTF-8'?>") or xml.startswith(
        b'<?xml version="1.0" encoding="UTF-8"?>'
    )
    CATALOGO_XSD.validate(xml.decode("utf-8"))
    decoded = CATALOGO_XSD.to_dict(xml.decode("utf-8"))
    assert decoded["@RFC"] == RFC and decoded["@Mes"] == "09" and decoded["@Anio"] == 2026
    cuentas = decoded["catalogocuentas:Ctas"]
    assert cuentas[1]["@Desc"] == "Caja & Bancos <principal>"
    assert cuentas[1]["@SubCtaDe"] == "1000" and cuentas[1]["@Nivel"] == 2
    assert "@SubCtaDe" not in cuentas[0]
    assert cuentas[2]["@Natur"] == "A"


def test_a_long_description_is_cut_to_the_schema_limit():
    rows = [CatalogRow("1000", "x" * 500, "100", None, 1, "D")]
    xml = render_catalogo(RFC, 2026, 9, rows)
    CATALOGO_XSD.validate(xml.decode("utf-8"))
    assert len(CATALOGO_XSD.to_dict(xml.decode("utf-8"))["catalogocuentas:Ctas"][0]["@Desc"]) == 400


def test_an_unknown_grouping_code_is_rejected_by_the_schema():
    rows = [CatalogRow("1000", "Activo", "999.99", None, 1, "D")]
    with pytest.raises(xmlschema.XMLSchemaValidationError):
        CATALOGO_XSD.validate(render_catalogo(RFC, 2026, 9, rows).decode("utf-8"))


def test_balance_is_valid_and_amounts_keep_two_decimals():
    rows = [
        BalanceRow("1100", Decimal("1000"), Decimal("250.5"), Decimal("0"), Decimal("1250.50")),
        BalanceRow("2100", Decimal("-30"), Decimal("0"), Decimal("30"), Decimal("0")),
    ]
    xml = render_balanza(RFC, 2026, 9, "N", rows)
    BALANZA_XSD.validate(xml.decode("utf-8"))
    decoded = BALANZA_XSD.to_dict(xml.decode("utf-8"))
    assert decoded["@TipoEnvio"] == "N" and "@FechaModBal" not in decoded
    first = decoded["BCE:Ctas"][0]
    assert (first["@SaldoIni"], first["@Debe"], first["@SaldoFin"]) == (
        Decimal("1000.00"),
        Decimal("250.50"),
        Decimal("1250.50"),
    )
    assert decoded["BCE:Ctas"][1]["@SaldoIni"] == Decimal("-30.00")


def test_a_complementary_balance_carries_its_modification_date():
    rows = [BalanceRow("1100", Decimal("0"), Decimal("1"), Decimal("1"), Decimal("0"))]
    xml = render_balanza(RFC, 2026, 9, "C", rows, fecha_mod=date(2026, 10, 6))
    BALANZA_XSD.validate(xml.decode("utf-8"))
    assert BALANZA_XSD.to_dict(xml.decode("utf-8"))["@FechaModBal"] == "2026-10-06"


def test_filenames_follow_the_anexo_24_convention():
    assert sat_filename(RFC, 2026, 9, "CT") == "FET180312AB1202609CT.xml"
    assert sat_filename(RFC, 2026, 9, "BN") == "FET180312AB1202609BN.xml"
    assert sat_filename(RFC, 2026, 12, "BC") == "FET180312AB1202612BC.xml"
```

- [ ] **Step 3: Correr y confirmar que fallan**

Run: `pytest tests/test_sat_xml.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.accounting.sat'`.

- [ ] **Step 4: Implementar**

`app/services/accounting/sat.py`:

```python
"""Contabilidad electrónica (Anexo 24 de la RMF): catálogo y balanza en XML 1.3.

Lo que ARCA sabe hacer aquí es producir los dos XML válidos contra los esquemas
oficiales del SAT y cuadrados con el libro. El sello con la e.firma y el envío
al buzón tributario los hace el contador con su herramienta: los XML salen sin
`Sello`, `noCertificado` ni `Certificado` (opcionales en el esquema).

La lista oficial de códigos agrupadores (1,080) viene de la enumeración
`c_CodAgrup` del esquema `CatalogosParaEsqContE.xsd`; los nombres, del Anexo 24
publicado en el DOF el 5 de enero de 2015.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET

from app.models.accounting import DEBIT_NORMAL_TYPES

NS_CATALOGO = "http://www.sat.gob.mx/esquemas/ContabilidadE/1_3/CatalogoCuentas"
NS_BALANZA = "http://www.sat.gob.mx/esquemas/ContabilidadE/1_3/BalanzaComprobacion"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
XSD_CATALOGO = f"{NS_CATALOGO}/CatalogoCuentas_1_3.xsd"
XSD_BALANZA = f"{NS_BALANZA}/BalanzaComprobacion_1_3.xsd"

# Patrón del propio esquema del SAT (t_RFC): 12 posiciones persona moral, 13 física.
RFC_PATTERN = re.compile(r"^[A-ZÑ&]{3,4}[0-9]{2}[0-1][0-9][0-3][0-9][A-Z0-9]?[A-Z0-9]?[0-9A-Z]?$")

# Cuentas de activo con naturaleza acreedora (contra-activos). Hoy sólo una.
CONTRA_ACCOUNT_CODES = {"1490"}

# Código agrupador por defecto para el catálogo que ARCA siembra (coa.DEFAULT_CHART).
# Son defaults razonables para una pyme; el contador los corrige cuenta por cuenta.
DEFAULT_SAT_CODES = {
    "1000": "100",
    "1100": "102.01",
    "1190": "118.01",
    "1191": "119.01",
    "1200": "105.01",
    "1300": "121.01",
    "1400": "160.01",
    "1490": "171.08",
    "2000": "200",
    "2100": "201.01",
    "2190": "208.01",
    "2191": "209.01",
    "2200": "205.06",
    "2300": "202.01",
    "2400": "216.04",
    "2410": "216.10",
    "3000": "300",
    "3100": "301.01",
    "3200": "304.01",
    "4000": "400",
    "4100": "401.01",
    "4200": "401.01",
    "5000": "600",
    "5100": "601.84",
    "5200": "601.01",
    "5300": "601.46",
    "5400": "601.60",
    "5500": "601.61",
    "5600": "601.72",
    "5700": "601.84",
    "5800": "613.08",
    "5900": "701.04",
}

_CODES_PATH = Path(__file__).with_name("sat_codes.json")


class SatError(ValueError):
    """Algo impide entregar un XML fiel: no se entrega nada."""


@lru_cache(maxsize=1)
def sat_codes() -> list[dict]:
    return json.loads(_CODES_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def sat_code_names() -> dict[str, str]:
    return {item["code"]: item["name"] for item in sat_codes()}


def normalize_rfc(rfc: str | None) -> str:
    return "".join((rfc or "").split()).upper()


def is_valid_rfc(rfc: str | None) -> bool:
    value = normalize_rfc(rfc)
    return 12 <= len(value) <= 13 and RFC_PATTERN.match(value) is not None


def nature(account_type: str, code: str) -> str:
    """D deudora, A acreedora. El tipo manda, salvo en los contra-activos."""
    if code in CONTRA_ACCOUNT_CODES:
        return "A"
    return "D" if account_type in DEBIT_NORMAL_TYPES else "A"


@dataclass(frozen=True)
class CatalogRow:
    code: str
    name: str
    sat_code: str
    parent_code: str | None
    level: int
    nature: str


@dataclass(frozen=True)
class BalanceRow:
    code: str
    saldo_ini: Decimal
    debe: Decimal
    haber: Decimal
    saldo_fin: Decimal


def sat_filename(rfc: str, year: int, month: int, kind: str) -> str:
    """Anexo 24: RFC + ejercicio + periodo + clave (CT catálogo, BN/BC balanza)."""
    return f"{rfc}{year:04d}{month:02d}{kind}.xml"


def _money(value: Decimal) -> str:
    return f"{Decimal(value):.2f}"


def _document(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True)


ET.register_namespace("catalogocuentas", NS_CATALOGO)
ET.register_namespace("BCE", NS_BALANZA)
ET.register_namespace("xsi", NS_XSI)


def render_catalogo(rfc: str, year: int, month: int, rows: list[CatalogRow]) -> bytes:
    root = ET.Element(
        f"{{{NS_CATALOGO}}}Catalogo",
        {
            f"{{{NS_XSI}}}schemaLocation": f"{NS_CATALOGO} {XSD_CATALOGO}",
            "Version": "1.3",
            "RFC": rfc,
            "Mes": f"{month:02d}",
            "Anio": str(year),
        },
    )
    for row in rows:
        attrs = {"CodAgrup": row.sat_code, "NumCta": row.code[:100], "Desc": row.name[:400]}
        if row.parent_code:
            attrs["SubCtaDe"] = row.parent_code[:100]
        attrs["Nivel"] = str(row.level)
        attrs["Natur"] = row.nature
        ET.SubElement(root, f"{{{NS_CATALOGO}}}Ctas", attrs)
    return _document(root)


def render_balanza(
    rfc: str,
    year: int,
    month: int,
    tipo: str,
    rows: list[BalanceRow],
    fecha_mod: date | None = None,
) -> bytes:
    attrs = {
        f"{{{NS_XSI}}}schemaLocation": f"{NS_BALANZA} {XSD_BALANZA}",
        "Version": "1.3",
        "RFC": rfc,
        "Mes": f"{month:02d}",
        "Anio": str(year),
        "TipoEnvio": tipo,
    }
    # Una balanza complementaria declara cuándo se modificó la que sustituye.
    if tipo == "C":
        attrs["FechaModBal"] = (fecha_mod or date.today()).isoformat()
    root = ET.Element(f"{{{NS_BALANZA}}}Balanza", attrs)
    for row in rows:
        ET.SubElement(
            root,
            f"{{{NS_BALANZA}}}Ctas",
            {
                "NumCta": row.code[:100],
                "SaldoIni": _money(row.saldo_ini),
                "Debe": _money(row.debe),
                "Haber": _money(row.haber),
                "SaldoFin": _money(row.saldo_fin),
            },
        )
    return _document(root)
```

- [ ] **Step 5: Correr y confirmar que pasan**

Run: `pytest tests/test_sat_xml.py -q && ruff check app tests`
Expected: `10 passed` y `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add app/services/accounting/sat.py app/services/accounting/sat_codes.json tests/fixtures/sat tests/test_sat_xml.py requirements-dev.txt
git commit -m "feat(sat): lista oficial de códigos agrupadores y XML del Anexo 24 como funciones puras

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Código agrupador por cuenta

**Files:**
- Modify: `app/models/accounting.py` (clase `Account`)
- Modify: `app/services/accounting/coa.py` (`seed_chart_of_accounts`)
- Create: `alembic/versions/20261006_01_codigo_agrupador.py`
- Modify: `app/domains/accounting/router.py` (`AccountRead`, `AccountUpdate`, `update_account`, nuevo `/sat/codes`)
- Test: `tests/test_sat_cuentas.py`

**Interfaces:**
- Consumes: de Task 1, `DEFAULT_SAT_CODES`, `sat_code_names`, `sat_codes`.
- Produces:
  - `Account.sat_code` (`String(10)`, nullable); `AccountRead.sat_code`.
  - `PATCH /api/accounting/accounts/{id}` acepta `sat_code` (validado contra la lista; `""` lo quita) y sólo toca los campos presentes en el cuerpo.
  - `GET /api/accounting/sat/codes` → `[{code, name}]`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_sat_cuentas.py`:

```python
"""Código agrupador: cada cuenta de ARCA sabe cómo la clasifica el SAT."""

from tests.helpers import auth_headers, register


def _accounts(client, headers) -> dict[str, dict]:
    return {a["code"]: a for a in client.get("/api/accounting/accounts", headers=headers).json()}


def _patch(client, headers, account_id, **body):
    return client.patch(f"/api/accounting/accounts/{account_id}", headers=headers, json=body)


def test_a_new_company_is_born_with_every_account_classified(client):
    headers = auth_headers(register(client))
    accounts = _accounts(client, headers)
    assert all(account["sat_code"] for account in accounts.values()), [
        a["code"] for a in accounts.values() if not a["sat_code"]
    ]
    assert accounts["1100"]["sat_code"] == "102.01"
    assert accounts["1490"]["sat_code"] == "171.08"
    assert accounts["4000"]["sat_code"] == "400"


def test_the_official_list_is_served_for_the_selector(client):
    headers = auth_headers(register(client))
    codes = client.get("/api/accounting/sat/codes", headers=headers).json()
    assert len(codes) == 1080
    assert {"code": "102.01", "name": "Bancos nacionales"} in codes


def test_the_code_can_be_changed_to_another_official_one(client):
    headers = auth_headers(register(client))
    renta = _accounts(client, headers)["5300"]
    response = _patch(client, headers, renta["id"], sat_code=" 601.45 ")
    assert response.status_code == 200, response.text
    assert response.json()["sat_code"] == "601.45"


def test_an_unofficial_code_is_rejected(client):
    headers = auth_headers(register(client))
    renta = _accounts(client, headers)["5300"]
    response = _patch(client, headers, renta["id"], sat_code="999.99")
    assert response.status_code == 400
    assert "SAT" in response.json()["detail"]
    assert _accounts(client, headers)["5300"]["sat_code"] == "601.46"


def test_an_empty_code_clears_it(client):
    headers = auth_headers(register(client))
    renta = _accounts(client, headers)["5300"]
    assert _patch(client, headers, renta["id"], sat_code="").json()["sat_code"] is None


def test_each_field_is_updated_only_when_sent(client):
    headers = auth_headers(register(client))
    renta = _accounts(client, headers)["5300"]
    _patch(client, headers, renta["id"], contpaqi_code="601-01")

    after_sat = _patch(client, headers, renta["id"], sat_code="601.45").json()
    assert (after_sat["contpaqi_code"], after_sat["sat_code"]) == ("60101", "601.45")

    after_empty = _patch(client, headers, renta["id"]).json()
    assert (after_empty["contpaqi_code"], after_empty["sat_code"]) == ("60101", "601.45")
```

- [ ] **Step 2: Correr y confirmar que fallan**

Run: `pytest tests/test_sat_cuentas.py -q`
Expected: FAIL; `KeyError: 'sat_code'` y 404 en `/sat/codes`.

- [ ] **Step 3: Modelo, sembrado y migración**

En `app/models/accounting.py`, en `class Account`, después de `contpaqi_code = ...`:

```python
    # Código agrupador del SAT (Anexo 24): cómo clasifica el fisco esta cuenta.
    sat_code = Column(String(10), nullable=True)
```

En `app/services/accounting/coa.py`: agregar `from app.services.accounting.sat import DEFAULT_SAT_CODES` y, en `seed_chart_of_accounts`, dentro de `Account(...)` después de `system=True,`:

```python
            sat_code=DEFAULT_SAT_CODES.get(code),
```

`alembic/versions/20261006_01_codigo_agrupador.py`:

```python
"""código agrupador del SAT por cuenta

Revision ID: 20261006_01
Revises: 20261005_01
Create Date: 2026-10-06

`accounts.sat_code`: el código agrupador del Anexo 24. Nullable; se rellena con
los defaults del catálogo de ARCA en las cuentas sembradas por el sistema que
aún no tengan uno. El diccionario va copiado: una migración no depende de
constantes vivas del código.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261006_01"
down_revision = "20261005_01"
branch_labels = None
depends_on = None

DEFAULTS = {
    "1000": "100", "1100": "102.01", "1190": "118.01", "1191": "119.01", "1200": "105.01",
    "1300": "121.01", "1400": "160.01", "1490": "171.08", "2000": "200", "2100": "201.01",
    "2190": "208.01", "2191": "209.01", "2200": "205.06", "2300": "202.01", "2400": "216.04",
    "2410": "216.10", "3000": "300", "3100": "301.01", "3200": "304.01", "4000": "400",
    "4100": "401.01", "4200": "401.01", "5000": "600", "5100": "601.84", "5200": "601.01",
    "5300": "601.46", "5400": "601.60", "5500": "601.61", "5600": "601.72", "5700": "601.84",
    "5800": "613.08", "5900": "701.04",
}  # fmt: skip


def upgrade() -> None:
    op.add_column("accounts", sa.Column("sat_code", sa.String(10), nullable=True))
    accounts = sa.table(
        "accounts",
        sa.column("code", sa.String),
        sa.column("system", sa.Boolean),
        sa.column("sat_code", sa.String),
    )
    for code, sat_code in DEFAULTS.items():
        op.execute(
            accounts.update()
            .where(accounts.c.code == code, accounts.c.system.is_(True), accounts.c.sat_code.is_(None))
            .values(sat_code=sat_code)
        )


def downgrade() -> None:
    op.drop_column("accounts", "sat_code")
```

Run: `alembic heads`
Expected: `20261006_01 (head)`.

- [ ] **Step 4: Endpoints**

En `app/domains/accounting/router.py`:

a) Import: `from app.services.accounting.sat import sat_code_names, sat_codes`.

b) En `AccountRead`, después de `contpaqi_code: str | None`:

```python
    sat_code: str | None
```

c) Reemplazar la clase `AccountUpdate` y la función `update_account` completas por:

```python
class AccountUpdate(BaseModel):
    contpaqi_code: str | None = None
    sat_code: str | None = None


@router.patch("/accounts/{account_id}", response_model=AccountRead)
def update_account(
    account_id: str,
    payload: AccountUpdate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Lo editable de una cuenta: su equivalente en CONTPAQi y su código agrupador.
    Sólo cambia lo que viene en el cuerpo; un campo ausente no borra nada."""
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.organization_id == org_id)
        .first()
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Esa cuenta no existe.")

    if "contpaqi_code" in payload.model_fields_set:
        # Se guarda como la escribe el layout de CONTPAQi: sin guiones, puntos ni espacios.
        code = re.sub(r"[\s.\-]", "", payload.contpaqi_code or "")
        if code and not (code.isascii() and code.isalnum()):
            raise HTTPException(
                status_code=400,
                detail="El número de cuenta sólo puede llevar letras, números y guiones.",
            )
        if len(code) > 30:
            raise HTTPException(
                status_code=400, detail="El número de cuenta no puede pasar de 30 caracteres."
            )
        account.contpaqi_code = code or None

    if "sat_code" in payload.model_fields_set:
        sat_code = (payload.sat_code or "").strip()
        if sat_code and sat_code not in sat_code_names():
            raise HTTPException(
                status_code=400, detail="Ese código agrupador no existe en el catálogo del SAT."
            )
        account.sat_code = sat_code or None

    db.commit()
    db.refresh(account)
    return AccountRead.model_validate(account)


@router.get("/sat/codes")
def list_sat_codes():
    """La lista oficial del Anexo 24, para el selector del catálogo."""
    return sat_codes()
```

- [ ] **Step 5: Correr y confirmar que pasan**

Run: `pytest tests/test_sat_cuentas.py tests/test_contpaqi_cuentas.py -q && ruff check app tests alembic`
Expected: `12 passed` y `All checks passed!`

- [ ] **Step 6: Suite completa y commit**

Run: `pytest -q`
Expected: todo en verde.

```bash
git add app/models/accounting.py app/services/accounting/coa.py alembic/versions/20261006_01_codigo_agrupador.py app/domains/accounting/router.py tests/test_sat_cuentas.py
git commit -m "feat(sat): código agrupador por cuenta, con defaults para el catálogo de ARCA

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Catálogo y balanza por mes

**Files:**
- Modify: `app/domains/accounting/service.py`
- Modify: `app/domains/accounting/router.py`
- Test: `tests/test_sat_export.py`

**Interfaces:**
- Consumes: de Task 1, `CatalogRow`, `BalanceRow`, `nature`, `is_valid_rfc`, `normalize_rfc`, `render_catalogo`, `render_balanza`, `sat_filename`, `SatError`; de Task 2, `Account.sat_code`.
- Produces:
  - `service.sat_catalog(db, org_id) -> list[CatalogRow]` (todas las cuentas activas, por código).
  - `service.sat_balance(db, org_id, year, month) -> list[BalanceRow]` (cuentas con algún valor y sus padres; lanza `SatError` si Σ Debe ≠ Σ Haber en hojas).
  - `service.sat_requirements(db, organization, year, month) -> dict` con `rfc`, `rfc_ok`, `accounts`, `missing_accounts: [{id, code, name}]`, `ready`.
  - `GET /api/accounting/sat/preview?year&month`, `GET /api/accounting/sat/catalogo?year&month`, `GET /api/accounting/sat/balanza?year&month&tipo=N|C`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_sat_export.py`:

```python
"""Catálogo y balanza del Anexo 24: válidos, cuadrados con el libro y sólo de la empresa."""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import xmlschema

from tests.helpers import auth_headers, register

FIXTURES = Path(__file__).parent / "fixtures" / "sat"
CATALOGO_XSD = xmlschema.XMLSchema(str(FIXTURES / "CatalogoCuentas_1_3.xsd"))
BALANZA_XSD = xmlschema.XMLSchema(str(FIXTURES / "BalanzaComprobacion_1_3.xsd"))
TODAY = date.today()
MONTH = {"year": TODAY.year, "month": TODAY.month}
LAST_MONTH_END = TODAY.replace(day=1) - timedelta(days=1)


def _setup(client, email="dueno@example.com", business="Mi Changarro", rfc="FET180312AB1"):
    headers = auth_headers(register(client, email=email, business=business, initial_cash="100000"))
    if rfc is not None:
        assert client.patch("/api/organizations/current", headers=headers, json={"tax_id": rfc}).status_code == 200
    account = client.get("/api/accounts", headers=headers).json()[0]

    def category(kind: str, name: str) -> str:
        rows = client.get(f"/api/categories?kind={kind}", headers=headers).json()
        return next(c["id"] for c in rows if c["name"] == name)

    return headers, account, category


def _income(client, headers, account, category, amount="11600", when=None, description="Venta"):
    response = client.post(
        "/api/income",
        headers=headers,
        json={
            "date": (when or TODAY).isoformat(),
            "description": description,
            "amount": amount,
            "tax_rate": "0.16",
            "category_id": category("INCOME", "Ventas"),
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    assert response.status_code == 201, response.text


def _expense(client, headers, account, category, amount="5800", when=None):
    response = client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": (when or TODAY).isoformat(),
            "description": "Renta",
            "amount": amount,
            "tax_rate": "0.16",
            "category_id": category("EXPENSE", "Renta"),
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    assert response.status_code == 201, response.text


def _balanza(client, headers, **params) -> dict:
    response = client.get("/api/accounting/sat/balanza", headers=headers, params=params or MONTH)
    assert response.status_code == 200, response.text
    text = response.content.decode("utf-8")
    BALANZA_XSD.validate(text)
    decoded = BALANZA_XSD.to_dict(text)
    return {row["@NumCta"]: row for row in decoded["BCE:Ctas"]}


def _catalogo(client, headers) -> dict:
    response = client.get("/api/accounting/sat/catalogo", headers=headers, params=MONTH)
    assert response.status_code == 200, response.text
    text = response.content.decode("utf-8")
    CATALOGO_XSD.validate(text)
    return {row["@NumCta"]: row for row in CATALOGO_XSD.to_dict(text)["catalogocuentas:Ctas"]}


def test_catalog_is_valid_and_carries_levels_and_natures(client):
    headers, _account, _category = _setup(client)
    response = client.get("/api/accounting/sat/catalogo", headers=headers, params=MONTH)
    assert response.headers["content-type"].startswith("application/xml")
    expected_name = f'FET180312AB1{TODAY.year}{TODAY.month:02d}CT.xml'
    assert response.headers["content-disposition"] == f'attachment; filename="{expected_name}"'

    rows = _catalogo(client, headers)
    assert rows["1000"]["@Nivel"] == 1 and "@SubCtaDe" not in rows["1000"]
    assert rows["1100"]["@Nivel"] == 2 and rows["1100"]["@SubCtaDe"] == "1000"
    assert rows["1100"]["@CodAgrup"] == "102.01" and rows["1100"]["@Natur"] == "D"
    assert rows["2100"]["@Natur"] == "A" and rows["4100"]["@Natur"] == "A"
    assert rows["1490"]["@Natur"] == "A"  # contra-activo


def test_balance_matches_the_ledger_and_balances_by_nature(client):
    headers, account, category = _setup(client)
    _income(client, headers, account, category)
    _expense(client, headers, account, category)

    rows = _balanza(client, headers)
    trial = {
        r["code"]: r
        for r in client.get("/api/accounting/trial-balance", headers=headers).json()["rows"]
    }
    for code, row in rows.items():
        if code in trial and code != "1490":
            assert row["@SaldoFin"] == Decimal(str(trial[code]["balance"])), code
    leaves = [row for code, row in rows.items() if len(code) == 4 and code[1:] != "000"]
    assert sum(r["@Debe"] for r in leaves) == sum(r["@Haber"] for r in leaves) > 0
    # Ecuación por naturaleza: deudora suma el debe; acreedora suma el haber.
    caja = rows["1100"]
    assert caja["@SaldoFin"] == caja["@SaldoIni"] + caja["@Debe"] - caja["@Haber"]
    ventas = rows["4100"]
    assert ventas["@SaldoFin"] == ventas["@SaldoIni"] - ventas["@Debe"] + ventas["@Haber"]
    assert ventas["@SaldoFin"] == Decimal("10000.00")


def test_parents_add_up_their_children_and_subtract_contra_assets(client, db):
    headers, account, category = _setup(client)
    _income(client, headers, account, category)
    from app.models.accounting import Account, JournalEntry, JournalEntryLine

    # Se simula depreciación acumulada: abono a 1490 contra gasto 5800, dentro del mes.
    org_id = db.query(Account).filter(Account.code == "1490").one().organization_id
    dep = db.query(Account).filter(Account.code == "1490", Account.organization_id == org_id).one()
    gasto = db.query(Account).filter(Account.code == "5800", Account.organization_id == org_id).one()
    entry = JournalEntry(
        organization_id=org_id, folio="Dr-9999-99-0001", kind="DIARIO", date=TODAY,
        description="Depreciación", status="POSTED",
    )
    db.add(entry)
    db.flush()
    db.add(JournalEntryLine(journal_entry_id=entry.id, account_id=gasto.id, debit=Decimal("300"), credit=0))
    db.add(JournalEntryLine(journal_entry_id=entry.id, account_id=dep.id, debit=0, credit=Decimal("300")))
    db.flush()

    rows = _balanza(client, headers)
    assert rows["1490"]["@SaldoFin"] == Decimal("300.00")  # acreedora, positiva en su naturaleza
    # El activo total resta la depreciación acumulada en vez de sumarla.
    expected_asset = sum(
        (-row["@SaldoFin"] if code == "1490" else row["@SaldoFin"])
        for code, row in rows.items()
        if len(code) == 4 and code.startswith("1") and code != "1000"
    )
    assert rows["1000"]["@SaldoFin"] == expected_asset
    assert rows["1000"]["@SaldoFin"] < sum(
        row["@SaldoFin"] for code, row in rows.items() if len(code) == 4 and code.startswith("1") and code != "1000"
    )


def test_last_month_movements_become_this_months_opening_balance(client):
    headers, account, category = _setup(client)
    _income(client, headers, account, category, amount="2320", when=LAST_MONTH_END)
    _income(client, headers, account, category, amount="1160")

    rows = _balanza(client, headers)
    ventas = rows["4100"]
    assert (ventas["@SaldoIni"], ventas["@Haber"], ventas["@SaldoFin"]) == (
        Decimal("2000.00"),
        Decimal("1000.00"),
        Decimal("3000.00"),
    )


def test_an_overdrawn_bank_shows_a_negative_balance_in_its_nature(client):
    headers, account, category = _setup(client)
    # 100,000 en caja; un gasto mayor deja la cuenta en saldo acreedor.
    _expense(client, headers, account, category, amount="150000")

    caja = _balanza(client, headers)["1100"]
    assert caja["@SaldoFin"] == Decimal("-50000.00")
    assert caja["@SaldoFin"] == caja["@SaldoIni"] + caja["@Debe"] - caja["@Haber"]


def test_a_complementary_balance_is_requested_with_tipo_c(client):
    headers, account, category = _setup(client)
    _income(client, headers, account, category)
    response = client.get(
        "/api/accounting/sat/balanza", headers=headers, params={**MONTH, "tipo": "C"}
    )
    assert response.status_code == 200
    text = response.content.decode("utf-8")
    BALANZA_XSD.validate(text)
    decoded = BALANZA_XSD.to_dict(text)
    assert decoded["@TipoEnvio"] == "C" and decoded["@FechaModBal"] == TODAY.isoformat()
    assert response.headers["content-disposition"].endswith('BC.xml"')


def test_preview_and_errors_when_the_company_is_not_ready(client):
    headers, account, category = _setup(client, rfc=None)
    _income(client, headers, account, category)
    renta = next(
        a for a in client.get("/api/accounting/accounts", headers=headers).json() if a["code"] == "5300"
    )
    client.patch(f"/api/accounting/accounts/{renta['id']}", headers=headers, json={"sat_code": ""})

    preview = client.get("/api/accounting/sat/preview", headers=headers, params=MONTH).json()
    assert preview["rfc_ok"] is False and preview["ready"] is False
    assert [a["code"] for a in preview["missing_accounts"]] == ["5300"]

    response = client.get("/api/accounting/sat/catalogo", headers=headers, params=MONTH)
    assert response.status_code == 400
    assert "RFC" in response.json()["detail"]

    client.patch("/api/organizations/current", headers=headers, json={"tax_id": "fet180312ab1"})
    response = client.get("/api/accounting/sat/balanza", headers=headers, params=MONTH)
    assert response.status_code == 400
    assert "5300" in response.json()["detail"]

    client.patch(f"/api/accounting/accounts/{renta['id']}", headers=headers, json={"sat_code": "601.45"})
    preview = client.get("/api/accounting/sat/preview", headers=headers, params=MONTH).json()
    assert preview["ready"] is True and preview["rfc"] == "FET180312AB1"
    assert _catalogo(client, headers)["5300"]["@CodAgrup"] == "601.45"


def test_only_the_active_company_goes_out(client):
    mine, my_account, my_category = _setup(client, email="yo@example.com", business="Mía")
    theirs, their_account, their_category = _setup(
        client, email="otro@example.com", business="Ajena", rfc="AJE010101AB1"
    )
    _income(client, mine, my_account, my_category, amount="1160")
    _income(client, theirs, their_account, their_category, amount="116000")

    assert _balanza(client, mine)["4100"]["@SaldoFin"] == Decimal("1000.00")


def test_a_viewer_cannot_download(client):
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
    assert client.get("/api/accounting/sat/catalogo", headers=viewer, params=MONTH).status_code == 403
```

- [ ] **Step 2: Correr y confirmar que fallan**

Run: `pytest tests/test_sat_export.py -q`
Expected: FAIL; 404 en `/api/accounting/sat/*`.

- [ ] **Step 3: Servicio**

En `app/domains/accounting/service.py`:

a) Imports: cambiar `from datetime import date` por `from datetime import date, timedelta`; agregar `from decimal import Decimal`, `from sqlalchemy import func` y:

```python
from app.models.organization import Organization
from app.services.accounting.sat import (
    BalanceRow,
    CatalogRow,
    SatError,
    is_valid_rfc,
    nature,
    normalize_rfc,
)
```

b) Al final del archivo:

```python
# --- Contabilidad electrónica (Anexo 24) ---


def _active_accounts(db: Session, organization_id: str) -> list[Account]:
    return (
        db.query(Account)
        .filter(Account.organization_id == organization_id, Account.active.is_(True))
        .order_by(Account.code)
        .all()
    )


def sat_catalog(db: Session, organization_id: str) -> list[CatalogRow]:
    """Todas las cuentas activas: el SAT quiere el catálogo completo, padres incluidos."""
    accounts = _active_accounts(db, organization_id)
    by_id = {account.id: account for account in accounts}
    rows = []
    for account in accounts:
        parent = by_id.get(account.parent_id) if account.parent_id else None
        rows.append(
            CatalogRow(
                code=account.code,
                name=account.name,
                sat_code=account.sat_code or "",
                parent_code=parent.code if parent else None,
                level=2 if parent else 1,
                nature=nature(account.type, account.code),
            )
        )
    return rows


def _line_sums(
    db: Session, organization_id: str, start: date | None, end: date | None
) -> dict[str, tuple[Decimal, Decimal]]:
    """(cargos, abonos) por cuenta en un rango de fechas, sólo pólizas contabilizadas."""
    query = (
        db.query(
            JournalEntryLine.account_id,
            func.coalesce(func.sum(JournalEntryLine.debit), 0),
            func.coalesce(func.sum(JournalEntryLine.credit), 0),
        )
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .filter(JournalEntry.organization_id == organization_id, JournalEntry.status == "POSTED")
    )
    if start is not None:
        query = query.filter(JournalEntry.date >= start)
    if end is not None:
        query = query.filter(JournalEntry.date <= end)
    return {
        account_id: (Decimal(debit or 0), Decimal(credit or 0))
        for account_id, debit, credit in query.group_by(JournalEntryLine.account_id).all()
    }


def sat_balance(db: Session, organization_id: str, year: int, month: int) -> list[BalanceRow]:
    """Saldo inicial, movimientos del mes y saldo final por cuenta, en la
    naturaleza de cada una. Los padres suman los cargos y abonos de sus hijas y
    aplican SU naturaleza: así un contra-activo resta en el total de activo."""
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    before = _line_sums(db, organization_id, None, start - timedelta(days=1))
    during = _line_sums(db, organization_id, start, end)

    accounts = _active_accounts(db, organization_id)
    zero = (Decimal("0"), Decimal("0"))
    raw: dict[str, list[Decimal]] = {}  # id → [deb_before, cred_before, deb_month, cred_month]
    for account in accounts:
        db_, cb = before.get(account.id, zero)
        dm, cm = during.get(account.id, zero)
        raw[account.id] = [db_, cb, dm, cm]
    for account in accounts:
        if account.parent_id in raw:
            for i in range(4):
                raw[account.parent_id][i] += raw[account.id][i]

    rows: list[BalanceRow] = []
    leaf_debe = leaf_haber = Decimal("0")
    for account in accounts:
        deb_before, cred_before, debe, haber = raw[account.id]
        if nature(account.type, account.code) == "D":
            saldo_ini = deb_before - cred_before
            saldo_fin = saldo_ini + debe - haber
        else:
            saldo_ini = cred_before - deb_before
            saldo_fin = saldo_ini - debe + haber
        if not any((saldo_ini, debe, haber, saldo_fin)):
            continue
        if account.parent_id:
            leaf_debe += debe
            leaf_haber += haber
        rows.append(BalanceRow(account.code, saldo_ini, debe, haber, saldo_fin))

    if leaf_debe != leaf_haber:
        raise SatError(
            f"La balanza de {year}-{month:02d} no cuadra: cargos {leaf_debe:.2f}, abonos {leaf_haber:.2f}."
        )
    return rows


def sat_requirements(db: Session, organization: Organization, year: int, month: int) -> dict:
    """Qué falta para poder generar los XML del mes."""
    accounts = _active_accounts(db, organization.id)
    missing = [
        {"id": a.id, "code": a.code, "name": a.name} for a in accounts if not a.sat_code
    ]
    rfc = normalize_rfc(organization.tax_id)
    rfc_ok = is_valid_rfc(rfc)
    return {
        "year": year,
        "month": month,
        "rfc": rfc or None,
        "rfc_ok": rfc_ok,
        "accounts": len(accounts),
        "missing_accounts": missing,
        "ready": rfc_ok and not missing,
    }
```

- [ ] **Step 4: Endpoints**

En `app/domains/accounting/router.py`:

a) Imports: `from datetime import date as date_type` ya existe; agregar `from app.models.organization import ACCOUNTING_ROLES, Organization` (sustituyendo el import actual de `ACCOUNTING_ROLES`) y:

```python
from app.services.accounting.sat import (
    SatError,
    render_balanza,
    render_catalogo,
    sat_filename,
)
```

b) Al final del archivo:

```python
def _sat_ready(db: Session, org_id: str, year: int, month: int) -> tuple[str, dict]:
    """RFC válido y todas las cuentas clasificadas, o 400 diciendo qué falta."""
    organization = db.get(Organization, org_id)
    requirements = service.sat_requirements(db, organization, year, month)
    if not requirements["rfc_ok"]:
        raise HTTPException(
            status_code=400,
            detail="Captura el RFC de la empresa en Configuración antes de generar los XML del SAT.",
        )
    if requirements["missing_accounts"]:
        codes = ", ".join(a["code"] for a in requirements["missing_accounts"][:10])
        raise HTTPException(
            status_code=400,
            detail=f"Hay cuentas sin código agrupador del SAT: {codes}. Asígnalo en el catálogo.",
        )
    return requirements["rfc"], requirements


def _xml_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/sat/preview")
def sat_preview(
    year: int = Query(ge=2015, le=2100),
    month: int = Query(ge=1, le=12),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    organization = db.get(Organization, org_id)
    return service.sat_requirements(db, organization, year, month)


@router.get("/sat/catalogo")
def sat_catalogo(
    year: int = Query(ge=2015, le=2100),
    month: int = Query(ge=1, le=12),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Catálogo de cuentas del Anexo 24, sin sellar."""
    rfc, _requirements = _sat_ready(db, org_id, year, month)
    xml = render_catalogo(rfc, year, month, service.sat_catalog(db, org_id))
    return _xml_response(xml, sat_filename(rfc, year, month, "CT"))


@router.get("/sat/balanza")
def sat_balanza(
    year: int = Query(ge=2015, le=2100),
    month: int = Query(ge=1, le=12),
    tipo: str = Query(default="N", pattern="^[NC]$"),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Balanza de comprobación del Anexo 24 (N normal, C complementaria), sin sellar."""
    rfc, _requirements = _sat_ready(db, org_id, year, month)
    try:
        rows = service.sat_balance(db, org_id, year, month)
    except SatError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    xml = render_balanza(rfc, year, month, tipo, rows)
    return _xml_response(xml, sat_filename(rfc, year, month, f"B{tipo}"))
```

- [ ] **Step 5: Correr y confirmar que pasan**

Run: `pytest tests/test_sat_export.py tests/test_sat_xml.py tests/test_sat_cuentas.py -q && ruff check app tests`
Expected: `25 passed` y `All checks passed!`

- [ ] **Step 6: Suite completa y commit**

Run: `pytest -q`
Expected: todo en verde.

```bash
git add app/domains/accounting/service.py app/domains/accounting/router.py tests/test_sat_export.py
git commit -m "feat(sat): catálogo y balanza del mes en XML del Anexo 24

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Frontend — columna "Código SAT" y botón SAT por mes

**Files:**
- Modify: `frontend/src/types/api.ts` (`LedgerAccount`, nuevo `SatCode`)
- Create: `frontend/src/features/accounting/AccountFieldCell.tsx`
- Delete: `frontend/src/features/accounting/ContpaqiCodeCell.tsx`
- Create: `frontend/src/features/accounting/SatExport.tsx`
- Modify: `frontend/src/features/accounting/AccountingPage.tsx`, `PeriodsPanel.tsx`

**Interfaces:**
- Consumes: `GET /api/accounting/sat/codes`, `/sat/preview`, `/sat/catalogo`, `/sat/balanza`; `PATCH /api/accounting/accounts/{id}` con `contpaqi_code` o `sat_code`; `downloadFile`/`downloadErrorMessage` de `@/lib/download`.
- Produces: `AccountFieldCell({account, field, placeholder, list?, caption?})`, `SatExport({period, title, onClose})`.

- [ ] **Step 1: Tipos**

En `frontend/src/types/api.ts`, en `LedgerAccount` después de `contpaqi_code: string | null`:

```ts
  /** Código agrupador del SAT (Anexo 24), o null. */
  sat_code: string | null
```

y al final del archivo:

```ts
export interface SatCode {
  code: string
  name: string
}
```

- [ ] **Step 2: Celda editable genérica**

`frontend/src/features/accounting/AccountFieldCell.tsx`:

```tsx
import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import type { LedgerAccount } from '@/types/api'

type Field = 'contpaqi_code' | 'sat_code'

/** Un dato editable de una cuenta del catálogo (equivalente en CONTPAQi o código
 *  agrupador del SAT). Se guarda al salir del campo o con Enter; vacío lo quita. */
export function AccountFieldCell({
  account,
  field,
  placeholder,
  list,
  caption,
}: {
  account: LedgerAccount
  field: Field
  placeholder: string
  /** id de un <datalist> con las opciones válidas */
  list?: string
  /** texto bajo el campo (p. ej. el nombre del código elegido) */
  caption?: string
}) {
  const queryClient = useQueryClient()
  const saved = account[field] ?? ''
  const [value, setValue] = useState(saved)
  const [error, setError] = useState<string | null>(null)
  const editing = useRef(false)

  // Si la lista se vuelve a pedir (otra sesión guardó algo), el campo sigue a
  // lo guardado mientras nadie lo esté editando: así no se pisa un dato ajeno.
  useEffect(() => {
    if (!editing.current) setValue(saved)
  }, [saved])

  const save = useMutation({
    mutationFn: async (next: string) =>
      (await api.patch<LedgerAccount>(`/accounting/accounts/${account.id}`, { [field]: next })).data,
    onSuccess: (updated) => {
      setValue(updated[field] ?? '')
      setError(null)
      void queryClient.invalidateQueries({ queryKey: ['accounting', 'accounts'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  function commit() {
    editing.current = false
    if (value.trim() !== saved) save.mutate(value.trim())
  }

  return (
    <div>
      <input
        aria-label={`${placeholder} de ${account.code} ${account.name}`}
        list={list}
        className="figures w-40 rounded border border-border bg-surface px-2 py-1 text-sm placeholder:text-muted/50 hover:border-muted/40 disabled:opacity-60"
        placeholder={placeholder}
        value={value}
        maxLength={40}
        disabled={save.isPending}
        onFocus={() => {
          editing.current = true
        }}
        onChange={(event) => setValue(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === 'Enter') event.currentTarget.blur()
          if (event.key === 'Escape') {
            setValue(saved)
            setError(null)
          }
        }}
      />
      {error ? (
        <p className="mt-1 text-xs text-neg">{error}</p>
      ) : caption ? (
        <p className="mt-0.5 max-w-[10rem] truncate text-[11px] text-muted" title={caption}>
          {caption}
        </p>
      ) : null}
    </div>
  )
}
```

Borrar `frontend/src/features/accounting/ContpaqiCodeCell.tsx`.

En `frontend/src/features/accounting/AccountingPage.tsx`:

a) Reemplazar `import { ContpaqiCodeCell } from '@/features/accounting/ContpaqiCodeCell'` por `import { AccountFieldCell } from '@/features/accounting/AccountFieldCell'`, y agregar `SatCode` al import de tipos: `import type { JournalEntry, LedgerAccount, Page, SatCode, TrialBalanceRow } from '@/types/api'`.

b) Después de `accountsQuery`, agregar:

```ts
  const satCodesQuery = useQuery({
    queryKey: ['accounting', 'sat-codes'],
    queryFn: async () => (await api.get<SatCode[]>('/accounting/sat/codes')).data,
    enabled: tab === 'catalogo',
    staleTime: Infinity,
  })
  const satName = useMemo(() => {
    const map = new Map((satCodesQuery.data ?? []).map((item) => [item.code, item.name]))
    return (code: string | null) => (code ? (map.get(code) ?? '') : '')
  }, [satCodesQuery.data])
```

c) Reemplazar la pestaña del catálogo (desde `{tab === 'catalogo' ? (` hasta su `) : null}`) por:

```tsx
      {tab === 'catalogo' ? (
        <>
          <Table headers={['Código', 'Cuenta', 'Tipo', 'Código SAT', 'Cuenta en CONTPAQi']} secondary={[3, 5]}>
            {(accountsQuery.data ?? []).map((account) => (
              <tr key={account.id} className={account.parent_id ? '' : 'bg-surface-2/40 font-medium'}>
                <td className="figures px-4 py-2">{account.code}</td>
                <td className={`px-4 py-2 ${account.parent_id ? 'pl-8' : ''}`}>{account.name}</td>
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
              </tr>
            ))}
          </Table>
          <datalist id="sat-codes">
            {(satCodesQuery.data ?? []).map((item) => (
              <option key={item.code} value={item.code}>
                {item.name}
              </option>
            ))}
          </datalist>
        </>
      ) : null}
```

- [ ] **Step 3: Modal SAT**

`frontend/src/features/accounting/SatExport.tsx`:

```tsx
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { downloadErrorMessage, downloadFile } from '@/lib/download'

interface Preview {
  rfc: string | null
  rfc_ok: boolean
  accounts: number
  missing_accounts: { id: string; code: string; name: string }[]
  ready: boolean
}

/** Contabilidad electrónica del SAT (Anexo 24): catálogo y balanza del mes en XML. */
export function SatExport({
  period,
  title,
  onClose,
}: {
  period: { year: number; month: number } | null
  title: string
  onClose: () => void
}) {
  const [busy, setBusy] = useState<'catalogo' | 'balanza' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const preview = useQuery({
    queryKey: ['accounting', 'sat-preview', period?.year, period?.month],
    queryFn: async () =>
      (
        await api.get<Preview>('/accounting/sat/preview', {
          params: { year: period!.year, month: period!.month },
        })
      ).data,
    enabled: period !== null,
    staleTime: 0,
  })

  function close() {
    setError(null)
    onClose()
  }

  async function download(kind: 'catalogo' | 'balanza') {
    if (!period) return
    setBusy(kind)
    setError(null)
    try {
      await downloadFile(
        `/accounting/sat/${kind}`,
        { year: period.year, month: period.month },
        `${kind}-sat.xml`,
      )
    } catch (err) {
      setError(await downloadErrorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  const data = preview.data
  const missing = data?.missing_accounts ?? []

  return (
    <Modal title={`Contabilidad electrónica de ${title}`} open={period !== null} onClose={close}>
      {preview.isLoading ? (
        <div className="h-24 animate-pulse rounded-lg bg-surface-2" />
      ) : preview.error ? (
        <p className="text-sm text-neg">{errorMessage(preview.error)}</p>
      ) : data ? (
        <div className="space-y-4">
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-xs text-muted">RFC</dt>
              <dd className={`figures font-semibold ${data.rfc_ok ? '' : 'text-neg'}`}>
                {data.rfc ?? 'Sin capturar'}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Cuentas en el catálogo</dt>
              <dd className="figures font-semibold">{data.accounts}</dd>
            </div>
          </dl>

          {!data.rfc_ok ? (
            <p className="rounded-lg border border-neg/30 bg-neg/10 p-3 text-sm text-neg">
              Falta el RFC de la empresa, o no tiene formato válido. Captúralo en{' '}
              <Link to="/configuracion" className="font-medium underline" onClick={close}>
                Configuración
              </Link>
              .
            </p>
          ) : null}

          {missing.length > 0 ? (
            <div className="rounded-lg border border-warn/30 bg-warn/10 p-3 text-sm">
              <p className="font-medium text-warn">
                {missing.length === 1
                  ? '1 cuenta sin código agrupador del SAT'
                  : `${missing.length} cuentas sin código agrupador del SAT`}
              </p>
              <p className="mt-1 text-muted">
                El SAT exige clasificar todas las cuentas. Asígnalo en el{' '}
                <Link
                  to="/contabilidad?vista=catalogo"
                  className="font-medium text-accent hover:underline"
                  onClick={close}
                >
                  catálogo de cuentas
                </Link>
                .
              </p>
              <ul className="figures mt-2 space-y-0.5 text-xs text-muted">
                {missing.map((account) => (
                  <li key={account.id}>
                    {account.code} {account.name}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <p className="text-xs text-muted">
            Los XML salen sin sellar. El sello con la e.firma y el envío al buzón tributario se
            hacen con la herramienta del contador.
          </p>

          {error ? (
            <p role="alert" className="rounded border-l-2 border-neg bg-neg/10 px-3 py-2 text-sm text-neg">
              {error}
            </p>
          ) : null}

          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="ghost" onClick={close}>
              Cerrar
            </Button>
            <Button
              variant="secondary"
              disabled={!data.ready || busy !== null}
              onClick={() => void download('catalogo')}
            >
              {busy === 'catalogo' ? 'Preparando…' : 'Catálogo XML'}
            </Button>
            <Button disabled={!data.ready || busy !== null} onClick={() => void download('balanza')}>
              {busy === 'balanza' ? 'Preparando…' : 'Balanza XML'}
            </Button>
          </div>
        </div>
      ) : null}
    </Modal>
  )
}
```

En `frontend/src/features/accounting/PeriodsPanel.tsx`:

a) Import: `import { SatExport } from '@/features/accounting/SatExport'`.

b) Junto a `const [exporting, setExporting] = useState<Period | null>(null)`:

```tsx
  const [satPeriod, setSatPeriod] = useState<Period | null>(null)
```

c) Justo después del botón `CONTPAQi` (dentro del mismo `{period.entries > 0 ? (…) : null}`), convertirlo en un fragmento con los dos botones:

```tsx
              {period.entries > 0 ? (
                <>
                  <Button
                    variant="ghost"
                    className="mr-1 !px-2 !py-1 text-xs"
                    onClick={() => setExporting(period)}
                  >
                    CONTPAQi
                  </Button>
                  <Button
                    variant="ghost"
                    className="mr-1 !px-2 !py-1 text-xs"
                    onClick={() => setSatPeriod(period)}
                  >
                    SAT
                  </Button>
                </>
              ) : null}
```

d) Después del `<ContpaqiExport … />`:

```tsx
      <SatExport
        period={satPeriod}
        title={satPeriod ? monthName(satPeriod.label) : ''}
        onClose={() => setSatPeriod(null)}
      />
```

- [ ] **Step 4: Verificar**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: sin errores.

- [ ] **Step 5: Commit**

```bash
git add -A frontend/src/features/accounting frontend/src/types/api.ts
git commit -m "feat(sat): código SAT en el catálogo y descarga de catálogo y balanza XML por mes

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Verificación de punta a punta y estado

**Files:**
- Modify: `docs/MVP_STATUS.md`

- [ ] **Step 1: Suite, lint, migración, build**

Run: `pytest -q && ruff check . && alembic heads && (cd frontend && npm run typecheck && npm run build)`
Expected: todo en verde; head `20261006_01`.

- [ ] **Step 2: Local con base desechable, siembra y XML reales**

```bash
rm -f "$S/sat.db"; DATABASE_URL="sqlite:///$S/sat.db" alembic upgrade head
DATABASE_URL="sqlite:///$S/sat.db" uvicorn app.main:app --port 8000 &
python scripts/demo_despacho.py --url http://localhost:8000
```

Con la Ferretería (tiene RFC): descargar catálogo y balanza de septiembre, validarlos contra `tests/fixtures/sat/*.xsd` con `xmlschema`, y comprobar que Σ Debe = Σ Haber en hojas y que `SaldoFin` de 1100 coincide con `/api/accounting/trial-balance`. Con el Despacho (sin RFC hasta que lo capture el script): la vista previa dice `rfc_ok: false` y la descarga responde 400.

- [ ] **Step 3: Navegador**

Con la página puente y el conductor de clics: `/contabilidad?vista=catalogo` muestra la columna "Código SAT" con nombre bajo cada código; cambiar 5300 a `601.45` guarda y muestra "Arrendamiento a personas físicas…"; `/contabilidad?vista=periodos` muestra el botón "SAT"; el modal muestra RFC y cuentas, y las dos descargas llegan como `application/xml`.

- [ ] **Step 4: Estado y commit**

En `docs/MVP_STATUS.md`, después del renglón "Puente a CONTPAQi":

```markdown
- **Contabilidad electrónica SAT** (spec 2026-10-06): código agrupador por cuenta (`accounts.sat_code`, defaults del catálogo de ARCA, selector con la lista oficial de 1,080 códigos), catálogo y balanza del mes en XML 1.3 del Anexo 24 validados contra los XSD oficiales (`GET /api/accounting/sat/catalogo`, `/sat/balanza`, vista previa en `/sat/preview`), botón SAT por mes en Cierre de periodo. Sin sellar: el sello y el envío los hace el contador.
```

```bash
git add docs/MVP_STATUS.md
git commit -m "docs(sat): estado de la contabilidad electrónica

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```
