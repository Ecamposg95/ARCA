"""Sección Contabilidad (task pack §25) — solo OWNER / ADMIN / ACCOUNTANT."""

import re
from datetime import date as date_type
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.accounting import service
from app.models.accounting import Account, JournalEntry, JournalEntryLine
from app.models.organization import ACCOUNTING_ROLES, Organization
from app.models.user import User
from app.security.deps import get_current_org_id, get_current_user, require_role
from app.services.accounting.coa import (
    account_has_movements,
    accounts_with_movements,
    create_account as create_catalog_account,
    rename_account,
    set_account_active,
)
from app.services.accounting.contpaqi import ENCODING, ExportError, render
from app.services.accounting.sat import sat_code_names, sat_codes
from app.services.accounting.sat import (
    SatError,
    render_balanza,
    render_catalogo,
    sat_filename,
)
from app.services.accounting.engine import trial_balance as compute_trial_balance
from app.services.accounting.rules import (
    MODULE_CONTROLLED_CODES,
    REVERSAL_PREFIX,
    ManualLine,
    manual_entry,
    reverse_manual_entry,
)

router = APIRouter(
    prefix="/accounting",
    tags=["accounting"],
    dependencies=[Depends(require_role(ACCOUNTING_ROLES))],
)


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    type: str
    parent_id: str | None
    active: bool
    system: bool
    contpaqi_code: str | None
    sat_code: str | None
    has_movements: bool = False
    # Acepta pólizas manuales: de detalle, activa y sin saldo espejo de un módulo.
    manual_allowed: bool = False


def _account_read(account: Account, has_movements: bool) -> AccountRead:
    item = AccountRead.model_validate(account)
    item.has_movements = has_movements
    item.manual_allowed = (
        account.parent_id is not None and account.active and account.code not in MODULE_CONTROLLED_CODES
    )
    return item


class JournalLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    debit: Decimal
    credit: Decimal
    description: str | None


class ReversalRef(BaseModel):
    """La póliza espejo que deshizo a otra: lo justo para enlazarla."""

    id: str
    folio: str
    date: date_type


class JournalEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    folio: str
    kind: str
    date: date_type
    description: str
    reference: str | None
    source_type: str | None
    source_id: str | None
    status: str
    reversed: bool = False
    reversal_of: str | None = None
    reversed_by: ReversalRef | None = None
    reversal_of_folio: str | None = None
    lines: list[JournalLineRead] = []


def _reversal_target(entry: JournalEntry) -> str | None:
    """Id de la póliza que este reverso deshace, o None si no es un reverso."""
    if entry.reference and entry.reference.startswith(REVERSAL_PREFIX):
        return entry.reference[len(REVERSAL_PREFIX):]
    return None


def _entries_read(db: Session, organization_id: str, entries: list[JournalEntry]) -> list[JournalEntryRead]:
    """Pólizas con sus líneas y el enlace con su reverso, en tres consultas como máximo.

    Todo por empresa: `reference` es texto libre y otra empresa no debe poder
    marcar ni nombrar una póliza ajena.
    """
    entry_ids = [entry.id for entry in entries]
    lines_by_entry: dict[str, list[JournalLineRead]] = {}
    reversed_by: dict[str, ReversalRef] = {}
    original_folios: dict[str, str] = {}
    if entry_ids:
        for line in db.query(JournalEntryLine).filter(JournalEntryLine.journal_entry_id.in_(entry_ids)).all():
            lines_by_entry.setdefault(line.journal_entry_id, []).append(JournalLineRead.model_validate(line))
        reversals = (
            db.query(JournalEntry.id, JournalEntry.folio, JournalEntry.date, JournalEntry.reference)
            .filter(
                JournalEntry.organization_id == organization_id,
                JournalEntry.reference.in_([f"{REVERSAL_PREFIX}{entry_id}" for entry_id in entry_ids]),
            )
            .order_by(JournalEntry.created_at)
            .all()
        )
        for reversal_id, folio, date, reference in reversals:
            reversed_by.setdefault(
                reference[len(REVERSAL_PREFIX):], ReversalRef(id=reversal_id, folio=folio, date=date)
            )
        original_ids = {target for target in map(_reversal_target, entries) if target}
        if original_ids:
            original_folios = dict(
                db.query(JournalEntry.id, JournalEntry.folio)
                .filter(JournalEntry.organization_id == organization_id, JournalEntry.id.in_(original_ids))
                .all()
            )
    items = []
    for entry in entries:
        item = JournalEntryRead.model_validate(entry)
        item.lines = lines_by_entry.get(entry.id, [])
        item.reversed_by = reversed_by.get(entry.id)
        item.reversed = item.reversed_by is not None
        item.reversal_of = _reversal_target(entry)
        if item.reversal_of:
            item.reversal_of_folio = original_folios.get(item.reversal_of)
        items.append(item)
    return items


def _entry_read(db: Session, organization_id: str, entry: JournalEntry) -> JournalEntryRead:
    return _entries_read(db, organization_id, [entry])[0]


@router.get("/accounts", response_model=list[AccountRead])
def list_accounts(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    accounts = db.query(Account).filter(Account.organization_id == org_id).order_by(Account.code).all()
    with_movements = accounts_with_movements(db, org_id)
    return [_account_read(account, account.id in with_movements) for account in accounts]


def _normalize_contpaqi_code(raw: str | None) -> str | None:
    # Se guarda como la escribe el layout de CONTPAQi: sin guiones, puntos ni espacios.
    code = re.sub(r"[\s.\-]", "", raw or "")
    if code and not (code.isascii() and code.isalnum()):
        raise HTTPException(status_code=400, detail="El número de cuenta sólo puede llevar letras, números y guiones.")
    if len(code) > 30:
        raise HTTPException(status_code=400, detail="El número de cuenta no puede pasar de 30 caracteres.")
    return code or None


def _validated_sat_code(raw: str | None) -> str | None:
    sat_code = (raw or "").strip()
    if sat_code and sat_code not in sat_code_names():
        raise HTTPException(status_code=400, detail="Ese código agrupador no existe en el catálogo del SAT.")
    return sat_code or None


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    active: bool | None = None
    contpaqi_code: str | None = None
    sat_code: str | None = None


@router.patch("/accounts/{account_id}", response_model=AccountRead)
def update_account(
    account_id: str,
    payload: AccountUpdate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Lo editable de una cuenta: nombre, activa, equivalente en CONTPAQi y código agrupador.
    Sólo cambia lo que viene en el cuerpo; un campo ausente no borra nada."""
    account = db.query(Account).filter(Account.id == account_id, Account.organization_id == org_id).first()
    if account is None:
        raise HTTPException(status_code=404, detail="Esa cuenta no existe.")
    try:
        if "name" in payload.model_fields_set:
            rename_account(account, payload.name or "")
        if "active" in payload.model_fields_set and payload.active is not None:
            set_account_active(db, account, payload.active)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if "contpaqi_code" in payload.model_fields_set:
        account.contpaqi_code = _normalize_contpaqi_code(payload.contpaqi_code)
    if "sat_code" in payload.model_fields_set:
        account.sat_code = _validated_sat_code(payload.sat_code)
    db.commit()
    db.refresh(account)
    return _account_read(account, account_has_movements(db, account.id))


class AccountCreate(BaseModel):
    parent_id: str = Field(min_length=1)
    code: str = Field(min_length=4, max_length=12)
    name: str = Field(min_length=1, max_length=255)
    sat_code: str | None = None
    contpaqi_code: str | None = None


@router.post("/accounts", response_model=AccountRead, status_code=201)
def create_account(
    payload: AccountCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Cuenta de detalle nueva bajo una cuenta mayor. El tipo lo fija la mayor."""
    sat_code = _validated_sat_code(payload.sat_code)
    contpaqi_code = _normalize_contpaqi_code(payload.contpaqi_code)
    try:
        account = create_catalog_account(
            db, org_id, payload.parent_id, payload.code, payload.name, sat_code=sat_code, contpaqi_code=contpaqi_code
        )
        db.commit()
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except IntegrityError as error:
        # Dos altas simultáneas del mismo código pasan la revisión previa; la
        # restricción uq_account_org_code frena a la segunda (al hacer flush o commit).
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Ya existe la cuenta {payload.code.strip()}.") from error
    db.refresh(account)
    return _account_read(account, False)


@router.get("/sat/codes")
def list_sat_codes():
    """La lista oficial del Anexo 24, para el selector del catálogo."""
    return sat_codes()


@router.get("/journal-entries")
def list_journal_entries(
    start: date_type | None = None,
    end: date_type | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    query = db.query(JournalEntry).filter(JournalEntry.organization_id == org_id)
    if start:
        query = query.filter(JournalEntry.date >= start)
    if end:
        query = query.filter(JournalEntry.date <= end)
    # Permite abrir "la contabilidad de ESTA operación" sin buscarla en el libro.
    if source_type:
        query = query.filter(JournalEntry.source_type == source_type)
    if source_id:
        query = query.filter(JournalEntry.source_id == source_id)
    query = query.order_by(JournalEntry.date.desc(), JournalEntry.created_at.desc())

    total = query.count()
    entries = query.limit(limit).offset(offset).all()
    items = _entries_read(db, org_id, entries)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/journal-entries/{entry_id}", response_model=JournalEntryRead)
def get_journal_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Una póliza por id: el diario la abre aunque no esté en la página visible."""
    entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id, JournalEntry.organization_id == org_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Esa póliza no existe.")
    return _entry_read(db, org_id, entry)


class JournalLineCreate(BaseModel):
    account_id: str = Field(min_length=1)
    # Centavos exactos desde la entrada: el motor redondea a dos decimales y un
    # tercer decimal podría cuadrar sólo después de redondear.
    debit: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2, allow_inf_nan=False)
    credit: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2, allow_inf_nan=False)
    description: str | None = Field(default=None, max_length=500)


class JournalEntryCreate(BaseModel):
    date: date_type
    description: str = Field(min_length=1, max_length=500)
    reference: str | None = Field(default=None, max_length=100)
    lines: list[JournalLineCreate] = Field(min_length=2, max_length=100)


@router.post("/journal-entries", response_model=JournalEntryRead, status_code=201)
def create_journal_entry(
    payload: JournalEntryCreate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
):
    """Póliza de diario capturada a mano. Las reglas viven en rules.manual_entry."""
    try:
        entry = manual_entry(
            db,
            org_id,
            date=payload.date,
            description=payload.description,
            lines=[ManualLine(l.account_id, l.debit, l.credit, l.description) for l in payload.lines],
            reference=payload.reference,
            created_by=user.id,
        )
    except LookupError as error:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error
    db.commit()
    db.refresh(entry)
    return _entry_read(db, org_id, entry)



class ReverseRequest(BaseModel):
    date: date_type
    description: str | None = Field(default=None, max_length=500)


@router.post("/journal-entries/{entry_id}/reverse", response_model=JournalEntryRead, status_code=201)
def reverse_journal_entry(
    entry_id: str,
    payload: ReverseRequest,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
):
    """Deshacer es revertir: la póliza espejo se emite y la original queda."""
    # FOR UPDATE: dos reversos simultáneos se serializan aquí; el segundo espera
    # el commit del primero y su consulta "ya fue revertida" ya ve el espejo.
    entry = (
        db.query(JournalEntry)
        .filter(JournalEntry.id == entry_id, JournalEntry.organization_id == org_id)
        .with_for_update()
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Esa póliza no existe.")
    try:
        reversal = reverse_manual_entry(
            db, org_id, entry, date=payload.date, description=payload.description, created_by=user.id
        )
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error
    db.commit()
    db.refresh(reversal)
    return _entry_read(db, org_id, reversal)


@router.get("/trial-balance")
def trial_balance(
    as_of: date_type | None = None,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    rows = compute_trial_balance(db, org_id, as_of)
    return {
        "rows": rows,
        "total_debit": sum((row["debit"] for row in rows), Decimal("0")),
        "total_credit": sum((row["credit"] for row in rows), Decimal("0")),
    }


@router.get("/contpaqi/preview")
def contpaqi_preview(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Qué saldría en el archivo, para avisar antes de descargar."""
    vouchers, unmapped = service.month_vouchers(db, org_id, year, month)
    return {
        "year": year,
        "month": month,
        "entries": len(vouchers),
        "movements": sum(
            1 for voucher in vouchers for m in voucher.movements if m.debit > 0 or m.credit > 0
        ),
        "unmapped_accounts": unmapped,
    }


@router.get("/contpaqi")
def contpaqi_export(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Las pólizas del mes en el layout de "Cargado de pólizas" de CONTPAQi."""
    vouchers, _unmapped = service.month_vouchers(db, org_id, year, month)
    if not vouchers:
        raise HTTPException(status_code=404, detail="No hay pólizas en ese mes.")
    try:
        content = render(vouchers)
    except ExportError as error:
        # Nunca un archivo a medias ni con un dato recortado: se detiene todo.
        raise HTTPException(status_code=409, detail=str(error)) from error
    return Response(
        content=content.encode(ENCODING),
        media_type="text/plain; charset=windows-1252",
        headers={
            "Content-Disposition": f'attachment; filename="polizas-contpaqi-{year}-{month:02d}.txt"'
        },
    )


def _sat_ready(db: Session, org_id: str, year: int, month: int) -> tuple[str, dict]:
    """RFC válido y todas las cuentas clasificadas, o 400 diciendo qué falta."""
    organization = db.get(Organization, org_id)
    requirements = service.sat_requirements(db, organization, year, month)
    if not requirements["rfc_ok"]:
        raise HTTPException(
            status_code=400,
            detail="Captura el RFC de la empresa en Configuración antes de generar los XML del SAT.",
        )
    if requirements["missing_accounts"]:
        codes = ", ".join(a["code"] for a in requirements["missing_accounts"][:10])
        raise HTTPException(
            status_code=400,
            detail=f"Hay cuentas sin código agrupador del SAT: {codes}. Asígnalo en el catálogo.",
        )
    return requirements["rfc"], requirements


def _xml_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/sat/preview")
def sat_preview(
    year: int = Query(ge=2015, le=2100),
    month: int = Query(ge=1, le=12),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    organization = db.get(Organization, org_id)
    return service.sat_requirements(db, organization, year, month)


@router.get("/sat/catalogo")
def sat_catalogo(
    year: int = Query(ge=2015, le=2100),
    month: int = Query(ge=1, le=12),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Catálogo de cuentas del Anexo 24, sin sellar."""
    rfc, _requirements = _sat_ready(db, org_id, year, month)
    xml = render_catalogo(rfc, year, month, service.sat_catalog(db, org_id))
    return _xml_response(xml, sat_filename(rfc, year, month, "CT"))


@router.get("/sat/balanza")
def sat_balanza(
    year: int = Query(ge=2015, le=2100),
    month: int = Query(ge=1, le=12),
    tipo: str = Query(default="N", pattern="^[NC]$"),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Balanza de comprobación del Anexo 24 (N normal, C complementaria), sin sellar."""
    rfc, _requirements = _sat_ready(db, org_id, year, month)
    try:
        rows = service.sat_balance(db, org_id, year, month)
    except SatError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    xml = render_balanza(rfc, year, month, tipo, rows)
    return _xml_response(xml, sat_filename(rfc, year, month, f"B{tipo}"))
