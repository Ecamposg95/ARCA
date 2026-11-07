"""Libros xlsx sintéticos con la geometría real de los Excel de La Fe y cifras
inventadas (salvo las tres que el plan usa como referencia)."""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook

MESES = [
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
    "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
]  # fmt: skip


def _bytes(wb: Workbook) -> bytes:
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def control_general_xlsx() -> bytes:
    wb = Workbook()
    wb.remove(wb.active)

    # --- RESUTADOS: meses en D…O, CAJA en col B, bancos en col C bajo BANCOS.
    ws = wb.create_sheet("RESUTADOS")
    for i, mes in enumerate(MESES):
        ws.cell(row=1, column=4 + i, value=mes)
    ws["A2"] = "ACTIVO CIRCULANTE"
    ws["B3"] = "CAJA"
    for i, v in enumerate([33000.0, 8500.0, 13060.0, 50000, 0.0, -308.4, 23427.0, 50855.0, 109071.0]):
        ws.cell(row=3, column=4 + i, value=v)
    ws["B4"] = "BANCOS"
    ws["C5"] = "SANTANDER PYME"
    for i, v in enumerate([12075.53, 3514.25, 27918.73]):
        ws.cell(row=5, column=4 + i, value=v)
    ws["C6"] = "NU BANK"
    ws["D6"] = 6000.0
    ws["E6"] = 0.0
    ws["C7"] = "TOTAL "
    for i in range(12):
        ws.cell(row=7, column=4 + i, value=0)
    ws["A8"] = "INGRESOS"
    ws["C9"] = "SUELDOS Y COMISIONES"
    ws["D9"] = "#REF!"
    ws["E9"] = 224975.49

    # --- PROY: VENTAS (años con % y DIFERENCIA intercalados) y NO. PACIENTES.
    ws = wb.create_sheet("PROY")
    header = ["VENTAS", 2022.0, "2023", "%", 2024.0, "%", "2025", "%", 2026.0, "%", 2027.0, "2027 conservador", "%", "DIFERENCIA"]
    for j, v in enumerate(header, start=1):
        ws.cell(row=1, column=j, value=v)
    ventas = {
        2022: [100 + m for m in range(12)],
        2023: [200 + m for m in range(12)],
        2024: [300 + m for m in range(12)],
        2025: [400 + m for m in range(12)],
        2026: [500 + m for m in range(12)],
        2027: [600 + m for m in range(12)],
        "cons": [650 + m for m in range(12)],
    }
    ventas[2025][8] = 573522.0
    ventas[2026][8] = 888242.0
    ventas[2026][9] = 916551.45  # proyección: sin pacientes
    ventas[2027][0] = 1328191.007
    cols = {2022: 2, 2023: 3, 2024: 5, 2025: 7, 2026: 9, 2027: 11, "cons": 12}
    for m, mes in enumerate(MESES):
        r = 2 + m
        ws.cell(row=r, column=1, value=mes)
        for year, col in cols.items():
            ws.cell(row=r, column=col, value=ventas[year][m])
        ws.cell(row=r, column=4, value=1.5)  # %
        ws.cell(row=r, column=14, value=9.9)  # DIFERENCIA
    ws.cell(row=14, column=2, value=sum(ventas[2022]))  # totales sin etiqueta
    ws.cell(row=15, column=17, value=125000)
    header2 = ["NO. PACIENTES", 2022.0, "2023", "%", 2024.0, "%", "2025", "%", "2026", "%"]
    for j, v in enumerate(header2, start=1):
        ws.cell(row=16, column=j, value=v)
    for m, mes in enumerate(MESES):
        r = 17 + m
        ws.cell(row=r, column=1, value=mes)
        for year, col in list(cols.items())[:5]:
            if year == 2026 and m >= 9:
                continue  # oct–dic 2026 sin pacientes = proyección
            ws.cell(row=r, column=col, value=1000 + m)
    ws.cell(row=29, column=2, value=1276.3)

    # --- PRESTAMOS: nombre en col B, total en col C.
    ws = wb.create_sheet("PRESTAMOS")
    ws["A1"] = "CONCENTRADO DE DEUDA"
    ws["C2"], ws["D2"], ws["E2"] = "TOTALES", "INTERES", "CRÉDITOS"
    ws["A3"], ws["E3"] = "LABORATORIO", 743693
    ws["B4"], ws["C4"], ws["D4"], ws["E4"] = "PRÉSTAMO SOCIA", 62692, 0.0, 62692
    ws["B5"], ws["C5"], ws["D5"], ws["E5"] = "DEUDA PROVEEDOR", 177001, 0.15, 177001
    ws["B6"], ws["D6"] = "EQUIPO SIN TOTAL", 0.0

    # --- INVERSIONES: CONCENTRADO GENERAL en H–I.
    ws = wb.create_sheet("INVERSIONES")
    ws["A1"], ws["C1"], ws["E1"], ws["H1"] = "SUCURSAL ALEDRO", "MONTO", "TOTAES HACIENDAS", "CONCENTRADO GENERAL"
    ws["A2"], ws["E2"], ws["F2"], ws["H2"], ws["I2"] = "ARRANQUE DE SUCURSAL", "DEPÓSITO Y RENTA", 38280, "HACIENDAS", 462678.33
    ws["B3"], ws["C3"], ws["H3"], ws["I3"] = "DEPÓSITO ", 19140.0, "IA", 85000
    ws["H4"], ws["I4"] = "TOTAL", 547678.33
    ws["I5"] = 118927.48  # cifra suelta sin nombre
    return _bytes(wb)
