"""El equipo de agentes residentes: cinco especialistas, cinco preguntas.

Cada agente responde UNA pregunta de negocio con números del libro:

- CFO           · ¿Cuándo entramos en zona crítica?   (runway, burn, escenarios)
- Treasury      · ¿Qué pagos priorizamos?             (nómina, impuestos, AP)
- Collections   · ¿Quién presiona la caja?            (AR, vencimientos, concentración)
- Accounting    · ¿Qué cambió este mes?               (variaciones, margen, gastos)
- Forecast      · ¿Qué pasa si contratamos?           (base, conservador, growth)

El razonamiento es determinista y auditable — cada cifra sale de los servicios
de reportes que ya tienen sus pruebas. La forma del brief es la de los
ejecutivos de Cortex ({headline, metrics, findings, recommendations}) para que
el día que un modelo tome el volante, la interfaz no cambie.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.reports import service as reports
from app.models.category import Category
from app.models.expense import Expense
from app.models.payable import Payable
from app.models.recurring import RecurringRule

AGENTS = (
    {
        "id": "cfo",
        "name": "CFO Agent",
        "question": "¿Cuándo entramos en zona crítica?",
        "topics": ["Runway", "burn", "escenarios"],
    },
    {
        "id": "treasury",
        "name": "Treasury Agent",
        "question": "¿Qué pagos priorizamos?",
        "topics": ["AP", "impuestos", "nómina"],
    },
    {
        "id": "collections",
        "name": "Collections Agent",
        "question": "¿Quién presiona la caja?",
        "topics": ["AR", "vencimientos", "concentración"],
    },
    {
        "id": "accounting",
        "name": "Accounting Agent",
        "question": "¿Qué cambió este mes?",
        "topics": ["Variaciones", "margen", "gastos"],
    },
    {
        "id": "forecast",
        "name": "Forecast Agent",
        "question": "¿Qué pasa si contratamos?",
        "topics": ["Base", "conservador", "growth"],
    },
)


def _money(value) -> str:
    return f"${Decimal(str(value)):,.0f}"


def _monthly_flows(db: Session, organization_id: str) -> tuple[Decimal, Decimal, Decimal]:
    """(entradas, salidas, neto) de EFECTIVO promedio mensual, últimos 90 días.

    Es flujo de caja, no estado de resultados: incluye préstamos recibidos y
    cobros de cartera. Para runway es la medida correcta; para hablar de
    "ingresos" del negocio está el Accounting Agent con el P&L.
    """
    series = reports.cash_series(db, organization_id, days=90)
    inflows = sum((Decimal(str(p["inflow"])) for p in series["points"]), Decimal("0"))
    outflows = sum((Decimal(str(p["outflow"])) for p in series["points"]), Decimal("0"))
    factor = Decimal("30") / Decimal("90")
    return inflows * factor, outflows * factor, (inflows - outflows) * factor


def _runway(cash: Decimal, monthly_net: Decimal) -> Decimal | None:
    """Meses de vida a un flujo neto dado. None si el flujo no quema caja."""
    if monthly_net >= 0:
        return None
    return (cash / -monthly_net).quantize(Decimal("0.1"))


# ══════════════════════════ CFO ══════════════════════════


def cfo_brief(db: Session, organization_id: str) -> dict:
    series = reports.cash_series(db, organization_id, days=90)
    projection = reports.cash_projection(db, organization_id, days=90)
    cash = Decimal(str(series["points"][-1]["balance"])) if series["points"] else Decimal("0")
    income, expense, net = _monthly_flows(db, organization_id)

    scenarios = []
    for label, factor in (("Base", Decimal("1")), ("Conservador (entradas −25%)", Decimal("0.75")), ("Estrés (entradas −50%)", Decimal("0.5"))):
        scenario_net = income * factor - expense
        runway = _runway(cash, scenario_net)
        scenarios.append(
            {
                "name": label,
                "monthly_net": scenario_net,
                "runway_months": runway,
            }
        )

    # Zona crítica: cuando quedaría menos de 3 meses de gasto en caja.
    critical_floor = expense * 3
    base = scenarios[0]
    if base["runway_months"] is None:
        headline = "Sin zona crítica a la vista: el flujo es positivo."
        critical_date = None
    else:
        months_to_critical = max(
            (cash - critical_floor) / (expense - income), Decimal("0")
        ) if expense > income else None
        critical_date = (
            (date_type.today() + timedelta(days=int(months_to_critical * 30)))
            if months_to_critical is not None
            else None
        )
        headline = (
            f"Zona crítica ≈ {critical_date.strftime('%d %b %Y')}: quedarían 3 meses de gasto en caja."
            if critical_date
            else "El burn actual consume la caja: revisar gastos ya."
        )

    findings = [
        f"Caja {_money(cash)} · entran {_money(income)}/mes · salen {_money(expense)}/mes (flujo de caja: incluye préstamos y cobros).",
    ]
    for scenario in scenarios:
        runway = scenario["runway_months"]
        findings.append(
            f"{scenario['name']}: neto {'+' if scenario['monthly_net'] >= 0 else '−'}{_money(abs(scenario['monthly_net']))}/mes → "
            + (f"runway {runway} meses." if runway is not None else "la caja crece, sin cuenta regresiva.")
        )
    if projection["shortfall_date"]:
        findings.append(
            f"Con los compromisos YA registrados, el saldo cruzaría a cero el {projection['shortfall_date']}."
        )

    return {
        "headline": headline,
        "metrics": [
            {"label": "Caja", "value": _money(cash)},
            {
                "label": "Burn neto",
                "value": ("+" if net >= 0 else "−") + _money(abs(net)) + "/mes",
                "tone": "pos" if net >= 0 else "neg",
            },
            {
                "label": "Runway base",
                "value": f"{base['runway_months']}m" if base["runway_months"] is not None else "∞",
            },
            {
                "label": "Zona crítica",
                "value": critical_date.strftime("%d %b") if critical_date else "no visible",
                "tone": "neg" if critical_date else "pos",
            },
        ],
        "findings": findings,
        "recommendations": [
            "Si el escenario conservador baja de 6 meses de runway, congelar gasto discrecional.",
            "Revisar esta pantalla cada lunes: la zona crítica se mueve con cada cobro.",
        ],
        "scenarios": scenarios,
    }


# ══════════════════════════ TREASURY ══════════════════════════


def treasury_brief(db: Session, organization_id: str) -> dict:
    today = date_type.today()
    horizon = today + timedelta(days=30)
    series = reports.cash_series(db, organization_id, days=30)
    cash = Decimal(str(series["points"][-1]["balance"])) if series["points"] else Decimal("0")

    # 1) Nómina: las reglas recurrentes de esa categoría son el compromiso más rígido.
    payroll_rules = (
        db.query(RecurringRule, Category.name)
        .join(Category, Category.id == RecurringRule.category_id)
        .filter(
            RecurringRule.organization_id == organization_id,
            RecurringRule.status == "ACTIVE",
        )
        .all()
    )
    payroll = sum(
        (Decimal(rule.amount) for rule, category in payroll_rules if category == "Nómina"),
        Decimal("0"),
    )
    other_recurring = sum(
        (Decimal(rule.amount) for rule, category in payroll_rules if category != "Nómina"),
        Decimal("0"),
    )

    # 2) Impuestos: lo que ya es del SAT, tomado del libro.
    from app.services.accounting.engine import trial_balance

    balance_rows = {row["code"]: row for row in trial_balance(db, organization_id)}

    def _liability(code: str) -> Decimal:
        row = balance_rows.get(code)
        if not row:
            return Decimal("0")
        return Decimal(str(row["credit"])) - Decimal(str(row["debit"]))

    taxes = _liability("2190") + _liability("2400") + _liability("2410")

    # 3) Proveedores por vencimiento.
    payables = (
        db.query(Payable)
        .filter(
            Payable.organization_id == organization_id,
            Payable.status.in_(("OPEN", "PARTIAL")),
            Payable.due_date <= horizon,
        )
        .order_by(Payable.due_date)
        .all()
    )
    ap_total = sum(
        (Decimal(p.amount) - Decimal(p.amount_paid) for p in payables), Decimal("0")
    )

    total = payroll + other_recurring + taxes + ap_total
    after = cash - total

    findings = [
        f"1º Nómina: {_money(payroll)} (recurrente; no se negocia).",
        f"2º Impuestos por enterar: {_money(taxes)} — IVA cobrado y retenciones ya son del SAT.",
        f"3º Proveedores 30 días: {_money(ap_total)} en {len(payables)} factura(s), por orden de vencimiento.",
    ]
    if other_recurring:
        findings.insert(1, f"1.5º Otros recurrentes (renta, servicios): {_money(other_recurring)}.")
    for payable in payables[:4]:
        saldo = Decimal(payable.amount) - Decimal(payable.amount_paid)
        findings.append(f"   · {payable.due_date.strftime('%d %b')} — {payable.description[:38]} ({_money(saldo)})")

    return {
        "headline": (
            f"Cubres los {_money(total)} de los próximos 30 días y te quedan {_money(after)}."
            if after >= 0
            else f"Los compromisos de 30 días ({_money(total)}) exceden la caja: prioriza en este orden."
        ),
        "metrics": [
            {"label": "Caja", "value": _money(cash)},
            {"label": "Nómina", "value": _money(payroll)},
            {"label": "Impuestos", "value": _money(taxes), "tone": "warn"},
            {"label": "Proveedores", "value": _money(ap_total)},
        ],
        "findings": findings,
        "recommendations": [
            "La nómina y el SAT no se difieren: cualquier ajuste sale de proveedores.",
            "Negociar plazo con el proveedor más grande vale más que retrasar tres chicos.",
        ],
    }


# ══════════════════════════ COLLECTIONS ══════════════════════════


def collections_brief(db: Session, organization_id: str) -> dict:
    aging = reports.aging_report(db, organization_id, "receivable")
    total = Decimal(str(aging["total"]))
    overdue = Decimal(str(aging["overdue"]))
    contacts = aging["contacts"]

    concentration = None
    if total > 0 and contacts:
        top = contacts[0]
        concentration = (Decimal(str(top["total"])) / total * 100).quantize(Decimal("0.1"))

    findings = []
    if overdue > 0:
        worst = max(contacts, key=lambda c: c["oldest_days"]) if contacts else None
        if worst:
            findings.append(
                f"{worst['name']} lleva {worst['oldest_days']} días de atraso — es quien más presiona la caja."
            )
    if concentration is not None and contacts:
        findings.append(
            f"Concentración: {contacts[0]['name']} es el {concentration}% de tu cartera"
            + (" — un solo cliente te puede secar la caja." if concentration > 50 else ".")
        )
    findings.append(
        f"DSO: te pagan en {aging['average_days']} días"
        + (
            f" ({'mejor' if aging['average_days'] <= aging['previous_average_days'] else 'peor'} que hace un mes: {aging['previous_average_days']})."
            if aging.get("previous_average_days") is not None
            else "."
        )
    )
    for bucket in aging["buckets"]:
        amount = Decimal(str(aging["totals"].get(bucket, 0)))
        if amount > 0 and bucket != "Por vencer":
            findings.append(f"Tramo {bucket} días: {_money(amount)} vencidos.")

    return {
        "headline": (
            f"{_money(overdue)} vencidos de {_money(total)} en la calle."
            if overdue > 0
            else f"Cartera sana: {_money(total)} en la calle, nada vencido."
        ),
        "metrics": [
            {"label": "Por cobrar", "value": _money(total)},
            {"label": "Vencido", "value": _money(overdue), "tone": "neg" if overdue > 0 else "pos"},
            {"label": "DSO", "value": f"{aging['average_days']}d"},
            {
                "label": "Concentración",
                "value": f"{concentration}%" if concentration is not None else "—",
                "tone": "warn" if concentration is not None and concentration > 50 else None,
            },
        ],
        "findings": findings,
        "recommendations": [
            "Llamada hoy al cliente con más días de atraso; el recargo de mora es palanca, no meta.",
            "Si un cliente pasa del 50% de la cartera, pedir anticipos en el siguiente contrato.",
        ],
    }


# ══════════════════════════ ACCOUNTING ══════════════════════════


def _category_totals(db: Session, organization_id: str, start: date_type, end: date_type) -> dict[str, Decimal]:
    rows = (
        db.query(Category.name, func.coalesce(func.sum(Expense.subtotal), 0))
        .join(Category, Category.id == Expense.category_id)
        .filter(
            Expense.organization_id == organization_id,
            Expense.status == "PAID",
            Expense.date >= start,
            Expense.date <= end,
        )
        .group_by(Category.name)
        .all()
    )
    return {name: Decimal(str(amount)) for name, amount in rows}


def accounting_brief(db: Session, organization_id: str) -> dict:
    today = date_type.today()
    start = today.replace(day=1)
    span = (today - start).days
    prev_end_month = start - timedelta(days=1)
    prev_start = prev_end_month.replace(day=1)
    prev_end = min(prev_start + timedelta(days=span), prev_end_month)

    current = reports.profit_loss(db, organization_id, start, today)
    previous = reports.profit_loss(db, organization_id, prev_start, prev_end)

    def _delta(now: Decimal, before: Decimal) -> str:
        if before == 0:
            return "nuevo" if now > 0 else "—"
        pct = ((now - before) / abs(before) * 100).quantize(Decimal("1"))
        return f"{'+' if pct >= 0 else ''}{pct}%"

    revenue_now = Decimal(str(current["total_revenue"]))
    revenue_prev = Decimal(str(previous["total_revenue"]))
    expense_now = Decimal(str(current["total_expenses"]))
    expense_prev = Decimal(str(previous["total_expenses"]))
    margin_now = (revenue_now - expense_now) / revenue_now * 100 if revenue_now else Decimal("0")
    margin_prev = (revenue_prev - expense_prev) / revenue_prev * 100 if revenue_prev else Decimal("0")

    cat_now = _category_totals(db, organization_id, start, today)
    cat_prev = _category_totals(db, organization_id, prev_start, prev_end)
    movements = sorted(
        (
            (name, cat_now.get(name, Decimal("0")) - cat_prev.get(name, Decimal("0")))
            for name in set(cat_now) | set(cat_prev)
        ),
        key=lambda item: abs(item[1]),
        reverse=True,
    )[:3]

    findings = [
        f"Ingresos {_money(revenue_now)} ({_delta(revenue_now, revenue_prev)} vs mismo corte del mes pasado).",
        f"Gastos {_money(expense_now)} ({_delta(expense_now, expense_prev)}).",
        f"Margen {margin_now.quantize(Decimal('0.1'))}% ({'+' if margin_now >= margin_prev else '−'}{abs(margin_now - margin_prev).quantize(Decimal('0.1'))} pts).",
    ]
    for name, delta in movements:
        if delta != 0:
            findings.append(
                f"{name}: {'subió' if delta > 0 else 'bajó'} {_money(abs(delta))} vs el corte anterior."
            )

    return {
        "headline": f"Margen {margin_now.quantize(Decimal('0.1'))}% este mes; el movimiento grande está en {movements[0][0] if movements else 'ninguna categoría'}.",
        "metrics": [
            {"label": "Ingresos", "value": _money(revenue_now), "hint": _delta(revenue_now, revenue_prev)},
            {"label": "Gastos", "value": _money(expense_now), "hint": _delta(expense_now, expense_prev)},
            {
                "label": "Margen",
                "value": f"{margin_now.quantize(Decimal('0.1'))}%",
                "tone": "pos" if margin_now >= margin_prev else "neg",
            },
        ],
        "findings": findings,
        "recommendations": [
            "Comparar contra el MISMO corte del mes anterior, nunca contra el mes completo.",
            "Un margen que cae dos meses seguidos es tendencia, no ruido.",
        ],
    }


# ══════════════════════════ FORECAST ══════════════════════════


def forecast_brief(
    db: Session, organization_id: str, monthly_cost: Decimal = Decimal("35000")
) -> dict:
    series = reports.cash_series(db, organization_id, days=90)
    cash = Decimal(str(series["points"][-1]["balance"])) if series["points"] else Decimal("0")
    income, expense, _net = _monthly_flows(db, organization_id)

    scenarios = []
    for name, hires, income_factor in (
        ("Base (sin contratar)", 0, Decimal("1")),
        ("Conservador (+1, entradas planas)", 1, Decimal("1")),
        ("Growth (+2, entradas +15%)", 2, Decimal("1.15")),
    ):
        scenario_net = income * income_factor - expense - monthly_cost * hires
        runway = _runway(cash, scenario_net)
        scenarios.append(
            {
                "name": name,
                "hires": hires,
                "monthly_net": scenario_net,
                "runway_months": runway,
            }
        )

    base, conservative, growth = scenarios
    findings = [
        f"Costo cargado por contratación: {_money(monthly_cost)}/mes ({_money(monthly_cost * 12)}/año).",
    ]
    for scenario in scenarios:
        runway = scenario["runway_months"]
        findings.append(
            f"{scenario['name']}: neto {'+' if scenario['monthly_net'] >= 0 else '−'}{_money(abs(scenario['monthly_net']))}/mes → "
            + (f"runway {runway} meses." if runway is not None else "la caja sigue creciendo.")
        )
    affordable = int(income - expense > 0 and (income - expense) / monthly_cost) if income - expense > 0 else 0

    return {
        "headline": (
            f"El flujo actual paga hasta {affordable} contratación(es) sin tocar la caja."
            if affordable > 0
            else "Contratar hoy saldría de la caja, no del flujo: revisar el escenario conservador."
        ),
        "metrics": [
            {"label": "Costo/hire", "value": _money(monthly_cost) + "/mes"},
            {
                "label": "Conservador",
                "value": f"{conservative['runway_months']}m runway"
                if conservative["runway_months"] is not None
                else "flujo +",
                "tone": None if conservative["runway_months"] is None else "warn",
            },
            {
                "label": "Growth",
                "value": f"{growth['runway_months']}m runway"
                if growth["runway_months"] is not None
                else "flujo +",
            },
            {"label": "Paga solas", "value": f"{affordable} hire(s)", "tone": "pos" if affordable else "neg"},
        ],
        "findings": findings,
        "recommendations": [
            "Contratar contra el flujo, no contra la caja: la caja es el colchón, no el sueldo.",
            "El escenario growth sólo vale si el +15% de entradas tiene nombre y apellido de cliente.",
        ],
        "scenarios": scenarios,
    }


BRIEF_BUILDERS = {
    "cfo": cfo_brief,
    "treasury": treasury_brief,
    "collections": collections_brief,
    "accounting": accounting_brief,
    "forecast": forecast_brief,
}


def build_brief(db: Session, organization_id: str, agent_id: str, **kwargs) -> dict:
    builder = BRIEF_BUILDERS.get(agent_id)
    if builder is None:
        raise ValueError("Ese agente no existe.")
    meta = next(agent for agent in AGENTS if agent["id"] == agent_id)
    brief = builder(db, organization_id, **kwargs)
    return {**meta, **brief, "generated_at": date_type.today().isoformat()}
