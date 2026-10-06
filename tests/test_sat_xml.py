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
