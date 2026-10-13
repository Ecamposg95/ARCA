"""Motor de reglas contables (task pack §18) — centralizado.

Cada evento de negocio tiene UNA función aquí que construye su póliza.
Prohibido armar asientos en routers o en el frontend.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.accounting import Account, JournalEntry, JournalEntryLine
from app.services.accounting.coa import (
    CODE_ACCOUNTS_PAYABLE,
    CODE_ACCOUNTS_RECEIVABLE,
    CODE_ACCUMULATED_DEPRECIATION,
    CODE_CAPITAL,
    CODE_CASH_BANK,
    CODE_CREDIT_CARDS,
    CODE_DEPRECIATION_EXPENSE,
    CODE_FIXED_ASSETS,
    CODE_INTEREST_EXPENSE,
    CODE_ISR_WITHHELD,
    CODE_LOANS_PAYABLE,
    CODE_RETAINED_EARNINGS,
    CODE_VAT_WITHHELD,
    CODE_VAT_CHARGED_COLLECTED,
    CODE_VAT_CHARGED_PENDING,
    CODE_VAT_CREDITABLE_PAID,
    CODE_VAT_CREDITABLE_PENDING,
)
from app.services.accounting.engine import (
    TWO_PLACES,
    YEAR_CLOSE_SOURCE,
    AccountingError,
    LineSpec,
    post_journal_entry,
)


def opening_balance_entry(
    db: Session,
    organization_id: str,
    account_name: str,
    amount: Decimal,
    date: date_type,
    source_id: str,
    created_by: str | None = None,
    account_code: str = CODE_CASH_BANK,
    liability: bool = False,
) -> JournalEntry:
    """Alta de instrumento con saldo inicial.

    Activo: Cargo al instrumento / Abono Capital (aportas dinero).
    Pasivo: Cargo Capital / Abono al instrumento (arrastras una deuda).
    """
    lines = (
        [
            LineSpec(CODE_CAPITAL, debit=amount, description="Deuda inicial"),
            LineSpec(account_code, credit=amount, description=account_name),
        ]
        if liability
        else [
            LineSpec(account_code, debit=amount, description=account_name),
            LineSpec(CODE_CAPITAL, credit=amount, description="Aportación inicial"),
        ]
    )
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=f"Saldo inicial de {account_name}",
        lines=lines,
        source_type="financial_account",
        source_id=source_id,
        created_by=created_by,
        kind="DIARIO",
    )


def income_paid_entry(
    db: Session,
    organization_id: str,
    description: str,
    amount: Decimal,
    date: date_type,
    revenue_account_code: str,
    source_id: str,
    created_by: str | None = None,
    cash_account_code: str = CODE_CASH_BANK,
    tax_amount: Decimal = Decimal("0"),
) -> JournalEntry:
    """Ingreso cobrado: Cargo Caja y Bancos (total) / Abono Ingresos (base) + IVA trasladado."""
    tax_amount = Decimal(tax_amount)
    lines = [
        LineSpec(cash_account_code, debit=amount),
        LineSpec(revenue_account_code, credit=amount - tax_amount),
    ]
    if tax_amount > 0:
        lines.append(LineSpec(CODE_VAT_CHARGED_COLLECTED, credit=tax_amount, description="IVA trasladado"))
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=lines,
        source_type="income",
        source_id=source_id,
        created_by=created_by,
        kind="INGRESO",
    )


def expense_paid_entry(
    db: Session,
    organization_id: str,
    description: str,
    amount: Decimal,
    date: date_type,
    expense_account_code: str,
    source_id: str,
    created_by: str | None = None,
    cash_account_code: str = CODE_CASH_BANK,
    tax_amount: Decimal = Decimal("0"),
    retention_isr: Decimal = Decimal("0"),
    retention_iva: Decimal = Decimal("0"),
) -> JournalEntry:
    """Gasto pagado: Cargo Gastos (base) + IVA acreditable / Abono Caja y Bancos.

    Con retenciones, al proveedor le sale menos dinero del que factura: la
    diferencia se queda como pasivo con el SAT hasta que se entera.
    """
    tax_amount = Decimal(tax_amount)
    retention_isr = Decimal(retention_isr)
    retention_iva = Decimal(retention_iva)
    withheld = retention_isr + retention_iva

    lines = [LineSpec(expense_account_code, debit=amount - tax_amount)]
    if tax_amount > 0:
        lines.append(LineSpec(CODE_VAT_CREDITABLE_PAID, debit=tax_amount, description="IVA acreditable"))
    if retention_isr > 0:
        lines.append(LineSpec(CODE_ISR_WITHHELD, credit=retention_isr, description="ISR retenido"))
    if retention_iva > 0:
        lines.append(LineSpec(CODE_VAT_WITHHELD, credit=retention_iva, description="IVA retenido"))
    lines.append(LineSpec(cash_account_code, credit=amount - withheld))
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=lines,
        source_type="expense",
        source_id=source_id,
        created_by=created_by,
        kind="EGRESO",
    )


def receivable_created_entry(
    db: Session,
    organization_id: str,
    description: str,
    amount: Decimal,
    date: date_type,
    revenue_account_code: str,
    source_id: str,
    created_by: str | None = None,
    tax_amount: Decimal = Decimal("0"),
) -> JournalEntry:
    """CxC emitida (devengo): Cargo CxC (total) / Abono Ingresos (base) + IVA pendiente de cobro."""
    tax_amount = Decimal(tax_amount)
    lines = [
        LineSpec(CODE_ACCOUNTS_RECEIVABLE, debit=amount),
        LineSpec(revenue_account_code, credit=amount - tax_amount),
    ]
    if tax_amount > 0:
        lines.append(
            LineSpec(CODE_VAT_CHARGED_PENDING, credit=tax_amount, description="IVA pendiente de cobro")
        )
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=lines,
        source_type="receivable",
        source_id=source_id,
        created_by=created_by,
        kind="DIARIO",
    )


def receivable_collected_entry(
    db: Session,
    organization_id: str,
    description: str,
    amount: Decimal,
    date: date_type,
    source_id: str,
    created_by: str | None = None,
    cash_account_code: str = CODE_CASH_BANK,
    tax_amount: Decimal = Decimal("0"),
) -> JournalEntry:
    """Cobro de CxC: Cargo Caja y Bancos / Abono CxC.

    El IVA proporcional pasa de "pendiente de cobro" a "cobrado": es hasta
    ahora cuando se declara ante el SAT.
    """
    tax_amount = Decimal(tax_amount)
    lines = [
        LineSpec(cash_account_code, debit=amount),
        LineSpec(CODE_ACCOUNTS_RECEIVABLE, credit=amount),
    ]
    if tax_amount > 0:
        lines.append(LineSpec(CODE_VAT_CHARGED_PENDING, debit=tax_amount, description="IVA ahora cobrado"))
        lines.append(LineSpec(CODE_VAT_CHARGED_COLLECTED, credit=tax_amount, description="IVA trasladado"))
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=lines,
        source_type="receivable",
        source_id=source_id,
        created_by=created_by,
        kind="INGRESO",
    )


def payable_created_entry(
    db: Session,
    organization_id: str,
    description: str,
    amount: Decimal,
    date: date_type,
    expense_account_code: str,
    source_id: str,
    created_by: str | None = None,
    tax_amount: Decimal = Decimal("0"),
) -> JournalEntry:
    """CxP registrada (devengo): Cargo Gastos (base) + IVA pendiente / Abono CxP (total)."""
    tax_amount = Decimal(tax_amount)
    lines = [LineSpec(expense_account_code, debit=amount - tax_amount)]
    if tax_amount > 0:
        lines.append(
            LineSpec(CODE_VAT_CREDITABLE_PENDING, debit=tax_amount, description="IVA pendiente de pago")
        )
    lines.append(LineSpec(CODE_ACCOUNTS_PAYABLE, credit=amount))
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=lines,
        source_type="payable",
        source_id=source_id,
        created_by=created_by,
        kind="DIARIO",
    )


def payable_payment_entry(
    db: Session,
    organization_id: str,
    description: str,
    amount: Decimal,
    date: date_type,
    source_id: str,
    created_by: str | None = None,
    cash_account_code: str = CODE_CASH_BANK,
    tax_amount: Decimal = Decimal("0"),
) -> JournalEntry:
    """Pago de CxP: Cargo CxP / Abono Caja y Bancos.

    El IVA proporcional pasa de "pendiente de pago" a acreditable: es hasta
    ahora cuando puede acreditarse.
    """
    tax_amount = Decimal(tax_amount)
    lines = [
        LineSpec(CODE_ACCOUNTS_PAYABLE, debit=amount),
        LineSpec(cash_account_code, credit=amount),
    ]
    if tax_amount > 0:
        lines.append(LineSpec(CODE_VAT_CREDITABLE_PAID, debit=tax_amount, description="IVA acreditable"))
        lines.append(
            LineSpec(CODE_VAT_CREDITABLE_PENDING, credit=tax_amount, description="IVA ya pagado")
        )
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=lines,
        source_type="payable",
        source_id=source_id,
        created_by=created_by,
        kind="EGRESO",
    )


REVERSAL_PREFIX = "reversal:"


def reversal_of(
    db: Session,
    organization_id: str,
    entry: JournalEntry,
    description: str,
    date: date_type,
    created_by: str | None = None,
    bypass_period_lock: bool = False,
) -> JournalEntry:
    """Asiento de reversa: las mismas líneas del original con cargo↔abono invertidos.

    Es la única forma correcta de 'deshacer' contabilidad: el original nunca
    se toca (task pack §27). `bypass_period_lock` sólo lo usa la reapertura de
    un ejercicio (ver `post_journal_entry`).
    """
    rows = (
        db.query(JournalEntryLine, Account.code)
        .join(Account, Account.id == JournalEntryLine.account_id)
        .filter(JournalEntryLine.journal_entry_id == entry.id)
        .all()
    )
    if not rows:
        raise ValueError("El asiento original no tiene líneas que revertir.")
    lines = [
        LineSpec(
            code,
            debit=Decimal(line.credit),
            credit=Decimal(line.debit),
            description=line.description,
        )
        for line, code in rows
    ]
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=lines,
        source_type=entry.source_type,
        source_id=entry.source_id,
        reference=f"{REVERSAL_PREFIX}{entry.id}",
        created_by=created_by,
        kind="DIARIO",
        bypass_period_lock=bypass_period_lock,
    )


def transfer_entry(
    db: Session,
    organization_id: str,
    description: str,
    amount: Decimal,
    date: date_type,
    from_account_name: str,
    to_account_name: str,
    source_id: str,
    created_by: str | None = None,
    from_account_code: str = CODE_CASH_BANK,
    to_account_code: str = CODE_CASH_BANK,
) -> JournalEntry:
    """Traspaso entre instrumentos propios.

    Entre dos activos es neutro. De banco a tarjeta es un PAGO de deuda:
    Cargo 2200 (debes menos) / Abono 1100 (tienes menos). No es un gasto:
    el gasto ocurrió cuando deslizaste la tarjeta.
    """
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=[
            LineSpec(to_account_code, debit=amount, description=f"Entrada a {to_account_name}"),
            LineSpec(from_account_code, credit=amount, description=f"Salida de {from_account_name}"),
        ],
        source_type="transfer",
        source_id=source_id,
        created_by=created_by,
        kind="DIARIO",
    )


def fixed_asset_purchase_entry(
    db: Session,
    organization_id: str,
    description: str,
    cost: Decimal,
    date: date_type,
    source_id: str,
    created_by: str | None = None,
    cash_account_code: str = CODE_CASH_BANK,
    tax_amount: Decimal = Decimal("0"),
) -> JournalEntry:
    """Compra de activo fijo: Cargo 1400 (costo) + IVA acreditable / Abono la cuenta.

    El costo NO pasa por gasto: se queda en el activo y se lleva a resultados
    mes a mes vía depreciación.
    """
    cost = Decimal(cost)
    tax_amount = Decimal(tax_amount)
    lines = [LineSpec(CODE_FIXED_ASSETS, debit=cost, description="Activo fijo")]
    if tax_amount > 0:
        lines.append(
            LineSpec(CODE_VAT_CREDITABLE_PAID, debit=tax_amount, description="IVA acreditable")
        )
    lines.append(LineSpec(cash_account_code, credit=cost + tax_amount))
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=lines,
        source_type="fixed_asset",
        source_id=source_id,
        created_by=created_by,
        kind="EGRESO",
    )


def depreciation_entry(
    db: Session,
    organization_id: str,
    description: str,
    amount: Decimal,
    date: date_type,
    source_id: str,
    created_by: str | None = None,
) -> JournalEntry:
    """Depreciación del mes: Cargo 5800 / Abono 1490 (acumulada).

    No mueve dinero: reconoce el desgaste. 1490 es contra-activo, así que restar
    del activo se logra abonando, nunca borrando el costo original.
    """
    amount = Decimal(amount)
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=[
            LineSpec(CODE_DEPRECIATION_EXPENSE, debit=amount),
            LineSpec(CODE_ACCUMULATED_DEPRECIATION, credit=amount, description="Depreciación acumulada"),
        ],
        source_type="depreciation",
        source_id=source_id,
        created_by=created_by,
        kind="DIARIO",
    )


def loan_received_entry(
    db: Session,
    organization_id: str,
    description: str,
    amount: Decimal,
    date: date_type,
    source_id: str,
    created_by: str | None = None,
    cash_account_code: str = CODE_CASH_BANK,
) -> JournalEntry:
    """Alta del crédito: Cargo la cuenta donde entró / Abono 2300.

    Recibir un préstamo no es ingreso: es dinero que entra y deuda que nace.
    """
    amount = Decimal(amount)
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=[
            LineSpec(cash_account_code, debit=amount),
            LineSpec(CODE_LOANS_PAYABLE, credit=amount, description="Préstamo por pagar"),
        ],
        source_type="loan",
        source_id=source_id,
        created_by=created_by,
        kind="INGRESO",
    )


def loan_payment_entry(
    db: Session,
    organization_id: str,
    description: str,
    principal: Decimal,
    interest: Decimal,
    date: date_type,
    source_id: str,
    created_by: str | None = None,
    cash_account_code: str = CODE_CASH_BANK,
) -> JournalEntry:
    """Pago del crédito: Cargo 2300 (capital) + 5900 (interés) / Abono la cuenta.

    Aquí vive la razón del módulo: sólo el interés es gasto. Tratar el pago
    completo como gasto infla los costos y deja la deuda inmóvil para siempre.
    """
    principal = Decimal(principal)
    interest = Decimal(interest)
    lines = [LineSpec(CODE_LOANS_PAYABLE, debit=principal, description="Capital")]
    if interest > 0:
        lines.append(LineSpec(CODE_INTEREST_EXPENSE, debit=interest, description="Intereses"))
    lines.append(LineSpec(cash_account_code, credit=principal + interest))
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=lines,
        source_type="loan_payment",
        source_id=source_id,
        created_by=created_by,
        kind="EGRESO",
    )


# --- Pólizas manuales (C-1) ---

# Cuentas que mantienen un saldo espejo fuera del ledger (instrumentos,
# cartera, activos fijos y préstamos). Una póliza manual contra ellas
# descuadraría ese espejo, así que se capturan desde su módulo.
MODULE_CONTROLLED_CODES = {
    CODE_CASH_BANK: "Movimientos",
    CODE_CREDIT_CARDS: "Movimientos",
    CODE_ACCOUNTS_RECEIVABLE: "Por cobrar",
    CODE_ACCOUNTS_PAYABLE: "Por pagar",
    CODE_FIXED_ASSETS: "Patrimonio",
    CODE_ACCUMULATED_DEPRECIATION: "Patrimonio",
    CODE_LOANS_PAYABLE: "Patrimonio",
}

MANUAL_SOURCE = "manual"
MAX_MANUAL_LINES = 100
OPENING_SOURCE = "opening"
# Pólizas que nacen a mano y por eso se revierten a mano desde el diario. Las
# de operaciones se cancelan en su módulo; la de cierre anual, reabriendo el año.
HAND_REVERSIBLE_SOURCES = (MANUAL_SOURCE, OPENING_SOURCE)


@dataclass(frozen=True)
class ManualLine:
    """Línea capturada por el contador: la cuenta viene por id, no por código."""

    account_id: str
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    description: str | None = None


def manual_entry(
    db: Session,
    organization_id: str,
    date: date_type,
    description: str,
    lines: list[ManualLine],
    reference: str | None = None,
    created_by: str | None = None,
) -> JournalEntry:
    """Póliza de diario capturada a mano.

    Valida lo propio de una captura manual (fecha, cuentas permitidas) y deja
    al motor lo demás: cuadre, montos, mes cerrado y folio. No hace commit.
    """
    if date > date_type.today():
        raise AccountingError("No se puede asentar una póliza con fecha futura.")
    description = (description or "").strip()
    if not description:
        raise AccountingError("La póliza necesita un concepto.")
    if not 2 <= len(lines) <= MAX_MANUAL_LINES:
        raise AccountingError(f"Una póliza lleva entre 2 y {MAX_MANUAL_LINES} líneas.")
    reference = (reference or "").strip() or None
    if reference and reference.startswith(REVERSAL_PREFIX):
        raise AccountingError(
            f"La referencia no puede empezar con '{REVERSAL_PREFIX}'; esa marca la pone ARCA al revertir."
        )

    wanted = {line.account_id for line in lines}
    accounts = {
        account.id: account
        for account in db.query(Account)
        .filter(Account.organization_id == organization_id, Account.id.in_(wanted))
        .all()
    }
    specs: list[LineSpec] = []
    for line in lines:
        account = accounts.get(line.account_id)
        if account is None:
            raise LookupError("Esa cuenta no existe.")
        if not account.active:
            raise AccountingError(f"La cuenta {account.code} está inactiva.")
        if account.parent_id is None:
            raise AccountingError(
                f"Las pólizas van a cuentas de detalle, no a la cuenta mayor {account.code}."
            )
        if account.code in MODULE_CONTROLLED_CODES:
            raise AccountingError(
                f"La cuenta {account.code} la mueven los módulos. Para bancos y tarjetas usa "
                "Movimientos; para cartera, Por cobrar y Por pagar; para activos fijos y "
                "préstamos, Patrimonio."
            )
        specs.append(
            LineSpec(account.code, debit=line.debit, credit=line.credit, description=line.description)
        )

    entry = post_journal_entry(
        db,
        organization_id,
        date=date,
        description=description,
        lines=specs,
        source_type=MANUAL_SOURCE,
        reference=reference,
        created_by=created_by,
        kind="DIARIO",
    )
    # El reverso la busca por (source_type, source_id) como a cualquier operación.
    entry.source_id = entry.id
    db.flush()
    return entry


def reverse_manual_entry(
    db: Session,
    organization_id: str,
    entry: JournalEntry,
    date: date_type,
    description: str | None = None,
    created_by: str | None = None,
) -> JournalEntry:
    """Reverso de una póliza manual o de apertura: espejo, una sola vez, nunca sobre un reverso.

    El reverso de una apertura lleva la fecha de la apertura: fechado después,
    los meses intermedios contarían dos aperturas. Por eso ignora la `date`
    recibida y usa `entry.date`; el candado de ejercicio del motor sigue aplicando.
    """
    if entry.source_type == YEAR_CLOSE_SOURCE:
        raise AccountingError("Una póliza de cierre se deshace reabriendo el ejercicio.")
    if entry.source_type not in HAND_REVERSIBLE_SOURCES:
        raise AccountingError("Esta póliza nació de una operación; cancélala desde su módulo.")
    if entry.reference and entry.reference.startswith(REVERSAL_PREFIX):
        raise AccountingError("Un reverso no se revierte; captura una póliza nueva.")
    if entry.status != "POSTED":
        raise AccountingError("Esta póliza no está contabilizada.")
    if entry.source_type == OPENING_SOURCE:
        date = entry.date
    else:
        if date < entry.date:
            raise AccountingError("El reverso no puede ser anterior a la póliza original.")
        if date > date_type.today():
            raise AccountingError("No se puede asentar una póliza con fecha futura.")
    already = (
        db.query(JournalEntry.id)
        .filter(JournalEntry.organization_id == organization_id, JournalEntry.reference == f"{REVERSAL_PREFIX}{entry.id}")
        .first()
    )
    if already is not None:
        raise AccountingError("Esta póliza ya fue revertida.")
    text = (description or "").strip() or f"Reverso de {entry.folio}: {entry.description}"
    return reversal_of(db, organization_id, entry, text[:500], date, created_by=created_by)


# --- Apertura (C-2) ---

# La cuenta contra la que cuadra la apertura: 3200 por defecto, 3100 si el
# contador prefiere llevar la diferencia a capital.
OPENING_BALANCING_CODES = (CODE_RETAINED_EARNINGS, CODE_CAPITAL)
BALANCE_SHEET_TYPES = ("ASSET", "LIABILITY", "EQUITY")
MAX_OPENING_LINES = 100


@dataclass(frozen=True)
class OpeningLine:
    """Saldo inicial de una cuenta, en su naturaleza (deudora o acreedora), >= 0."""

    account_id: str
    amount: Decimal


def opening_source_id(organization_id: str) -> str:
    return f"opening:{organization_id}"


def live_opening_entry(db: Session, organization_id: str) -> JournalEntry | None:
    """La apertura vigente: contabilizada, que no es un reverso y que nadie revirtió.

    El reverso conserva `source_type`/`source_id` (lo hace `reversal_of`), así
    que originales y reversos salen de la misma consulta y se separan por
    `reference`.
    """
    entries = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.organization_id == organization_id,
            JournalEntry.source_type == OPENING_SOURCE,
            JournalEntry.source_id == opening_source_id(organization_id),
            JournalEntry.status == "POSTED",
        )
        .order_by(JournalEntry.created_at.desc())
        .all()
    )
    reversed_ids = {
        entry.reference[len(REVERSAL_PREFIX):]
        for entry in entries
        if entry.reference and entry.reference.startswith(REVERSAL_PREFIX)
    }
    return next(
        (
            entry
            for entry in entries
            if not (entry.reference or "").startswith(REVERSAL_PREFIX) and entry.id not in reversed_ids
        ),
        None,
    )


def opening_entry(
    db: Session,
    organization_id: str,
    date: date_type,
    lines: list[OpeningLine],
    balancing_code: str = CODE_RETAINED_EARNINGS,
    description: str | None = None,
    created_by: str | None = None,
) -> JournalEntry:
    """Póliza de apertura: los saldos con los que la empresa llega a ARCA.

    Cada cuenta de balance entra en su naturaleza (activo al cargo; pasivo y
    capital al abono) y la diferencia va a la cuenta de cuadre. Las cuentas con
    saldo espejo abren desde su módulo. Una sola apertura viva por empresa; para
    corregirla se revierte y se captura otra. No hace commit.
    """
    if balancing_code not in OPENING_BALANCING_CODES:
        raise AccountingError("La apertura cuadra contra Resultados Acumulados (3200) o Capital (3100).")
    if date > date_type.today():
        raise AccountingError("No se puede asentar una póliza con fecha futura.")
    if len(lines) > MAX_OPENING_LINES:
        raise AccountingError(f"La apertura lleva hasta {MAX_OPENING_LINES} cuentas.")
    existing = live_opening_entry(db, organization_id)
    if existing is not None:
        raise AccountingError(
            f"Ya existe una póliza de apertura ({existing.folio}). Reviértela desde el diario para capturar otra."
        )

    wanted = {line.account_id for line in lines}
    accounts = {
        account.id: account
        for account in db.query(Account)
        .filter(Account.organization_id == organization_id, Account.id.in_(wanted))
        .all()
    }
    specs: list[LineSpec] = []
    seen: set[str] = set()
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for line in lines:
        account = accounts.get(line.account_id)
        if account is None:
            raise LookupError("Esa cuenta no existe.")
        if account.id in seen:
            raise AccountingError(f"La cuenta {account.code} aparece dos veces.")
        seen.add(account.id)
        if not account.active:
            raise AccountingError(f"La cuenta {account.code} está inactiva.")
        if account.parent_id is None:
            raise AccountingError(
                f"Las pólizas van a cuentas de detalle, no a la cuenta mayor {account.code}."
            )
        if account.type not in BALANCE_SHEET_TYPES:
            raise AccountingError("La apertura sólo lleva cuentas de balance; ingresos y gastos empiezan en cero.")
        if account.code in MODULE_CONTROLLED_CODES:
            raise AccountingError(
                f"La cuenta {account.code} abre desde su módulo: bancos y tarjetas en Movimientos, "
                "cartera en Por cobrar y Por pagar, activos fijos y préstamos en Patrimonio."
            )
        if account.code == balancing_code:
            raise AccountingError(f"La cuenta {account.code} es la de cuadre; su saldo se calcula.")
        amount = Decimal(line.amount).quantize(TWO_PLACES)
        if amount < 0:
            raise AccountingError("Los saldos iniciales no pueden ser negativos.")
        if amount == 0:
            continue  # una cuenta sin saldo no lleva línea
        if account.type == "ASSET":
            specs.append(LineSpec(account.code, debit=amount))
            total_debit += amount
        else:
            specs.append(LineSpec(account.code, credit=amount))
            total_credit += amount

    if not specs:
        raise AccountingError("Captura el saldo de al menos una cuenta.")
    residual = total_debit - total_credit
    if residual > 0:
        specs.append(LineSpec(balancing_code, credit=residual, description="Cuadre de la apertura"))
    elif residual < 0:
        specs.append(LineSpec(balancing_code, debit=-residual, description="Cuadre de la apertura"))

    text = (description or "").strip() or f"Saldos iniciales al {date:%d/%m/%Y}"
    return post_journal_entry(
        db,
        organization_id,
        date=date,
        description=text[:500],
        lines=specs,
        source_type=OPENING_SOURCE,
        source_id=opening_source_id(organization_id),
        created_by=created_by,
        kind="DIARIO",
    )


# --- Cierre de ejercicio (C-2) ---

RESULT_TYPES = ("REVENUE", "EXPENSE")


def year_close_entry(
    db: Session,
    organization_id: str,
    year: int,
    created_by: str | None = None,
) -> JournalEntry | None:
    """Póliza de cierre: deja en cero cada cuenta de resultados y traspasa la
    utilidad (o la pérdida) a Resultados Acumulados (3200), fechada el 31 de diciembre.

    El neto de cada cuenta incluye los cierres y reaperturas previos del mismo
    año, que se anulan entre sí: recerrar un año reabierto produce el cierre
    correcto. Sin cuentas con neto regresa None (el año se cierra sin póliza).
    Entra aunque diciembre esté cerrado por mes (`bypass_period_lock`): el
    módulo de periodos es dueño del candado. No hace commit.
    """
    start, end = date_type(year, 1, 1), date_type(year, 12, 31)
    rows = (
        db.query(
            Account.code,
            func.coalesce(func.sum(JournalEntryLine.debit), 0),
            func.coalesce(func.sum(JournalEntryLine.credit), 0),
        )
        .join(JournalEntryLine, JournalEntryLine.account_id == Account.id)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .filter(
            Account.organization_id == organization_id,
            Account.type.in_(RESULT_TYPES),
            Account.parent_id.isnot(None),
            JournalEntry.organization_id == organization_id,
            JournalEntry.status == "POSTED",
            JournalEntry.date >= start,
            JournalEntry.date <= end,
        )
        .group_by(Account.code)
        .order_by(Account.code)
        .all()
    )
    lines: list[LineSpec] = []
    result = Decimal("0")  # acreedor positivo: utilidad
    for code, debit, credit in rows:
        net = (Decimal(debit or 0) - Decimal(credit or 0)).quantize(TWO_PLACES)
        if net > 0:  # saldo deudor (gasto): se abona
            lines.append(LineSpec(code, credit=net))
            result -= net
        elif net < 0:  # saldo acreedor (ingreso): se carga
            lines.append(LineSpec(code, debit=-net))
            result += -net
    if not lines:
        return None
    if result > 0:
        lines.append(LineSpec(CODE_RETAINED_EARNINGS, credit=result, description="Utilidad del ejercicio"))
    elif result < 0:
        lines.append(LineSpec(CODE_RETAINED_EARNINGS, debit=-result, description="Pérdida del ejercicio"))
    return post_journal_entry(
        db,
        organization_id,
        date=end,
        description=f"Cierre del ejercicio {year}",
        lines=lines,
        source_type=YEAR_CLOSE_SOURCE,
        source_id=f"year_close:{year}",
        created_by=created_by,
        kind="DIARIO",
        bypass_period_lock=True,
    )
