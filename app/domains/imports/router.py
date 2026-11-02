from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.imports import service
from app.domains.imports.schemas import ImportBatchDetail, ImportBatchRead, ImportRowRead, MappingRequest
from app.models.import_batch import ImportBatch
from app.models.organization import WRITE_ROLES
from app.models.user import User
from app.schemas.common import paginate
from app.security.deps import get_current_org_id, get_current_user, require_role

router = APIRouter(prefix="/imports", tags=["imports"])

ROW_STATUS_PATTERN = "^(OK|ERROR|DUPLICATE|SKIPPED|CREATED)$"


def _load(db: Session, org_id: str, batch_id: str) -> ImportBatch:
    try:
        return service.get_batch(db, org_id, batch_id)
    except service.ImportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _detail(db: Session, org_id: str, batch: ImportBatch, status: str | None, limit: int, offset: int) -> dict:
    query = service.batch_rows(db, org_id, batch.id)
    if status:
        from app.models.import_batch import ImportRow

        query = query.filter(ImportRow.status == status)
    page = paginate(query, limit, offset, ImportRowRead)
    detail = ImportBatchRead.model_validate(batch).model_dump()
    detail["rows"] = page
    return ImportBatchDetail.model_validate(detail).model_dump()


@router.get("")
def list_batches(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    query = (
        db.query(ImportBatch)
        .filter(ImportBatch.organization_id == org_id)
        .order_by(ImportBatch.created_at.desc())
    )
    return paginate(query, limit, offset, ImportBatchRead)


@router.post("", status_code=201)
def upload(
    file: UploadFile = File(...),
    kind: str = Form(...),
    sheet: str | None = Form(default=None),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    content = file.file.read(service.MAX_FILE_BYTES + 1)
    try:
        batch = service.create_batch(
            db, org_id, kind, file.filename or "archivo", content, sheet or None, created_by=user.id
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _detail(db, org_id, batch, None, service.PREVIEW_LIMIT, 0)


@router.get("/{batch_id}")
def get_batch(
    batch_id: str,
    status: str | None = Query(default=None, pattern=ROW_STATUS_PATTERN),
    limit: int = Query(default=service.PREVIEW_LIMIT, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
):
    batch = _load(db, org_id, batch_id)
    return _detail(db, org_id, batch, status, limit, offset)


@router.post("/{batch_id}/map")
def map_batch(
    batch_id: str,
    payload: MappingRequest,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    batch = _load(db, org_id, batch_id)
    try:
        batch = service.apply_mapping(db, org_id, batch, payload.mapping, payload.defaults)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _detail(db, org_id, batch, None, service.PREVIEW_LIMIT, 0)


@router.post("/{batch_id}/confirm")
def confirm_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    batch = _load(db, org_id, batch_id)
    try:
        batch = service.confirm_batch(db, org_id, batch, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _detail(db, org_id, batch, None, service.PREVIEW_LIMIT, 0)


@router.post("/{batch_id}/discard", response_model=ImportBatchRead)
def discard_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    _membership=Depends(require_role(WRITE_ROLES)),
):
    batch = _load(db, org_id, batch_id)
    try:
        batch = service.discard_batch(db, org_id, batch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportBatchRead.model_validate(batch)
