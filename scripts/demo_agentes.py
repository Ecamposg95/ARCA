"""El equipo de agentes: financiero, contable y patrimonial sobre una empresa real.

Tres especialistas leen la MISMA empresa por la API de agentes —cada uno con su
propia llave, así la bandeja muestra tres firmas distintas— y cada uno deja una
propuesta con su evidencia. Ninguno escribe: proponen, y el humano decide en la
bandeja de ARCA. Es la demo de la tesis agéntica completa sin depender de un
modelo ni de la red de un tercero: el razonamiento aquí es determinista, como
los ejecutivos simulados de Cortex, pero los DATOS y la GOBERNANZA son reales.

    python scripts/demo_agentes.py --url https://arca-production-d769.up.railway.app \
        --email demo08270644@atlas.mx

Correr dos veces duplica propuestas (a propósito: cada corrida es una sesión de
trabajo de los agentes). Entre ensayos, rechaza las anteriores en la bandeja.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from decimal import Decimal

import httpx

ANCHO = 66


def caja(titulo: str) -> None:
    print("\n┌─ " + titulo + " " + "─" * max(ANCHO - len(titulo) - 4, 1) + "┐")


def linea(texto: str = "") -> None:
    print("│ " + texto)


def cierra() -> None:
    print("└" + "─" * ANCHO + "┘")


def dinero(valor) -> str:
    return f"${Decimal(str(valor)):,.2f}"


MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


class Agente:
    """Una llave, un nombre, y las herramientas de ARCA."""

    def __init__(self, base_url: str, token: str, nombre: str):
        self.nombre = nombre
        self.http = httpx.Client(
            base_url=f"{base_url}/api",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )

    def invoca(self, tool: str, argumentos: dict | None = None):
        respuesta = self.http.post(
            "/agent/invoke", json={"tool": tool, "arguments": argumentos or {}}
        )
        if respuesta.status_code >= 400:
            sys.exit(f"{self.nombre}: ARCA rechazó {tool}: {respuesta.text}")
        return respuesta.json()["result"]

    def lista(self, tool: str, argumentos: dict | None = None) -> list:
        """Los tools de listado devuelven lista plana o {items}: da igual cuál."""
        resultado = self.invoca(tool, argumentos)
        if isinstance(resultado, dict):
            return resultado.get("items", [])
        return resultado


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo del equipo de agentes")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--email", required=True, help="Dueño de la empresa del demo")
    parser.add_argument("--password", default="demoforo2026")
    args = parser.parse_args()
    base = args.url.rstrip("/")

    # --- El dueño crea las tres llaves (una por especialista) ---
    dueno = httpx.Client(base_url=f"{base}/api", timeout=30)
    sesion = dueno.post(
        "/auth/login", json={"email": args.email, "password": args.password}
    )
    if sesion.status_code != 200:
        sys.exit(f"No pude entrar como {args.email}: {sesion.text}")
    auth = sesion.json()
    dueno.headers.update(
        {
            "Authorization": f"Bearer {auth['access_token']}",
            "X-Organization-ID": auth["organization"]["id"],
        }
    )

    def llave(nombre: str) -> str:
        creada = dueno.post(
            "/agent-keys", json={"name": nombre, "scopes": "READ,PROPOSE"}
        )
        if creada.status_code != 201:
            sys.exit(f"No pude crear la llave de {nombre}: {creada.text}")
        return creada.json()["token"]

    financiero = Agente(base, llave("Agente Financiero"), "Agente Financiero")
    contable = Agente(base, llave("Agente Contable"), "Agente Contable")
    patrimonial = Agente(base, llave("Agente Patrimonial"), "Agente Patrimonial")

    hoy = date.today()
    propuestas: list[tuple[str, str]] = []

    # ══════════════════════ AGENTE FINANCIERO ══════════════════════
    resumen = financiero.invoca("dashboard_summary")
    cartera = financiero.invoca("aging_report", {"kind": "receivable"})
    proyeccion = financiero.invoca("cash_projection", {"days": 90})

    caja("AGENTE FINANCIERO · liquidez y cobranza")
    linea(f"Disponible hoy: {dinero(resumen['cash'])}")
    linea(
        f"Cartera: {dinero(cartera['total'])} · vencido {dinero(cartera['overdue'])}"
        f" · te pagan en {cartera['average_days']} días"
    )
    linea(f"Proyección 90d: {dinero(proyeccion['projected_cash'])}")

    vencidas = financiero.lista("list_receivables", {"status": "OVERDUE"})
    if vencidas:
        peor = max(vencidas, key=lambda r: Decimal(str(r["amount"])) - Decimal(str(r["amount_paid"])))
        saldo = Decimal(str(peor["amount"])) - Decimal(str(peor["amount_paid"]))
        dias = (hoy - date.fromisoformat(peor["due_date"])).days
        recargo = (saldo * Decimal("0.02")).quantize(Decimal("0.01"))
        linea(f"Hallazgo: '{peor['description']}' lleva {dias} días vencida ({dinero(saldo)}).")
        linea(f"→ Propone recargo por mora del 2%: {dinero(recargo)}")
        creada = financiero.invoca(
            "propose_receivable",
            {
                "summary": f"Recargo por mora 2% — {peor['description']} ({dias} días vencida)",
                "evidence": (
                    f"La factura venció el {peor['due_date']} y el saldo es {dinero(saldo)}. "
                    "El contrato marco permite 2% mensual de recargo. Cobrarlo también "
                    "acelera el pago del principal."
                ),
                "customer_id": peor["customer_id"],
                "description": f"Recargo por mora — {peor['description']}",
                "amount": str(recargo),
                "due_date": (hoy + timedelta(days=15)).isoformat(),
                "category_id": peor["category_id"],
            },
        )
        propuestas.append(("Agente Financiero", creada["proposal_id"]))
    else:
        linea("Sin facturas vencidas: nada que proponer hoy.")
    cierra()

    # ══════════════════════ AGENTE CONTABLE ══════════════════════
    balanza = contable.invoca("trial_balance")
    filas = balanza if isinstance(balanza, list) else balanza.get("rows", balanza)
    cargos = sum(Decimal(str(f["debit"])) for f in filas)
    abonos = sum(Decimal(str(f["credit"])) for f in filas)
    por_codigo = {f["code"]: f for f in filas}
    iva_por_cobrar = Decimal(str(por_codigo.get("2190", {}).get("credit", 0))) - Decimal(
        str(por_codigo.get("2190", {}).get("debit", 0))
    )

    gastos_mes = contable.lista(
        "list_expenses", {"start": hoy.replace(day=1).isoformat(), "end": hoy.isoformat()}
    )
    no_deducibles = [
        g
        for g in gastos_mes
        if g.get("payment_method") == "EFECTIVO" and Decimal(str(g["amount"])) > 2000
    ]

    caja("AGENTE CONTABLE · libros y disciplina fiscal")
    linea(f"Balanza: cargos {dinero(cargos)} = abonos {dinero(abonos)} → {'CUADRA' if cargos == abonos else 'NO CUADRA'}")
    linea(f"IVA trasladado cobrado por enterar: {dinero(iva_por_cobrar)}")
    if no_deducibles:
        total_nd = sum(Decimal(str(g["amount"])) for g in no_deducibles)
        linea(
            f"Hallazgo: {len(no_deducibles)} gasto(s) en efectivo > $2,000 "
            f"({dinero(total_nd)}) — no deducibles (LISR 27-III)."
        )
    categorias = {c["name"]: c for c in contable.lista("list_categories", {"kind": "EXPENSE"})}
    proveedores = {v["name"]: v for v in contable.lista("list_vendors")}
    despacho = proveedores.get("Despacho Contable Núñez")
    honorarios = categorias.get("Honorarios")
    if despacho and honorarios:
        linea("→ Propone provisionar los honorarios del cierre mensual.")
        creada = contable.invoca(
            "propose_expense",
            {
                "summary": f"Provisión: honorarios del cierre contable de {MESES[hoy.month - 1]}",
                "evidence": (
                    f"El mes lleva {len(gastos_mes)} gastos registrados y la balanza cuadra "
                    f"({dinero(cargos)}). El despacho factura el cierre a inicios del mes "
                    "siguiente; provisionarlo hoy deja el resultado del mes completo."
                    + (
                        f" Nota: detecté {len(no_deducibles)} gasto(s) en efectivo no deducibles."
                        if no_deducibles
                        else ""
                    )
                ),
                "date": hoy.isoformat(),
                "vendor_id": despacho["id"],
                "description": "Honorarios del cierre contable mensual",
                "amount": "5800",
                "tax_rate": "0.16",
                "category_id": honorarios["id"],
            },
        )
        propuestas.append(("Agente Contable", creada["proposal_id"]))
    cierra()

    # ══════════════════════ AGENTE PATRIMONIAL ══════════════════════
    patrimonio = patrimonial.invoca("net_worth", {"months": 6})
    balance = patrimonial.invoca("balance_sheet")
    activos = {f["code"]: Decimal(str(f["amount"])) for f in balance["assets"]}
    pasivos = {f["code"]: Decimal(str(f["amount"])) for f in balance["liabilities"]}
    activo_fijo = activos.get("1400", Decimal("0"))
    depreciado = activos.get("1490", Decimal("0"))  # contra-activo: llega negativo
    prestamos = pasivos.get("2300", Decimal("0"))
    tarjetas = pasivos.get("2200", Decimal("0"))

    caja("AGENTE PATRIMONIAL · lo que tienes y lo que debes")
    linea(f"Patrimonio neto: {dinero(patrimonio['net_worth'])}")
    if activo_fijo:
        linea(f"Activo fijo: {dinero(activo_fijo)} (depreciación acumulada {dinero(abs(depreciado))})")
    if prestamos:
        linea(f"Préstamos por pagar: {dinero(prestamos)}")
    if tarjetas:
        linea(f"Tarjetas: {dinero(tarjetas)} — deuda cara; vigilar que no crezca")
    transporte = None
    for c in patrimonial.lista("list_categories", {"kind": "EXPENSE"}):
        if c["name"] in ("Transporte", "Otros Gastos"):
            transporte = c
            if c["name"] == "Transporte":
                break
    if activo_fijo > 0 and transporte:
        linea("→ Propone el mantenimiento preventivo del equipo rodante.")
        creada = patrimonial.invoca(
            "propose_expense",
            {
                "summary": "Mantenimiento preventivo de la camioneta (servicio semestral)",
                "evidence": (
                    f"El activo fijo en libros vale {dinero(activo_fijo + depreciado)} y se "
                    "deprecia cada mes; el plan de vida útil de 48 meses asume mantenimiento "
                    "al día. Saltarse el servicio abarata el mes y encarece el año."
                ),
                "date": hoy.isoformat(),
                "description": "Servicio preventivo camioneta de reparto",
                "amount": "4640",
                "tax_rate": "0.16",
                "category_id": transporte["id"],
            },
        )
        propuestas.append(("Agente Patrimonial", creada["proposal_id"]))
    cierra()

    # ══════════════════════ RESUMEN ══════════════════════
    caja("BANDEJA DE PROPUESTAS")
    linea(f"{len(propuestas)} propuesta(s) esperando decisión humana:")
    for autor, pid in propuestas:
        linea(f"  · {autor}  →  {pid}")
    linea()
    linea("Nadie escribió en la contabilidad. Abre Propuestas en ARCA:")
    linea("cada tarjeta trae su autor, su evidencia y sus botones.")
    cierra()


if __name__ == "__main__":
    main()
