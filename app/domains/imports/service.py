"""Importación con vista previa: Toronja y archivos de Excel/CSV.

Flujo: subir → clasificar cada fila (OK / ERROR / DUPLICATE / SKIPPED) → el
usuario revisa → confirmar crea las operaciones de las filas OK en UNA
transacción (todas o ninguna) a través de los services de ingresos, gastos y
cuentas por cobrar: aquí no se arma ningún asiento ni se toca un saldo.

Privacidad: el `payload` de una fila de Toronja nunca lleva `CLIENTE` ni
`ESTUDIOS`; el parser ya no los entrega y aquí no se vuelven a leer.
"""

from __future__ import annotations

import hashlib
from datetime import date as date_type
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domains.expenses.schemas import ExpenseCreate
from app.domains.expenses.service import build_expense
from app.domains.imports.schemas import DEFAULT_FIELDS, MAPPING_FIELDS
from app.domains.income.schemas import IncomeCreate
from app.domains.income.service import build_income
from app.domains.receivables.schemas import ReceivableCreate
from app.domains.receivables.service import build_receivable
from app.models.business_unit import BusinessUnit
from app.models.category import Category
from app.models.contact import Customer
from app.models.financial_account import ASSET_ACCOUNT_TYPES, FinancialAccount
from app.models.fiscal_entity import FiscalEntity
from app.models.import_batch import IMPORT_KINDS, ImportBatch, ImportRow
from app.models.organization import Organization
from app.services.accounting.engine import ClosedPeriodError, _assert_period_open
from app.services.dimensions import normalize_alias
from app.services.imports.tabular import TabularFormatError, read_table
from app.services.imports.toronja import ToronjaFormatError, parse_toronja
from app.services.imports.values import clean_text, parse_date, parse_money

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_ROWS = 50_000
PREVIEW_LIMIT = 200
GENERIC_KINDS = ("INCOMES", "EXPENSES", "CASH")
TORONJA_SUPPORT_VENDOR = "SOPORTE TECNICO DEL SISTEMA"
TORONJA_CUSTOMER_NAME = "Pacientes (Toronja)"
DEFAULT_INCOME_CATEGORY = "Ventas"
RECEIVABLE_DAYS = 30
# Cuentas donde puede caer dinero cobrado. `PROCESSOR` (procesador de tarjetas)
# lo introduce otro bloque: si el tipo no existe aún, cualquier cuenta de dinero
# de activo sirve como procesador.
MONEY_ACCOUNT_TYPES = tuple(ASSET_ACCOUNT_TYPES) + ("PROCESSOR",)

# Forma de pago de Toronja → (clave del payload con la cuenta, método del movimiento, etiqueta)
TORONJA_FORMS = (
    ("cash", "cash_account_id", "EFECTIVO", "efectivo"),
    ("card", "processor_account_id", "TARJETA", "tarjeta"),
    ("transfer", "bank_account_id", "TRANSFERENCIA", "transferencia"),
)
PAYMENT_METHOD_ALIASES = {
    "EFECTIVO": "EFECTIVO",
    "CASH": "EFECTIVO",
    "TRANSFERENCIA": "TRANSFERENCIA",
    "SPEI": "TRANSFERENCIA",
    "TARJETA": "TARJETA",
    "TARJETA DEBITO": "TARJETA_DEBITO",
    "TARJETA DE DEBITO": "TARJETA_DEBITO",
    "DEBITO": "TARJETA_DEBITO",
    "TARJETA CREDITO": "TARJETA_CREDITO",
    "TARJETA DE CREDITO": "TARJETA_CREDITO",
    "CREDITO": "TARJETA_CREDITO",
    "DOMICILIACION": "DOMICILIACION",
    "CHEQUE": "CHEQUE",
    "PASARELA": "PASARELA",
}


class ImportNotFoundError(LookupError):
    pass


# --- Utilidades ---------------------------------------------------------------


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date_type)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _money(payload: dict, key: str) -> Decimal:
    return Decimal(str(payload.get(key) or "0"))


def _two(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"))


def _hash_external_id(when: date_type, amount: Decimal, description: str) -> str:
    key = f"{when.isoformat()}|{_two(amount)}|{normalize_alias(description)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:40]


def _summarize(rows: list[ImportRow], operations: int | None = None) -> dict:
    counts = {"OK": 0, "ERROR": 0, "DUPLICATE": 0, "SKIPPED": 0, "CREATED": 0}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    return {
        "rows": len(rows),
        "ok": counts["OK"],
        "errors": counts["ERROR"],
        "duplicates": counts["DUPLICATE"],
        "skipped": counts["SKIPPED"],
        "created": counts["CREATED"],
        "operations": operations if operations is not None else counts["OK"],
    }


def get_batch(db: Session, org_id: str, batch_id: str) -> ImportBatch:
    batch = (
        db.query(ImportBatch).filter(ImportBatch.id == batch_id, ImportBatch.organization_id == org_id).first()
    )
    if batch is None:
        raise ImportNotFoundError("Esa importación no existe.")
    return batch


def batch_rows(db: Session, org_id: str, batch_id: str):
    """Query de las filas del lote, en orden del archivo; el router pagina."""
    return (
        db.query(ImportRow)
        .filter(ImportRow.batch_id == batch_id, ImportRow.organization_id == org_id)
        .order_by(ImportRow.row_number.asc())
    )


def _created_external_ids(db: Session, org_id: str, kind: str) -> set[str]:
    rows = (
        db.query(ImportRow.external_id)
        .filter(
            ImportRow.organization_id == org_id,
            ImportRow.kind == kind,
            ImportRow.status == "CREATED",
            ImportRow.external_id.isnot(None),
        )
        .all()
    )
    return {external_id for (external_id,) in rows}


class _PeriodCheck:
    """Un mes cerrado se consulta una vez por lote, no una vez por fila."""

    def __init__(self, db: Session, org_id: str) -> None:
        self.db = db
        self.org_id = org_id
        self.cache: dict[tuple[int, int], str | None] = {}

    def closed_message(self, when: date_type) -> str | None:
        key = (when.year, when.month)
        if key not in self.cache:
            try:
                _assert_period_open(self.db, self.org_id, when)
                self.cache[key] = None
            except ClosedPeriodError as exc:
                self.cache[key] = f"Mes cerrado: {exc}"
        return self.cache[key]


def _unit_index(db: Session, org_id: str) -> dict[str, BusinessUnit]:
    """Nombre y alias normalizados → unidad activa."""
    index: dict[str, BusinessUnit] = {}
    units = (
        db.query(BusinessUnit)
        .filter(BusinessUnit.organization_id == org_id, BusinessUnit.active.is_(True))
        .order_by(BusinessUnit.sort_order, BusinessUnit.name)
        .all()
    )
    for unit in units:
        index.setdefault(normalize_alias(unit.name), unit)
        index.setdefault(normalize_alias(unit.code), unit)
        for alias in unit.aliases or []:
            index.setdefault(normalize_alias(alias), unit)
    return index


def _cash_by_unit(db: Session, org_id: str) -> dict[str, FinancialAccount]:
    """La caja de cada unidad: la primera cuenta CASH activa por nombre."""
    accounts = (
        db.query(FinancialAccount)
        .filter(
            FinancialAccount.organization_id == org_id,
            FinancialAccount.type == "CASH",
            FinancialAccount.active.is_(True),
            FinancialAccount.deleted_at.is_(None),
            FinancialAccount.business_unit_id.isnot(None),
        )
        .order_by(FinancialAccount.name)
        .all()
    )
    result: dict[str, FinancialAccount] = {}
    for account in accounts:
        result.setdefault(account.business_unit_id, account)
    return result


def _money_account(db: Session, org_id: str, account_id: str | None) -> FinancialAccount | None:
    if not account_id:
        return None
    return (
        db.query(FinancialAccount)
        .filter(
            FinancialAccount.id == account_id,
            FinancialAccount.organization_id == org_id,
            FinancialAccount.type.in_(MONEY_ACCOUNT_TYPES),
            FinancialAccount.active.is_(True),
            FinancialAccount.deleted_at.is_(None),
        )
        .first()
    )


def _category(db: Session, org_id: str, category_id: str | None, kind: str) -> Category | None:
    if not category_id:
        return None
    return (
        db.query(Category)
        .filter(
            Category.id == category_id,
            Category.organization_id == org_id,
            Category.kind == kind,
            Category.active.is_(True),
        )
        .first()
    )


def _category_by_name(db: Session, org_id: str, name: str, kind: str) -> Category | None:
    wanted = normalize_alias(name)
    for category in (
        db.query(Category)
        .filter(Category.organization_id == org_id, Category.kind == kind, Category.active.is_(True))
        .all()
    ):
        if normalize_alias(category.name) == wanted:
            return category
    return None


def _customer(db: Session, org_id: str, customer_id: str | None) -> Customer | None:
    if not customer_id:
        return None
    return (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.organization_id == org_id, Customer.deleted_at.is_(None))
        .first()
    )


# --- Ajustes por empresa ------------------------------------------------------


def get_import_settings(db: Session, org_id: str) -> dict:
    organization = db.get(Organization, org_id)
    settings = dict(organization.import_settings or {})
    settings.setdefault("toronja", {})
    return settings


def update_import_settings(db: Session, org_id: str, toronja: dict | None) -> dict:
    """Valida que cada id sea de la empresa y del tipo correcto antes de guardarlo."""
    organization = db.get(Organization, org_id)
    settings = dict(organization.import_settings or {})
    if toronja is not None:
        current = dict(settings.get("toronja") or {})
        for key in ("bank_account_id", "processor_account_id"):
            if key in toronja:
                value = toronja[key]
                if value and _money_account(db, org_id, value) is None:
                    raise ValueError("Esa cuenta de dinero no existe o no sirve para recibir cobros.")
                current[key] = value or None
        if "receivable_customer_id" in toronja:
            value = toronja["receivable_customer_id"]
            if value and _customer(db, org_id, value) is None:
                raise ValueError("Ese cliente no existe.")
            current["receivable_customer_id"] = value or None
        if "income_category_id" in toronja:
            value = toronja["income_category_id"]
            if value and _category(db, org_id, value, "INCOME") is None:
                raise ValueError("Esa categoría de ingreso no existe.")
            current["income_category_id"] = value or None
        settings["toronja"] = current
    organization.import_settings = settings
    db.commit()
    db.refresh(organization)
    return get_import_settings(db, org_id)


def _resolved_toronja_settings(db: Session, org_id: str) -> dict:
    """Ids efectivos para Toronja (con los defaults sembrados) o None por cada uno."""
    raw = get_import_settings(db, org_id).get("toronja") or {}
    bank = _money_account(db, org_id, raw.get("bank_account_id"))
    processor = _money_account(db, org_id, raw.get("processor_account_id"))
    category = _category(db, org_id, raw.get("income_category_id"), "INCOME") or _category_by_name(
        db, org_id, DEFAULT_INCOME_CATEGORY, "INCOME"
    )
    customer = _customer(db, org_id, raw.get("receivable_customer_id"))
    return {
        "bank_account_id": bank.id if bank else None,
        "processor_account_id": processor.id if processor else None,
        "income_category_id": category.id if category else None,
        "receivable_customer_id": customer.id if customer else None,
    }


# --- Subir ---------------------------------------------------------------------


def create_batch(
    db: Session,
    org_id: str,
    kind: str,
    filename: str,
    content: bytes,
    sheet: str | None,
    created_by: str,
) -> ImportBatch:
    if kind not in IMPORT_KINDS:
        raise ValueError("Formato de importación desconocido.")
    if not content:
        raise ValueError("El archivo está vacío.")
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("El archivo pesa más de 20 MB.")

    batch = ImportBatch(
        organization_id=org_id,
        kind=kind,
        filename=(filename or "archivo")[:255],
        status="PREVIEW",
        mapping={},
        options={},
        summary={},
        created_by=created_by,
    )
    db.add(batch)
    db.flush()

    if kind == "TORONJA":
        try:
            parsed = parse_toronja(content)
        except ToronjaFormatError as exc:
            raise ValueError(str(exc)) from exc
        if len(parsed) > MAX_ROWS:
            raise ValueError("El archivo tiene más de 50,000 filas.")
        rows = _classify_toronja(db, org_id, batch, parsed)
        operations = _count_toronja_operations(rows)
    else:
        try:
            table = read_table(content, filename, sheet)
        except TabularFormatError as exc:
            raise ValueError(str(exc)) from exc
        if len(table.rows) > MAX_ROWS:
            raise ValueError("El archivo tiene más de 50,000 filas.")
        batch.options = {"columns": table.columns, "sheets": table.sheets, "sheet": table.sheet, "defaults": {}}
        rows = []
        for raw in table.rows:
            row_number = raw.pop("_row_number")
            rows.append(
                ImportRow(
                    organization_id=org_id,
                    batch_id=batch.id,
                    kind=kind,
                    row_number=row_number,
                    payload={"raw": {k: _jsonable(v) for k, v in raw.items()}},
                    status="SKIPPED",
                    message="Sin mapeo de columnas.",
                )
            )
        operations = 0

    db.add_all(rows)
    batch.summary = _summarize(rows, operations)
    db.commit()
    db.refresh(batch)
    return batch


# --- Toronja: clasificación ---------------------------------------------------


def _classify_toronja(db: Session, org_id: str, batch: ImportBatch, parsed: list[dict]) -> list[ImportRow]:
    settings = _resolved_toronja_settings(db, org_id)
    units = _unit_index(db, org_id)
    cash_by_unit = _cash_by_unit(db, org_id)
    created = _created_external_ids(db, org_id, "TORONJA")
    periods = _PeriodCheck(db, org_id)
    seen: set[str] = set()
    rows: list[ImportRow] = []

    for item in parsed:
        payload = {
            "folio": item.get("folio"),
            "date": _jsonable(item.get("date")),
            "vendor": item.get("vendor"),
            "cash": _jsonable(item.get("cash")),
            "debit_card": _jsonable(item.get("debit_card")),
            "credit_card": _jsonable(item.get("credit_card")),
            "transfer": _jsonable(item.get("transfer")),
            "credit": _jsonable(item.get("credit")),
            "discount": _jsonable(item.get("discount")),
            "debt": _jsonable(item.get("debt")),
            "gran_total": _jsonable(item.get("gran_total")),
            "total": _jsonable(item.get("total")),
            "cancelled": item.get("cancelled") or "",
            "cancelled_by": item.get("cancelled_by") or "",
            "edited": item.get("edited") or "",
        }
        row = ImportRow(
            organization_id=org_id,
            batch_id=batch.id,
            kind="TORONJA",
            row_number=item.get("row_number", 0),
            external_id=(item.get("folio") or None),
            payload=payload,
        )
        rows.append(row)
        status, message = _classify_toronja_row(item, payload, settings, units, cash_by_unit, created, seen, periods)
        row.status, row.message = status, message
    return rows


def _classify_toronja_row(item, payload, settings, units, cash_by_unit, created, seen, periods) -> tuple[str, str | None]:
    if item.get("error"):
        return "ERROR", f"No se pudo leer la fila: {item['error']}"
    folio = item.get("folio") or ""
    if not folio:
        return "ERROR", "Fila sin folio."
    if item.get("cancelled"):
        return "SKIPPED", "Ticket cancelado."
    vendor = item.get("vendor") or ""
    if normalize_alias(vendor) == TORONJA_SUPPORT_VENDOR:
        return "SKIPPED", "Soporte técnico del sistema."

    cash = item.get("cash") or Decimal("0")
    card = (item.get("debit_card") or Decimal("0")) + (item.get("credit_card") or Decimal("0"))
    transfer = item.get("transfer") or Decimal("0")
    owed = (item.get("credit") or Decimal("0")) + (item.get("debt") or Decimal("0"))
    gran_total = item.get("gran_total") or Decimal("0")
    if gran_total == 0 and owed == 0 and cash + card + transfer == 0:
        return "SKIPPED", "Ticket en cero."
    if folio in seen:
        return "DUPLICATE", "Folio repetido en el archivo."
    seen.add(folio)
    if folio in created:
        return "DUPLICATE", "Este folio ya se importó antes."

    unit = units.get(normalize_alias(vendor))
    if unit is None:
        return "ERROR", f"Vendedor sin unidad: {vendor}. Agrégalo como alias en Configuración."
    payload["unit_id"] = unit.id
    payload["unit_name"] = unit.name
    payload["unit_code"] = unit.code

    closed = periods.closed_message(item["date"])
    if closed:
        return "ERROR", closed

    if settings["income_category_id"] is None:
        return "ERROR", "No hay una categoría de ingreso para las ventas. Elígela en Configuración → Importación."
    payload["category_id"] = settings["income_category_id"]

    if cash > 0:
        account = cash_by_unit.get(unit.id)
        if account is None:
            return "ERROR", f"La unidad {unit.name} no tiene caja."
        payload["cash_account_id"] = account.id
    if card > 0:
        if settings["processor_account_id"] is None:
            return "ERROR", "Configura la cuenta del procesador de tarjetas en Configuración → Importación."
        payload["processor_account_id"] = settings["processor_account_id"]
    if transfer > 0:
        if settings["bank_account_id"] is None:
            return "ERROR", "Configura la cuenta de banco para transferencias en Configuración → Importación."
        payload["bank_account_id"] = settings["bank_account_id"]
    payload["card"] = str(_two(card))
    payload["owed"] = str(_two(owed))
    return "OK", None


def _toronja_groups(rows: list[ImportRow]) -> tuple[dict, dict]:
    """Ingresos por (unidad, fecha, forma) y adeudos por (unidad, fecha), a partir de filas OK."""
    incomes: dict[tuple, dict] = {}
    receivables: dict[tuple, dict] = {}
    for row in rows:
        payload = row.payload
        for amount_key, account_key, method, label in TORONJA_FORMS:
            amount = _money(payload, amount_key)
            if amount <= 0:
                continue
            key = (payload["unit_id"], payload["date"], method)
            group = incomes.setdefault(
                key,
                {
                    "unit_id": payload["unit_id"],
                    "unit_name": payload["unit_name"],
                    "unit_code": payload.get("unit_code") or payload["unit_name"],
                    "date": payload["date"],
                    "method": method,
                    "label": label,
                    "account_id": payload[account_key],
                    "category_id": payload["category_id"],
                    "amount": Decimal("0"),
                    "rows": [],
                },
            )
            group["amount"] += amount
            group["rows"].append(row)
        owed = _money(payload, "owed")
        if owed > 0:
            key = (payload["unit_id"], payload["date"])
            group = receivables.setdefault(
                key,
                {
                    "unit_id": payload["unit_id"],
                    "unit_name": payload["unit_name"],
                    "date": payload["date"],
                    "category_id": payload["category_id"],
                    "amount": Decimal("0"),
                    "rows": [],
                },
            )
            group["amount"] += owed
            group["rows"].append(row)
    return incomes, receivables


def _count_toronja_operations(rows: list[ImportRow]) -> int:
    incomes, receivables = _toronja_groups([row for row in rows if row.status == "OK"])
    return len(incomes) + len(receivables)


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _ensure_toronja_customer(db: Session, org_id: str, customer_id: str | None) -> str:
    customer = _customer(db, org_id, customer_id)
    if customer is None:
        customer = (
            db.query(Customer)
            .filter(
                Customer.organization_id == org_id,
                Customer.name == TORONJA_CUSTOMER_NAME,
                Customer.deleted_at.is_(None),
            )
            .first()
        )
    if customer is None:
        customer = Customer(
            organization_id=org_id,
            name=TORONJA_CUSTOMER_NAME,
            notes="Adeudos de pacientes importados del reporte de ventas de Toronja.",
        )
        db.add(customer)
        db.flush()
    return customer.id


def _confirm_toronja(db: Session, org_id: str, batch: ImportBatch, rows: list[ImportRow], user_id: str) -> int:
    ok_rows = [row for row in rows if row.status == "OK"]
    incomes, receivables = _toronja_groups(ok_rows)
    results: dict[str, list[dict]] = {row.id: [] for row in ok_rows}
    created = 0

    for group in incomes.values():
        when = date_type.fromisoformat(group["date"])
        n = len(group["rows"])
        payload = IncomeCreate(
            date=when,
            description=f"Ventas Toronja · {group['unit_name']} · {group['label']} · {_plural(n, 'ticket', 'tickets')}",
            amount=_two(group["amount"]),
            tax_rate=Decimal("0"),
            category_id=group["category_id"],
            business_unit_id=group["unit_id"],
            financial_account_id=group["account_id"],
            payment_method=group["method"],
            reference=f"toronja:{group['date']}:{group['unit_code']}:{group['label']}"[:100],
            status="PAID",
        )
        income = build_income(db, org_id, payload, created_by=user_id)
        income.paid_at = datetime.combine(when, time.min, tzinfo=timezone.utc)
        created += 1
        for row in group["rows"]:
            results[row.id].append({"type": "income", "id": income.id})

    customer_id = None
    if receivables:
        customer_id = _ensure_toronja_customer(db, org_id, _resolved_toronja_settings(db, org_id)["receivable_customer_id"])
    for group in receivables.values():
        when = date_type.fromisoformat(group["date"])
        n = len(group["rows"])
        payload = ReceivableCreate(
            customer_id=customer_id,
            description=f"Adeudos Toronja · {group['unit_name']} · {group['date']} · {_plural(n, 'folio', 'folios')}",
            amount=_two(group["amount"]),
            tax_rate=Decimal("0"),
            date=when,
            due_date=when + timedelta(days=RECEIVABLE_DAYS),
            category_id=group["category_id"],
            business_unit_id=group["unit_id"],
        )
        receivable = build_receivable(db, org_id, payload, created_by=user_id)
        created += 1
        for row in group["rows"]:
            results[row.id].append({"type": "receivable", "id": receivable.id})

    for row in ok_rows:
        made = results[row.id]
        if not made:
            row.status, row.message = "SKIPPED", "Sin montos que registrar."
            continue
        row.status = "CREATED"
        row.message = None
        row.result_type, row.result_id = made[0]["type"], made[0]["id"]
        row.payload = {**row.payload, "results": made}
    return created


# --- Genérico: mapeo y clasificación -------------------------------------------


def _normalize_payment_method(value) -> str | None:
    text = normalize_alias(clean_text(value))
    if not text:
        return None
    return PAYMENT_METHOD_ALIASES.get(text, text[:20])


def apply_mapping(db: Session, org_id: str, batch: ImportBatch, mapping: dict, defaults: dict) -> ImportBatch:
    if batch.kind not in GENERIC_KINDS:
        raise ValueError("El reporte de Toronja no necesita mapeo de columnas.")
    if batch.status != "PREVIEW":
        raise ValueError("Esta importación ya se cerró.")
    columns = set(batch.options.get("columns") or [])

    clean_mapping = {k: v for k, v in mapping.items() if v}
    unknown = [k for k in clean_mapping if k not in MAPPING_FIELDS]
    if unknown:
        raise ValueError(f"Campo de mapeo desconocido: {', '.join(unknown)}.")
    missing_cols = [v for v in clean_mapping.values() if v not in columns]
    if missing_cols:
        raise ValueError(f"El archivo no tiene la columna {missing_cols[0]}.")
    if "fecha" not in clean_mapping or "concepto" not in clean_mapping:
        raise ValueError("Indica qué columna es la fecha y cuál es el concepto.")
    two_columns = "ingreso" in clean_mapping or "egreso" in clean_mapping
    if batch.kind == "CASH" and two_columns:
        if not ("ingreso" in clean_mapping and "egreso" in clean_mapping):
            raise ValueError("Para efectivo indica la columna de entradas y la de salidas, o una sola con signo.")
    elif "monto" not in clean_mapping:
        raise ValueError("Indica qué columna es el monto.")

    clean_defaults = {k: v for k, v in defaults.items() if v}
    unknown = [k for k in clean_defaults if k not in DEFAULT_FIELDS]
    if unknown:
        raise ValueError(f"Valor por defecto desconocido: {', '.join(unknown)}.")
    resolved_defaults = _resolve_defaults(db, org_id, batch.kind, clean_defaults)

    rows = batch_rows(db, org_id, batch.id).all()
    units = _unit_index(db, org_id)
    created = _created_external_ids(db, org_id, batch.kind)
    periods = _PeriodCheck(db, org_id)
    accounts = {
        normalize_alias(a.name): a
        for a in db.query(FinancialAccount)
        .filter(
            FinancialAccount.organization_id == org_id,
            FinancialAccount.active.is_(True),
            FinancialAccount.deleted_at.is_(None),
        )
        .all()
    }
    entities = {
        normalize_alias(e.name): e
        for e in db.query(FiscalEntity)
        .filter(FiscalEntity.organization_id == org_id, FiscalEntity.active.is_(True))
        .all()
    }
    categories = {
        kind: {
            normalize_alias(c.name): c
            for c in db.query(Category)
            .filter(Category.organization_id == org_id, Category.kind == kind, Category.active.is_(True))
            .all()
        }
        for kind in ("INCOME", "EXPENSE")
    }
    seen: set[str] = set()
    for row in rows:
        raw = dict(row.payload.get("raw") or {})
        payload = {"raw": raw}
        row.result_type = row.result_id = None
        row.status, row.message = _classify_generic_row(
            batch.kind, raw, clean_mapping, resolved_defaults, payload, units, accounts, entities, categories, created, seen, periods
        )
        row.external_id = payload.get("external_id")
        row.payload = payload

    batch.mapping = clean_mapping
    batch.options = {**batch.options, "defaults": clean_defaults}
    batch.summary = _summarize(rows)
    db.commit()
    db.refresh(batch)
    return batch


def _resolve_defaults(db: Session, org_id: str, kind: str, defaults: dict) -> dict:
    resolved: dict = {}
    for key, category_kind in (
        ("category_id", "INCOME" if kind == "INCOMES" else "EXPENSE"),
        ("income_category_id", "INCOME"),
        ("expense_category_id", "EXPENSE"),
    ):
        if defaults.get(key):
            if _category(db, org_id, defaults[key], category_kind) is None:
                raise ValueError("La categoría por defecto no existe.")
            resolved[key] = defaults[key]
    if defaults.get("financial_account_id"):
        account = (
            db.query(FinancialAccount)
            .filter(
                FinancialAccount.id == defaults["financial_account_id"],
                FinancialAccount.organization_id == org_id,
                FinancialAccount.active.is_(True),
                FinancialAccount.deleted_at.is_(None),
            )
            .first()
        )
        if account is None:
            raise ValueError("La cuenta de dinero por defecto no existe.")
        if kind == "CASH" and account.type != "CASH":
            raise ValueError("Para efectivo elige una caja.")
        resolved["financial_account_id"] = account.id
    if defaults.get("business_unit_id"):
        unit = (
            db.query(BusinessUnit)
            .filter(
                BusinessUnit.id == defaults["business_unit_id"],
                BusinessUnit.organization_id == org_id,
                BusinessUnit.active.is_(True),
            )
            .first()
        )
        if unit is None:
            raise ValueError("La unidad por defecto no existe.")
        resolved["business_unit_id"] = unit.id
    return resolved


def _classify_generic_row(
    kind, raw, mapping, defaults, payload, units, accounts, entities, categories, created, seen, periods
) -> tuple[str, str | None]:
    def cell(field: str):
        column = mapping.get(field)
        return raw.get(column) if column else None

    try:
        when = parse_date(cell("fecha"))
    except ValueError as exc:
        return "ERROR", str(exc)
    payload["date"] = when.isoformat()

    description = clean_text(cell("concepto"))
    if not description:
        return "ERROR", "Falta el concepto."
    payload["description"] = description[:500]

    try:
        if kind == "CASH" and "ingreso" in mapping:
            inflow = parse_money(cell("ingreso"))
            outflow = parse_money(cell("egreso"))
            if inflow > 0 and outflow > 0:
                return "ERROR", "La fila trae entrada y salida a la vez."
            amount, direction = (inflow, "INCOME") if inflow > 0 else (outflow, "EXPENSE")
        else:
            signed = parse_money(cell("monto"))
            if kind == "INCOMES":
                amount, direction = abs(signed), "INCOME"
            elif kind == "EXPENSES":
                amount, direction = abs(signed), "EXPENSE"
            else:
                amount, direction = abs(signed), ("INCOME" if signed > 0 else "EXPENSE")
    except ValueError as exc:
        return "ERROR", str(exc)
    if amount <= 0:
        return "ERROR", "El monto debe ser mayor a cero."
    payload["amount"] = str(_two(amount))
    payload["direction"] = direction

    external_id = _hash_external_id(when, amount, description)
    payload["external_id"] = external_id
    if external_id in seen:
        return "DUPLICATE", "Repetido en el archivo."
    seen.add(external_id)
    if external_id in created:
        return "DUPLICATE", "Esta operación ya se importó antes."

    closed = periods.closed_message(when)
    if closed:
        return "ERROR", closed

    category_kind = "INCOME" if direction == "INCOME" else "EXPENSE"
    category_name = clean_text(cell("categoria"))
    category = categories[category_kind].get(normalize_alias(category_name)) if category_name else None
    if category is not None:
        payload["category_id"], payload["category_name"] = category.id, category.name
    elif category_name:
        return "ERROR", f"La categoría {category_name} no existe."
    else:
        default_key = "category_id" if kind != "CASH" else ("income_category_id" if direction == "INCOME" else "expense_category_id")
        if not defaults.get(default_key):
            return "ERROR", "Falta la categoría: mapea una columna o elige una por defecto."
        payload["category_id"] = defaults[default_key]

    account_name = clean_text(cell("cuenta"))
    account = accounts.get(normalize_alias(account_name)) if account_name else None
    if account is not None:
        if kind == "CASH" and account.type != "CASH":
            return "ERROR", f"{account.name} no es una caja."
        payload["financial_account_id"], payload["account_name"] = account.id, account.name
    elif account_name:
        return "ERROR", f"La cuenta {account_name} no existe."
    elif defaults.get("financial_account_id"):
        payload["financial_account_id"] = defaults["financial_account_id"]
    else:
        return "ERROR", "Falta la cuenta de dinero: mapea una columna o elige una por defecto."

    unit_name = clean_text(cell("unidad"))
    if unit_name:
        unit = units.get(normalize_alias(unit_name))
        if unit is None:
            return "ERROR", f"Unidad desconocida: {unit_name}. Agrégala como alias en Configuración."
        payload["business_unit_id"], payload["unit_name"] = unit.id, unit.name
    elif defaults.get("business_unit_id"):
        payload["business_unit_id"] = defaults["business_unit_id"]

    entity_name = clean_text(cell("contribuyente"))
    if entity_name:
        entity = entities.get(normalize_alias(entity_name))
        if entity is None:
            return "ERROR", f"Contribuyente desconocido: {entity_name}."
        payload["fiscal_entity_id"], payload["entity_name"] = entity.id, entity.name

    reference = clean_text(cell("referencia"))
    if reference:
        payload["reference"] = reference[:100]
    method = _normalize_payment_method(cell("forma_pago"))
    if method:
        payload["payment_method"] = method
    return "OK", None


def _confirm_generic(db: Session, org_id: str, batch: ImportBatch, rows: list[ImportRow], user_id: str) -> int:
    created = 0
    for row in rows:
        if row.status != "OK":
            continue
        payload = row.payload
        when = date_type.fromisoformat(payload["date"])
        if payload["direction"] == "INCOME":
            income = build_income(
                db,
                org_id,
                IncomeCreate(
                    date=when,
                    description=payload["description"],
                    amount=Decimal(payload["amount"]),
                    tax_rate=Decimal("0"),
                    category_id=payload["category_id"],
                    business_unit_id=payload.get("business_unit_id"),
                    fiscal_entity_id=payload.get("fiscal_entity_id"),
                    financial_account_id=payload["financial_account_id"],
                    payment_method=payload.get("payment_method"),
                    reference=payload.get("reference"),
                    status="PAID",
                ),
                created_by=user_id,
            )
            income.paid_at = datetime.combine(when, time.min, tzinfo=timezone.utc)
            row.result_type, row.result_id = "income", income.id
        else:
            expense = build_expense(
                db,
                org_id,
                ExpenseCreate(
                    date=when,
                    description=payload["description"],
                    amount=Decimal(payload["amount"]),
                    tax_rate=Decimal("0"),
                    category_id=payload["category_id"],
                    business_unit_id=payload.get("business_unit_id"),
                    fiscal_entity_id=payload.get("fiscal_entity_id"),
                    financial_account_id=payload["financial_account_id"],
                    payment_method=payload.get("payment_method"),
                    reference=payload.get("reference"),
                    status="PAID",
                ),
                created_by=user_id,
            )
            expense.paid_at = datetime.combine(when, time.min, tzinfo=timezone.utc)
            row.result_type, row.result_id = "expense", expense.id
        row.status, row.message = "CREATED", None
        created += 1
    return created


# --- Confirmar / descartar ----------------------------------------------------


def confirm_batch(db: Session, org_id: str, batch: ImportBatch, user_id: str) -> ImportBatch:
    """Crea las operaciones de las filas OK: todas o ninguna."""
    if batch.status == "CONFIRMED":
        raise ValueError("Esta importación ya se hizo.")
    if batch.status == "DISCARDED":
        raise ValueError("Esta importación se descartó; vuelve a subir el archivo.")

    rows = batch_rows(db, org_id, batch.id).all()
    # Alguien pudo confirmar otro lote con los mismos folios entre la vista previa y ahora.
    already = _created_external_ids(db, org_id, batch.kind)
    for row in rows:
        if row.status == "OK" and row.external_id and row.external_id in already:
            row.status, row.message = "DUPLICATE", "Este folio ya se importó antes."

    try:
        if batch.kind == "TORONJA":
            created = _confirm_toronja(db, org_id, batch, rows, user_id)
        else:
            created = _confirm_generic(db, org_id, batch, rows, user_id)
        batch.status = "CONFIRMED"
        batch.confirmed_at = datetime.now(timezone.utc)
        batch.summary = {**_summarize(rows, created), "created": created}
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise ValueError(f"No se importó nada: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - todo o nada; el detalle va al log
        db.rollback()
        raise ValueError("No se importó nada: ocurrió un error inesperado al crear las operaciones.") from exc
    db.refresh(batch)
    return batch


def discard_batch(db: Session, org_id: str, batch: ImportBatch) -> ImportBatch:
    if batch.status == "CONFIRMED":
        raise ValueError("Esta importación ya se hizo; cancela sus operaciones una por una si hace falta.")
    batch.status = "DISCARDED"
    db.commit()
    db.refresh(batch)
    return batch
