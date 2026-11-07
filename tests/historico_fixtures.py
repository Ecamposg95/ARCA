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


def reconstruccion_xlsx() -> bytes:
    """Hojas 03, 04, 17 y 18 de la reconstrucción: valores como texto, igual
    que el archivo real (lo exporta así)."""
    wb = Workbook()
    wb.remove(wb.active)

    ws = wb.create_sheet("03_Libro_Diario")
    ws["A1"] = "Libro diario reconstruido (preliminar)"
    ws["A3"] = "← Volver al índice"
    header = [
        "Póliza", "Fecha", "Mes #", "Mes", "Concepto", "Cuenta de cargo", "Nombre cuenta de cargo",
        "Cuenta de abono", "Nombre cuenta de abono", "Monto (MXN)", "Entidad (Liza / Ale)", "Unidad de negocio",
        "Contraparte", "Fuente", "Referencia de origen (trazabilidad)", "Estatus", "Ajuste aplicado", "Hallazgo",
    ]  # fmt: skip
    for j, v in enumerate(header, start=1):
        ws.cell(row=5, column=j, value=v)
    polizas = [
        ("PZ-00001", "2026-01-01 00:00:00", "6111", "Software y suscripciones", "389.76", "Liza", "Villas", "Confirmado"),
        ("PZ-00002", "2026-01-15 00:00:00", "6111", "Software y suscripciones", "110.24", "Liza", "Villas", "Confirmado"),
        ("PZ-00003", "2026-01-20 00:00:00", "6128", "Consumos con tarjeta por validar", "500", "Por asignar", None, "Por confirmar"),
        ("PZ-00004", "2026-02-02 00:00:00", "5101", "Reactivos", "1000.5", "Ale", "Centro Médico", "Reclasificado"),
        ("PZ-00005", "2026-02-03 00:00:00", "1102", "Bancos", "99999", "Liza", None, "Confirmado"),
    ]
    for i, (folio, fecha, cargo, nombre, monto, entidad, unidad, estatus) in enumerate(polizas, start=6):
        ws.cell(row=i, column=1, value=folio)
        ws.cell(row=i, column=2, value=fecha)
        ws.cell(row=i, column=6, value=cargo)
        ws.cell(row=i, column=7, value=nombre)
        ws.cell(row=i, column=8, value="2101")
        ws.cell(row=i, column=10, value=monto)
        ws.cell(row=i, column=11, value=entidad)
        ws.cell(row=i, column=12, value=unidad)
        ws.cell(row=i, column=16, value=estatus)

    ws = wb.create_sheet("04_Estado_Resultados")
    ws["A1"] = "Estado de resultados preliminar 2026 (enero–septiembre)"
    for j, v in enumerate(["Cuenta", "Concepto", "Código SAT", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Total ene–sep", "% de ingresos"], start=1):
        ws.cell(row=5, column=j, value=v)
    ws["A6"] = "Ingresos"
    rows = [
        ("4101", "Servicios de laboratorio", ["824764.74"] + ["800000"] * 8),
        (None, "Total de ingresos", ["861269.74"] + ["850000"] * 7 + ["930425.82"]),
        (None, "Total costo de ventas", ["165795.95"] + ["100000"] * 8),
        (None, "Utilidad bruta", ["695473.79"] + ["750000"] * 8),
        (None, "Total gastos de operación", ["485746.67"] + ["500000"] * 8),
        (None, "Utilidad de operación", ["209727.12"] + ["250000"] * 8),
        (None, "Total resultado integral de financiamiento", ["8523.63"] + ["9000"] * 8),
        (None, "Utilidad antes de sueldo de socias", ["201203.49"] + ["241000"] * 8),
        ("3201", "Sueldo de socias (30,000 por socia)", ["60000"] * 9),
        (None, "Utilidad después de sueldo de socias", ["141203.49"] + ["181000"] * 7 + ["-15020.82"]),
    ]
    for i, (code, concepto, values) in enumerate(rows, start=7):
        ws.cell(row=i, column=1, value=code)
        ws.cell(row=i, column=2, value=concepto)
        for j, v in enumerate(values):
            ws.cell(row=i, column=4 + j, value=v)
        ws.cell(row=i, column=13, value="0")

    ws = wb.create_sheet("17_Hallazgos")
    ws["A1"] = "Hallazgos"
    for j, v in enumerate(["ID", "Severidad", "Estatus", "Tema"], start=1):
        ws.cell(row=5, column=j, value=v)
    for i, (hid, est) in enumerate([("H-01", "Parcial"), ("H-02", "Resuelto"), ("H-03", "Resuelto"), ("H-04", "Nuevo")], start=6):
        ws.cell(row=i, column=1, value=hid)
        ws.cell(row=i, column=3, value=est)

    ws = wb.create_sheet("18_Dudas")
    ws["A1"] = "Dudas"
    for j, v in enumerate(["ID", "Tema", "Pregunta", "Estatus"], start=1):
        ws.cell(row=5, column=j, value=v)
    for i, (did, est) in enumerate([("D-01", "Parcial"), ("D-02", "Respondida"), ("D-03", "Sin respuesta")], start=6):
        ws.cell(row=i, column=1, value=did)
        ws.cell(row=i, column=4, value=est)
    return _bytes(wb)
