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
