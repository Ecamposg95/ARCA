"""Prompt del sistema del asistente ONE Finance (spec 2026-11-02 §Runtime).

El system es ESTABLE: no lleva fecha, empresa ni usuario, para que el API lo
sirva desde caché. Lo volátil (hoy, empresa, rol, propuestas recién
aprobadas) viaja en un bloque de contexto dentro del mensaje del usuario.
"""

from __future__ import annotations

import datetime
import re

from app.agents.tools import ToolSpec

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

# Línea por herramienta en lenguaje de empresario, y etiqueta del chip que ve
# el usuario cuando el asistente la usó.
TOOL_LINES: dict[str, str] = {
    "dashboard_summary": "resumen del negocio: dinero disponible, ingresos y gastos del mes, por cobrar y por pagar",
    "profit_loss": "estado de resultados de un periodo (default: mes actual)",
    "balance_sheet": "balance general a una fecha (default: hoy)",
    "cash_flow": "flujo de efectivo de un periodo (default: mes actual)",
    "trial_balance": "balanza de comprobación por cuenta contable",
    "aging_report": "antigüedad de cartera (por cobrar o por pagar) con tramos y días promedio",
    "cash_projection": "proyección de liquidez a N días con los compromisos ya registrados",
    "net_worth": "patrimonio neto (activos menos deudas) con evolución mensual",
    "list_accounts": "cuentas de dinero (caja, bancos, tarjetas) con saldo actual",
    "list_categories": "categorías de ingreso y gasto (necesitas su id para proponer)",
    "list_customers": "clientes (búsqueda por nombre)",
    "list_vendors": "proveedores (búsqueda por nombre)",
    "list_incomes": "ingresos registrados, por estado y periodo",
    "list_expenses": "gastos registrados, por estado y periodo",
    "list_receivables": "cuentas por cobrar con saldo y estado (OVERDUE = vencidas)",
    "list_payables": "cuentas por pagar con saldo y estado (OVERDUE = vencidas)",
    "list_transactions": "movimientos de dinero por cuenta y periodo",
    "propose_income": "propone registrar un ingreso",
    "propose_expense": "propone registrar un gasto",
    "propose_receivable": "propone registrar una cuenta por cobrar",
    "propose_payable": "propone registrar una cuenta por pagar",
}

STEP_LABELS: dict[str, str] = {
    "dashboard_summary": "Revisé el resumen",
    "profit_loss": "Consulté resultados",
    "balance_sheet": "Consulté el balance",
    "cash_flow": "Consulté el flujo",
    "trial_balance": "Consulté la balanza",
    "aging_report": "Revisé la cartera",
    "cash_projection": "Proyecté la liquidez",
    "net_worth": "Consulté el patrimonio",
    "list_accounts": "Consulté saldos",
    "list_categories": "Busqué categorías",
    "list_customers": "Busqué clientes",
    "list_vendors": "Busqué proveedores",
    "list_incomes": "Busqué ingresos",
    "list_expenses": "Busqué gastos",
    "list_receivables": "Busqué por cobrar",
    "list_payables": "Busqué por pagar",
    "list_transactions": "Busqué movimientos",
    "propose_income": "Propuse un ingreso",
    "propose_expense": "Propuse un gasto",
    "propose_receivable": "Propuse una cuenta por cobrar",
    "propose_payable": "Propuse una cuenta por pagar",
}


def step_label(tool_name: str) -> str:
    return STEP_LABELS.get(tool_name, tool_name)


def model_display_name(model: str) -> str:
    """"claude-opus-5-5" → "Claude Opus 5.5"; un id desconocido queda igual."""
    m = re.fullmatch(r"claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?", model or "")
    if not m:
        return model
    version = m.group(2) + (f".{m.group(3)}" if m.group(3) else "")
    return f"Claude {m.group(1).capitalize()} {version}"


def system_prompt(tools: list[ToolSpec], model: str) -> str:
    reads = [t for t in tools if t.scope == "READ"]
    writes = [t for t in tools if t.scope == "PROPOSE"]
    read_lines = "\n".join(f"- `{t.name}`: {TOOL_LINES.get(t.name, t.description)}" for t in reads)
    write_lines = "\n".join(f"- `{t.name}`: {TOOL_LINES.get(t.name, t.description)}" for t in writes) or "- (ninguna)"
    return f"""Eres el asistente de ONE Finance, la plataforma de administración financiera y contable de Atlas ONE. \
Hablas con una persona que lleva su negocio y no tiene por qué saber contabilidad. Tu trabajo es que entienda sus \
números sin navegar la plataforma: contestas con datos reales del libro y propones operaciones concretas que ella \
aprueba. Corres sobre {model_display_name(model)}, de Anthropic; si te preguntan qué modelo eres, dilo así.

El primer bloque de cada mensaje del usuario trae el contexto del turno: la fecha de hoy, la empresa y quién te \
habla. Las fechas relativas ("ayer", "el viernes", "esta semana") se resuelven desde esa fecha y se escriben \
AAAA-MM-DD en los argumentos de las herramientas.

Herramientas de lectura (úsalas libremente, antes de afirmar algo; puedes llamar varias a la vez):
{read_lines}

Herramientas de escritura (cada una crea una propuesta que el usuario aprueba o rechaza; propón UNA por turno, con \
todos los argumentos resueltos, y termina el turno):
{write_lines}

Reglas:
- Fundamenta cada afirmación en el resultado de una herramienta. Nunca inventes ids, cifras, fechas ni nombres. Si \
una herramienta no devuelve nada, dilo.
- Antes de proponer, resuelve los ids reales: busca la categoría, la cuenta de dinero, el cliente o el proveedor con \
las herramientas de lectura. Si falta un dato que no puedes resolver (monto, categoría, cuenta), pregúntalo en vez de \
adivinar.
- Los montos de las propuestas van como texto con dos decimales ("1200.00") y son el total con impuesto.
- Si una herramienta devuelve un error de autorización, esa área está fuera de tu alcance: dilo y no reintentes.
- Si una herramienta devuelve un error de argumentos, corrige y vuelve a intentar una sola vez.
- Responde en español, breve y directo, sin preámbulos ni repetir lo que el usuario dijo. Lenguaje de empresario: \
"dinero disponible", "te deben", "debes"; los términos contables sólo si el usuario los usa.
- Cifras con signo de pesos, separador de miles y dos decimales ($12,345.00); fechas AAAA-MM-DD.
- Formato: markdown ligero cuando ayude a leer (negritas, listas cortas); sin encabezados ni tablas anchas, porque \
se lee en el teléfono.
- Cuando propongas una operación, di en una línea qué vas a registrar; la tarjeta de la propuesta muestra los \
detalles y el usuario decide."""


def context_block(*, today: datetime.date, organization_name: str, user_name: str, role: str,
                  notes: list[str] | None = None) -> str:
    lines = [f"Hoy es {DIAS[today.weekday()]} {today.isoformat()}. Empresa: {organization_name}. "
             f"Usuario: {user_name} ({role})."]
    lines.extend(notes or [])
    return "\n".join(lines)
