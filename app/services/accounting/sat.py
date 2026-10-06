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
