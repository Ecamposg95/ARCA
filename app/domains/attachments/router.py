"""Adjuntos de las operaciones (hoy: gastos).

Leer (listar, descargar) lo puede cualquier miembro, como ver el gasto; subir y
quitar exige los mismos roles que registrar gastos.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.attachments.schemas import AttachmentRead
from app.domains.periods.service import is_closed, is_year_closed
from app.models.attachment import Attachment
from app.models.expense import Expense
from app.models.organization import WRITE_ROLES
from app.models.user import User
from app.security.deps import get_current_org_id, get_current_user, require_role
from app.services import attachments as storage

router = APIRouter(tags=["attachments"])


def _expense(db: Session, org_id: str, expense_id: str) -> Expense:
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.organization_id == org_id).first()
    if expense is None:
        raise HTTPException(status_code=404, detail="El gasto no existe.")
    return expense


def _attachment(db: Session, org_id: str, attachment_id: str) -> Attachment:
    try:
        return storage.get(db, org_id, attachment_id)
    except storage.AttachmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/expenses/{expense_id}/attachments")
def list_expense_attachments(
    expense_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    expense = _expense(db, org_id, expense_id)
    rows = storage.list_for(db, org_id, "expense", expense.id)
    return {
        "items": [AttachmentRead.model_validate(row) for row in rows],
        "total": len(rows),
        "limit": storage.MAX_PER_OWNER,
        "offset": 0,
    }


@router.post("/expenses/{expense_id}/attachments", response_model=AttachmentRead, status_code=201)
def upload_expense_attachment(
    expense_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    expense = _expense(db, org_id, expense_id)
    # Un byte de más basta para saber que se pasó del límite sin leerlo todo.
    data = file.file.read(storage.MAX_FILE_BYTES + 1)
    try:
        attachment = storage.save(
            db,
            org_id,
            "expense",
            expense.id,
            file.filename or "archivo",
            file.content_type,
            data,
            uploaded_by=user.id,
        )
    except storage.AttachmentError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AttachmentRead.model_validate(attachment)


@router.get("/attachments/{attachment_id}/download")
def download_attachment(
    attachment_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    attachment = _attachment(db, org_id, attachment_id)
    try:
        data = storage.read_bytes(db, attachment)
    except storage.AttachmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    disposition = "inline" if attachment.content_type in storage.INLINE_TYPES else "attachment"
    ascii_name = attachment.filename.encode("ascii", "ignore").decode().replace('"', "") or "archivo"
    return Response(
        content=data,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": (
                f'{disposition}; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(attachment.filename)}'
            ),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/attachments/{attachment_id}", status_code=204)
def delete_attachment(
    attachment_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    attachment = _attachment(db, org_id, attachment_id)
    if attachment.owner_type == "expense":
        expense = _expense(db, org_id, attachment.owner_id)
        # La evidencia de un mes cerrado ya respaldó una declaración.
        year, month = expense.date.year, expense.date.month
        if is_closed(db, org_id, year, month) or is_year_closed(db, org_id, year):
            raise HTTPException(
                status_code=400,
                detail="El mes de este gasto está cerrado: reábrelo para quitar el adjunto.",
            )
    storage.soft_delete(db, attachment, user.id)
    return Response(status_code=204)
