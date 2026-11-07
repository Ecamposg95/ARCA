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
