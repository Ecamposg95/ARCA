"""Adjuntos: validación y almacenamiento de la evidencia de una operación.

Hoy los bytes viven en PostgreSQL (`attachment_blobs`) porque el disco de
Railway es efímero y aún no hay bucket. Este módulo es el único que los lee o
escribe: mudarlos a S3 (o similar) sólo cambia `_store_bytes` / `read_bytes`.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.attachment import ATTACHMENT_OWNER_TYPES, Attachment, AttachmentBlob

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PER_OWNER = 10

# Extensión → (tipo canónico que se guarda, tipos declarados aceptables).
_TYPES: dict[str, tuple[str, frozenset[str]]] = {
    ".jpg": ("image/jpeg", frozenset({"image/jpeg", "image/jpg", "image/pjpeg"})),
    ".jpeg": ("image/jpeg", frozenset({"image/jpeg", "image/jpg", "image/pjpeg"})),
    ".png": ("image/png", frozenset({"image/png"})),
    ".webp": ("image/webp", frozenset({"image/webp"})),
    ".heic": ("image/heic", frozenset({"image/heic", "image/heif"})),
    ".heif": ("image/heic", frozenset({"image/heic", "image/heif"})),
    ".pdf": ("application/pdf", frozenset({"application/pdf", "application/x-pdf"})),
    ".xml": ("application/xml", frozenset({"application/xml", "text/xml"})),
}
# Navegadores y teléfonos a veces no declaran tipo: entonces mandan la
# extensión y la firma del archivo.
_GENERIC_TYPES = frozenset({"", "application/octet-stream"})

INLINE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/heic", "application/pdf"})

ALLOWED_HINT = "Sube una foto (JPG, PNG, WEBP o HEIC), un PDF o el XML de la factura."


class AttachmentError(ValueError):
    """Archivo rechazado; el mensaje es para el usuario."""


class AttachmentNotFoundError(LookupError):
    pass


def _signature_ok(content_type: str, data: bytes) -> bool:
    if content_type == "application/pdf":
        return data.startswith(b"%PDF-")
    if content_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if content_type == "image/webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if content_type == "image/heic":
        return data[4:8] == b"ftyp"
    if content_type == "application/xml":
        head = data[:64].lstrip(b"\xef\xbb\xbf").lstrip()
        return head.startswith(b"<")
    return False


def validate(filename: str, declared_type: str | None, data: bytes) -> str:
    """Devuelve el tipo canónico del archivo o lanza AttachmentError."""
    extension = os.path.splitext(filename or "")[1].lower()
    known = _TYPES.get(extension)
    if known is None:
        raise AttachmentError(f"Ese tipo de archivo no se acepta. {ALLOWED_HINT}")
    canonical, accepted = known
    declared = (declared_type or "").split(";")[0].strip().lower()
    if declared not in accepted and declared not in _GENERIC_TYPES:
        raise AttachmentError(f"El archivo dice ser {extension} pero llegó como otro tipo. {ALLOWED_HINT}")
    if not data:
        raise AttachmentError("El archivo está vacío.")
    if len(data) > MAX_FILE_BYTES:
        raise AttachmentError("El archivo pesa más de 10 MB. Toma la foto con menor resolución o comprime el PDF.")
    if not _signature_ok(canonical, data):
        raise AttachmentError(f"El contenido no corresponde a un archivo {extension} válido.")
    return canonical


def _clean_filename(filename: str) -> str:
    # Sólo el nombre: nunca rutas del equipo del usuario.
    name = os.path.basename((filename or "").replace("\\", "/")).strip()
    return (name or "archivo")[:255]


def _live(db: Session, organization_id: str):
    return db.query(Attachment).filter(
        Attachment.organization_id == organization_id,
        Attachment.deleted_at.is_(None),
    )


def list_for(db: Session, organization_id: str, owner_type: str, owner_id: str) -> list[Attachment]:
    return (
        _live(db, organization_id)
        .filter(Attachment.owner_type == owner_type, Attachment.owner_id == owner_id)
        .order_by(Attachment.created_at.asc())
        .all()
    )


def get(db: Session, organization_id: str, attachment_id: str) -> Attachment:
    attachment = _live(db, organization_id).filter(Attachment.id == attachment_id).first()
    if attachment is None:
        raise AttachmentNotFoundError("El adjunto no existe.")
    return attachment


def _store_bytes(db: Session, attachment: Attachment, data: bytes) -> None:
    db.add(AttachmentBlob(attachment_id=attachment.id, data=data))


def read_bytes(db: Session, attachment: Attachment) -> bytes:
    blob = db.get(AttachmentBlob, attachment.id)
    if blob is None:
        raise AttachmentNotFoundError("El archivo del adjunto no está disponible.")
    return bytes(blob.data)


def save(
    db: Session,
    organization_id: str,
    owner_type: str,
    owner_id: str,
    filename: str,
    declared_type: str | None,
    data: bytes,
    uploaded_by: str | None,
) -> Attachment:
    """Valida y guarda. El dueño (gasto, etc.) ya fue validado contra la org."""
    if owner_type not in ATTACHMENT_OWNER_TYPES:
        raise AttachmentError("Ese tipo de operación no acepta adjuntos.")
    content_type = validate(filename, declared_type, data)
    current = list_for(db, organization_id, owner_type, owner_id)
    if len(current) >= MAX_PER_OWNER:
        raise AttachmentError(f"Ya tiene {MAX_PER_OWNER} adjuntos, el máximo. Quita uno para subir otro.")
    digest = hashlib.sha256(data).hexdigest()
    if any(item.sha256 == digest for item in current):
        raise AttachmentError("Ese archivo ya está adjunto.")

    attachment = Attachment(
        organization_id=organization_id,
        owner_type=owner_type,
        owner_id=owner_id,
        filename=_clean_filename(filename),
        content_type=content_type,
        size_bytes=len(data),
        sha256=digest,
        uploaded_by=uploaded_by,
    )
    db.add(attachment)
    db.flush()
    _store_bytes(db, attachment, data)
    db.commit()
    db.refresh(attachment)
    return attachment


def soft_delete(db: Session, attachment: Attachment, user_id: str | None) -> None:
    attachment.deleted_at = datetime.now(timezone.utc)
    attachment.deleted_by = user_id
    db.commit()
