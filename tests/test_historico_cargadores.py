"""Cargadores del histórico: de un archivo a puntos agregados, sin datos de pacientes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domains.analytics.loading import load_files
from app.domains.analytics.loaders.toronja import load_toronja
from app.domains.analytics.points import Point
from app.models.historical import HistoricalPoint
from tests.helpers import auth_headers, register
from tests.toronja_fixture import render_html, ticket


def value(points, metric, period=None, dataset=None, **dims):
    found = [
        p
        for p in points
        if p.metric == metric
        and (period is None or p.period_start == period)
        and (dataset is None or p.dataset == dataset)
        and all(getattr(p, k) == v for k, v in dims.items())
    ]
    assert len(found) == 1, f"{metric} {period} {dims}: {found}"
    return found[0].value


def has(points, dataset, metric, period) -> bool:
    return any(p.dataset == dataset and p.metric == metric and p.period_start == period for p in points)


@pytest.fixture()
def org(client):
    body = register(client, email="cargas@example.com")
    return body["organization"]["id"], auth_headers(body)


@pytest.fixture()
def org_con_unidades(client, org):
    organization_id, headers = org
    villas = client.post(
        "/api/business-units", headers=headers, json={"name": "Villas", "aliases": ["VILLAS DE NUESTRA SEÑORA"]}
    ).json()
    cumbres = client.post("/api/business-units", headers=headers, json={"name": "Cumbres", "aliases": ["LAS CUMBRES"]}).json()
    assert client.patch(f"/api/business-units/{cumbres['id']}", headers=headers, json={"active": False}).status_code == 200
    return organization_id, headers, {"villas": villas["id"], "cumbres": cumbres["id"]}


# --- Toronja ---------------------------------------------------------------


def test_toronja_agrega_por_dia_unidad_y_excluye_cancelados():
    content = render_html(
        [
            ticket("0201260001", "2026-01-02", "VILLAS", efectivo="1000"),
            ticket("0201260002", "2026-01-02", "VILLAS", tarjeta_debito="300", tarjeta_credito="200"),
            ticket("0201260003", "2026-01-02", "VILLAS", efectivo="300", cancelado="SI", cancelado_por="ADMIN"),
        ]
    )
    points = load_toronja(content, "ventas.xls")
    net = [p for p in points if p.metric == "net_sales"]
    assert net == [Point("sales_daily", "net_sales", date(2026, 1, 2), "day", Decimal("1500.00"), unit_label="VILLAS")]
    assert value(points, "tickets") == 2
    assert value(points, "cancelled") == 1
    assert value(points, "net_sales_by_method", payment_method="EFECTIVO") == Decimal("1000.00")
    assert value(points, "net_sales_by_method", payment_method="TARJETA") == Decimal("500.00")
    assert not any(p.payment_method in ("TRANSFERENCIA", "CREDITO") for p in points)


def test_toronja_descuento_adeudo_editados_y_dias_separados():
    content = render_html(
        [
            ticket("0201260001", "2026-01-02", "MORELOS", efectivo="740", descuento="60", editado="SI"),
            ticket("0301260002", "2026-01-03", "MORELOS", efectivo="200", adeudo="800"),
            ticket("0301260003", "2026-01-03", "VILLAS", credito="1500"),
        ]
    )
    points = load_toronja(content, "ventas.xls")
    assert value(points, "discount", date(2026, 1, 2), unit_label="MORELOS") == Decimal("60.00")
    assert value(points, "edited", date(2026, 1, 2), unit_label="MORELOS") == Decimal("1")
    assert value(points, "debt", date(2026, 1, 3), unit_label="MORELOS") == Decimal("800.00")
    assert value(points, "net_sales", date(2026, 1, 3), unit_label="MORELOS") == Decimal("1000.00")
    assert value(points, "net_sales_by_method", date(2026, 1, 3), unit_label="VILLAS", payment_method="CREDITO") == Decimal("1500.00")
    assert not has(points, "sales_daily", "net_sales_by_method", date(2026, 1, 2)) or value(
        points, "net_sales_by_method", date(2026, 1, 2), payment_method="EFECTIVO"
    ) == Decimal("740.00")


def test_toronja_omite_soporte_y_tickets_en_cero():
    content = render_html(
        [
            ticket("0201260001", "2026-01-02", "VILLAS", efectivo="100"),
            ticket("0201260002", "2026-01-02", "Soporte Técnico del Sistema"),
            ticket("0201260003", "2026-01-02", "VILLAS"),
        ]
    )
    points = load_toronja(content, "ventas.xls")
    assert value(points, "tickets") == 1
    assert not any(p.unit_label and "SOPORTE" in p.unit_label.upper() for p in points)


def test_toronja_archivo_equivocado_levanta_error_en_espanol():
    from app.domains.analytics.points import HistoricalFormatError

    with pytest.raises(HistoricalFormatError) as exc:
        load_toronja(b"PK\x03\x04 no soy html", "cg.xlsx")
    assert "Toronja" in str(exc.value)


# --- load_files ------------------------------------------------------------


def test_toronja_nunca_persiste_paciente_ni_estudios(db, org):
    organization_id, _ = org
    content = render_html([ticket("0201260001", "2026-01-02", "VILLAS", efectivo="100", cliente="JUANA PEREZ", estudios="BH")])
    load_files(db, organization_id, {"toronja": ("v.xls", content)}, None)
    rows = db.query(HistoricalPoint).filter_by(organization_id=organization_id).all()
    assert rows
    dump = " ".join(str(c) for row in rows for c in row.__dict__.values())
    assert "JUANA" not in dump and "BH" not in dump


def test_unidad_no_resuelta_queda_con_etiqueta_y_se_reporta(db, org_con_unidades):
    organization_id, _, units = org_con_unidades
    content = render_html(
        [
            ticket("0201260001", "2026-01-02", "SUCURSAL FANTASMA", efectivo="100"),
            ticket("0201260002", "2026-01-02", "Villas", efectivo="50"),
        ]
    )
    report = load_files(db, organization_id, {"toronja": ("v.xls", content)}, None)
    assert report.unresolved_units == ["SUCURSAL FANTASMA"]
    assert report.loads[0]["family"] == "toronja" and report.loads[0]["rows"] > 0
    assert report.loads[0]["period_from"] == date(2026, 1, 2) == report.loads[0]["period_to"]
    fantasma = db.query(HistoricalPoint).filter_by(organization_id=organization_id, metric="net_sales", unit_label="SUCURSAL FANTASMA").one()
    assert fantasma.business_unit_id is None
    villas = db.query(HistoricalPoint).filter_by(organization_id=organization_id, metric="net_sales", business_unit_id=units["villas"]).one()
    assert villas.unit_label == "Villas" and villas.value == Decimal("50.00")


def test_alias_resuelve_unidad_inactiva(db, org_con_unidades):
    organization_id, _, units = org_con_unidades
    content = render_html([ticket("0201260001", "2026-01-02", "LAS CUMBRES", efectivo="100")])
    report = load_files(db, organization_id, {"toronja": ("v.xls", content)}, None)
    assert report.unresolved_units == []
    point = db.query(HistoricalPoint).filter_by(organization_id=organization_id, metric="net_sales").one()
    assert point.business_unit_id == units["cumbres"]


def test_dry_run_no_guarda(db, org):
    organization_id, _ = org
    content = render_html([ticket("0201260001", "2026-01-02", "VILLAS", efectivo="100")])
    report = load_files(db, organization_id, {"toronja": ("v.xls", content)}, None, dry_run=True)
    assert report.loads[0]["rows"] > 0
    assert db.query(HistoricalPoint).filter_by(organization_id=organization_id).count() == 0


def test_recargar_con_un_mes_mas_reemplaza_y_agrega(db, org):
    organization_id, _ = org
    ene_sep = [ticket(f"0{m}01260001", f"2026-0{m}-01", "VILLAS", efectivo=str(100 * m)) for m in range(1, 10)]
    load_files(db, organization_id, {"toronja": ("v1.xls", render_html(ene_sep))}, None)
    load_files(db, organization_id, {"toronja": ("v1.xls", render_html(ene_sep))}, None)
    first = db.query(HistoricalPoint).filter_by(organization_id=organization_id, metric="net_sales").count()
    assert first == 9

    ene_oct = ene_sep + [ticket("0110260001", "2026-10-01", "VILLAS", efectivo="1000")]
    ene_oct[0] = ticket("0101260001", "2026-01-01", "VILLAS", efectivo="111")
    load_files(db, organization_id, {"toronja": ("v2.xls", render_html(ene_oct))}, None)
    rows = (
        db.query(HistoricalPoint)
        .filter_by(organization_id=organization_id, metric="net_sales")
        .order_by(HistoricalPoint.period_start)
        .all()
    )
    assert len(rows) == 10
    assert rows[0].value == Decimal("111.00") and rows[-1].period_start == date(2026, 10, 1)
    assert all(r.source == "toronja:v2.xls#ventas" for r in rows)


# --- CONTROL GENERAL -------------------------------------------------------


@pytest.fixture(scope="module")
def cg_points():
    from app.domains.analytics.loaders.control_general import load_control_general
    from tests.historico_fixtures import control_general_xlsx

    return load_control_general(control_general_xlsx(), "2026_CONTROL_GENERAL_2.xlsx")


def test_proy_carga_anios_y_descarta_proyeccion(cg_points):
    pts = cg_points
    assert value(pts, "net_sales", date(2025, 9, 1), "sales_monthly") == Decimal("573522.00")
    assert value(pts, "net_sales", date(2026, 9, 1), "sales_monthly") == Decimal("888242.00")
    assert value(pts, "net_sales", date(2022, 1, 1), "sales_monthly") == Decimal("100.00")
    assert not has(pts, "sales_monthly", "net_sales", date(2026, 10, 1))  # sin pacientes = proyección
    assert not has(pts, "sales_monthly", "net_sales", date(2027, 1, 1))
    assert value(pts, "patients", date(2026, 9, 1), "sales_monthly") == Decimal("1008")
    assert len([p for p in pts if p.dataset == "sales_monthly" and p.metric == "net_sales"]) == 12 * 4 + 9


def test_proy_meta_2027(cg_points):
    assert value(cg_points, "target", date(2027, 1, 1), "sales_target") == Decimal("1328191.01")
    assert value(cg_points, "target_conservative", date(2027, 1, 1), "sales_target") == Decimal("650.00")
    assert len([p for p in cg_points if p.dataset == "sales_target"]) == 24


def test_resultados_saldos_omite_ref_y_total(cg_points):
    pts = [p for p in cg_points if p.dataset == "balance_monthly"]
    assert value(pts, "balance", date(2026, 1, 1), account_label="CAJA") == Decimal("33000.00")
    assert value(pts, "balance", date(2026, 5, 1), account_label="CAJA") == Decimal("0.00")
    assert value(pts, "balance", date(2026, 6, 1), account_label="CAJA") == Decimal("-308.40")
    assert value(pts, "balance", date(2026, 3, 1), account_label="SANTANDER PYME") == Decimal("27918.73")
    assert not has(pts, "balance_monthly", "balance", date(2026, 4, 1)) or not any(
        p.account_label == "SANTANDER PYME" and p.period_start == date(2026, 4, 1) for p in pts
    )
    assert {p.account_label for p in pts} == {"CAJA", "SANTANDER PYME", "NU BANK"}
    assert len([p for p in pts if p.period_start == date(2026, 10, 1)]) == 0


def test_prestamos_e_inversiones_como_foto(cg_points):
    snap = [p for p in cg_points if p.dataset == "snapshot"]
    assert all(p.period_grain == "snapshot" and p.period_start == date(2026, 10, 31) for p in snap)
    assert value(snap, "loan_balance", account_label="PRÉSTAMO SOCIA") == Decimal("62692.00")
    assert value(snap, "loan_balance", account_label="DEUDA PROVEEDOR") == Decimal("177001.00")
    assert {p.account_label for p in snap if p.metric == "loan_balance"} == {"PRÉSTAMO SOCIA", "DEUDA PROVEEDOR"}
    assert value(snap, "investment", unit_label="HACIENDAS") == Decimal("462678.33")
    assert {p.unit_label for p in snap if p.metric == "investment"} == {"HACIENDAS", "IA"}


def test_control_general_archivo_equivocado():
    from app.domains.analytics.loaders.control_general import load_control_general
    from app.domains.analytics.points import HistoricalFormatError

    with pytest.raises(HistoricalFormatError):
        load_control_general(b"<html><table><tr><td>FOLIO</td></tr></table></html>", "v.xls")


# --- Reconstrucción contable ----------------------------------------------


@pytest.fixture(scope="module")
def rec_points():
    from app.domains.analytics.loaders.reconstruccion import load_reconstruccion
    from tests.historico_fixtures import reconstruccion_xlsx

    return load_reconstruccion(reconstruccion_xlsx(), "Lafe_Registro_Contable_Reconstruido_2026_v2.xlsx")


def test_estado_resultados_mapea_totales(rec_points):
    pnl = [p for p in rec_points if p.dataset == "pnl_monthly"]
    assert value(pnl, "profit_after_partners", date(2026, 9, 1)) == Decimal("-15020.82")
    assert value(pnl, "revenue", date(2026, 1, 1)) == Decimal("861269.74")
    assert value(pnl, "cost_of_sales", date(2026, 1, 1)) == Decimal("165795.95")
    assert value(pnl, "gross_profit", date(2026, 1, 1)) == Decimal("695473.79")
    assert value(pnl, "operating_expenses", date(2026, 1, 1)) == Decimal("485746.67")
    assert value(pnl, "operating_profit", date(2026, 1, 1)) == Decimal("209727.12")
    assert value(pnl, "financial_result", date(2026, 1, 1)) == Decimal("8523.63")
    assert value(pnl, "profit_before_partners", date(2026, 1, 1)) == Decimal("201203.49")
    assert {p.metric for p in pnl} == {
        "revenue", "cost_of_sales", "gross_profit", "operating_expenses", "operating_profit",
        "financial_result", "profit_before_partners", "profit_after_partners",
    }  # fmt: skip
    assert len(pnl) == 8 * 9 and all(p.period_grain == "month" for p in pnl)


def test_libro_diario_agrega_gasto_y_omite_ingresos(rec_points):
    exp = [p for p in rec_points if p.dataset == "expense_monthly"]
    software = value(exp, "amount", date(2026, 1, 1), account_code="6111", entity_label="Liza", unit_label="Villas")
    assert software == Decimal("500.00")
    assert [p.account_label for p in exp if p.account_code == "6111"] == ["Software y suscripciones"]
    assert value(exp, "amount", date(2026, 2, 1), account_code="5101") == Decimal("1000.50")
    assert not any(p.account_code == "1102" for p in exp)
    assert len(exp) == 3


def test_por_asignar_queda_sin_entidad(rec_points):
    exp = [p for p in rec_points if p.dataset == "expense_monthly" and p.account_code == "6128"]
    assert len(exp) == 1 and exp[0].entity_label is None and exp[0].unit_label is None


def test_avance_de_revision_cuenta_por_estatus(rec_points):
    snap = {p.metric: p.value for p in rec_points if p.dataset == "snapshot"}
    assert all(p.period_start == date(2026, 10, 21) for p in rec_points if p.dataset == "snapshot")
    assert snap["journal_confirmed"] == 3 and snap["journal_pending"] == 2
    assert snap["findings_resuelto"] == 2 and snap["findings_parcial"] == 1 and snap["findings_nuevo"] == 1
    assert snap["questions_respondida"] == 1 and snap["questions_sin_respuesta"] == 1 and snap["questions_parcial"] == 1
