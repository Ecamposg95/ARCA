from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AttachmentRead(BaseModel):
    """Metadatos del adjunto. Los bytes sólo salen por /download."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_type: str
    owner_id: str
    filename: str
    content_type: str
    size_bytes: int
    uploaded_by: str | None
    uploaded_by_name: str | None = None
    created_at: datetime
