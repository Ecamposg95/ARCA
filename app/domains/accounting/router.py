"""Sección Contabilidad (task pack §25) — solo OWNER / ADMIN / ACCOUNTANT."""

import re
from datetime import date as date_type
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.accounting import service
from app.models.accounting import Account, JournalEntry, JournalEntryLine
from app.models.organization import ACCOUNTING_ROLES, Organization
from app.security.deps import get_current_org_id, require_role
from app.services.accounting.contpaqi import ENCODING, ExportError, render
from app.services.accounting.sat import sat_code_names, sat_codes
from app.services.accounting.sat import (
    SatError,
    render_balanza,
    render_catalogo,
    sat_filename,
)
from app.services.accounting.engine import trial_balance as compute_trial_balance

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
    contpaqi_code: str | None
    sat_code: str | None


class JournalLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    debit: Decimal
    credit: Decimal
    description: str | None


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
    lines: list[JournalLineRead] = []


@router.get("/accounts", response_model=list[AccountRead])
def list_accounts(
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    accounts = (
        db.query(Account)
        .filter(Account.organization_id == org_id)
        .order_by(Account.code)
        .all()
    )
    return [AccountRead.model_validate(account) for account in accounts]


class AccountUpdate(BaseModel):
    contpaqi_code: str | None = None
    sat_code: str | None = None


@router.patch("/accounts/{account_id}", response_model=AccountRead)
def update_account(
    account_id: str,
    payload: AccountUpdate,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    """Lo editable de una cuenta: su equivalente en CONTPAQi y su código agrupador.
    Sólo cambia lo que viene en el cuerpo; un campo ausente no borra nada."""
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.organization_id == org_id)
        .first()
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Esa cuenta no existe.")

    if "contpaqi_code" in payload.model_fields_set:
        # Se guarda como la escribe el layout de CONTPAQi: sin guiones, puntos ni espacios.
        code = re.sub(r"[\s.\-]", "", payload.contpaqi_code or "")
        if code and not (code.isascii() and code.isalnum()):
            raise HTTPException(
                status_code=400,
                detail="El número de cuenta sólo puede llevar letras, números y guiones.",
            )
        if len(code) > 30:
            raise HTTPException(
                status_code=400, detail="El número de cuenta no puede pasar de 30 caracteres."
            )
        account.contpaqi_code = code or None

    if "sat_code" in payload.model_fields_set:
        sat_code = (payload.sat_code or "").strip()
        if sat_code and sat_code not in sat_code_names():
            raise HTTPException(
                status_code=400, detail="Ese código agrupador no existe en el catálogo del SAT."
            )
        account.sat_code = sat_code or None

    db.commit()
    db.refresh(account)
    return AccountRead.model_validate(account)


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
    entry_ids = [entry.id for entry in entries]
    lines_by_entry: dict[str, list[JournalLineRead]] = {}
    if entry_ids:
        lines = (
            db.query(JournalEntryLine)
            .filter(JournalEntryLine.journal_entry_id.in_(entry_ids))
            .all()
        )
        for line in lines:
            lines_by_entry.setdefault(line.journal_entry_id, []).append(JournalLineRead.model_validate(line))

    items = []
    for entry in entries:
        item = JournalEntryRead.model_validate(entry)
        item.lines = lines_by_entry.get(entry.id, [])
        items.append(item)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


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
