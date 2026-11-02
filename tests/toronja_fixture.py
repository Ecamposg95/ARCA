"""Reporte de ventas de Toronja sintético.

Reproduce el formato verificado en el spec: archivo `.xls` que en realidad es
HTML (`<table>` con `<tr>`/`<td>`), latin-1, encabezados exactos, montos como
`$ 1,240.00`, folio `DDMMAA####`, FECHA `AAAA-MM-DD`, VENDEDOR como unidad.
Los nombres de pacientes (`CLIENTE`) y los estudios van en el archivo para
comprobar que NUNCA se persisten.
"""

from __future__ import annotations

from decimal import Decimal

TORONJA_HEADERS = [
    "FOLIO",
    "CLIENTE",
    "ESTUDIOS",
    "TOTAL",
    "EFECTIVO",
    "TARJETA DEBITO",
    "TARJETA CREDITO",
    "TRANSFERENCIA",
    "CREDITO",
    "SUMA ABONO",
    "IVA",
    "TOTAL CON IVA",
    "PAGO CON IVA / DESCUENTO",
    "GRAN TOTAL",
    "ADEUDO",
    "VENDEDOR",
    "CANCELADO",
    "CANCELADO POR",
    "EDITADO",
    "FECHA",
]


def money(value) -> str:
    amount = Decimal(str(value or 0))
    return f"$ {amount:,.2f}"


def ticket(
    folio: str,
    fecha: str,
    vendedor: str,
    *,
    cliente: str = "PACIENTE DE PRUEBA",
    estudios: str = "BH, QS",
    efectivo="0",
    tarjeta_debito="0",
    tarjeta_credito="0",
    transferencia="0",
    credito="0",
    descuento="0",
    adeudo="0",
    cancelado: str = "",
    cancelado_por: str = "",
    editado: str = "",
) -> dict:
    cobrado = sum(Decimal(str(x)) for x in (efectivo, tarjeta_debito, tarjeta_credito, transferencia, credito))
    gran_total = cobrado + Decimal(str(adeudo))
    total = gran_total + Decimal(str(descuento))
    return {
        "FOLIO": folio,
        "CLIENTE": cliente,
        "ESTUDIOS": estudios,
        "TOTAL": money(total),
        "EFECTIVO": money(efectivo),
        "TARJETA DEBITO": money(tarjeta_debito),
        "TARJETA CREDITO": money(tarjeta_credito),
        "TRANSFERENCIA": money(transferencia),
        "CREDITO": money(credito),
        "SUMA ABONO": money(cobrado),
        "IVA": money(0),
        "TOTAL CON IVA": money(total),
        "PAGO CON IVA / DESCUENTO": money(descuento),
        "GRAN TOTAL": money(gran_total),
        "ADEUDO": money(adeudo),
        "VENDEDOR": vendedor,
        "CANCELADO": cancelado,
        "CANCELADO POR": cancelado_por,
        "EDITADO": editado,
        "FECHA": fecha,
    }


def render_html(tickets: list[dict], headers: list[str] | None = None) -> bytes:
    headers = headers or TORONJA_HEADERS
    rows = ["<tr>" + "".join(f"<td>{h}</td>" for h in headers) + "</tr>"]
    for item in tickets:
        rows.append("<tr>" + "".join(f"<td>{item.get(h, '')}</td>" for h in headers) + "</tr>")
    html = (
        '<html><head><meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">'
        "<title>Reporte de ventas</title></head><body>"
        '<table border="1">' + "".join(rows) + "</table></body></html>"
    )
    return html.encode("latin-1")


# Las unidades y su alias en Toronja, como las usaría LaFe.
UNIT_MORELOS = "MORELOS"
UNIT_VILLAS = "VILLAS DE NUESTRA SEÑORA"
UNIT_MOVIL = "CENTRO MOVIL"


def sample_tickets() -> list[dict]:
    """12 tickets: varias unidades, formas de pago mezcladas, uno cancelado, uno
    con adeudo, uno con vendedor desconocido, uno de soporte en 0 y dos del
    mismo día y unidad (el spec pide exactamente este surtido)."""
    return [
        # Morelos, 15-oct: dos en efectivo el mismo día (se agrupan) y uno con tarjeta.
        ticket("1510260001", "2026-10-15", UNIT_MORELOS, efectivo="500"),
        ticket("1510260002", "2026-10-15", UNIT_MORELOS, efectivo="740", descuento="60"),
        ticket("1510260003", "2026-10-15", UNIT_MORELOS, tarjeta_debito="1200"),
        # Morelos, 15-oct: tarjeta de crédito y transferencia.
        ticket("1510260004", "2026-10-15", UNIT_MORELOS, tarjeta_credito="300"),
        ticket("1510260005", "2026-10-15", UNIT_MORELOS, transferencia="950"),
        # Villas (con Ñ en latin-1), 15-oct: efectivo y un adeudo parcial.
        ticket("1510260006", "2026-10-15", UNIT_VILLAS, efectivo="400"),
        ticket("1510260007", "2026-10-15", UNIT_VILLAS, efectivo="200", adeudo="800"),
        # Villas, 16-oct: ticket a crédito (va a CxC).
        ticket("1610260008", "2026-10-16", UNIT_VILLAS, credito="1500"),
        # Cancelado: no se importa.
        ticket("1610260009", "2026-10-16", UNIT_MORELOS, efectivo="999", cancelado="SI", cancelado_por="ADMIN"),
        # Vendedor sin unidad: error que no bloquea.
        ticket("1610260010", "2026-10-16", "SUCURSAL FANTASMA", efectivo="100"),
        # Soporte técnico del sistema, en cero: omitido.
        ticket("1610260011", "2026-10-16", "Soporte Técnico del Sistema"),
        # Centro móvil, mezcla efectivo + tarjeta en el mismo ticket.
        ticket("1610260012", "2026-10-16", UNIT_MOVIL, efectivo="150", tarjeta_debito="350"),
    ]
