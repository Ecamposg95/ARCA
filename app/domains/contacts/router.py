"""Clientes y proveedores: mismo contrato, dos tablas (factory compartido)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.contact import Customer, Vendor
from app.models.organization import WRITE_ROLES
from app.schemas.common import paginate
from app.security.deps import get_current_org_id, require_role


class ContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    tax_id: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=1000)


class ContactUpdate(ContactCreate):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")


class ContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    legal_name: str | None
    tax_id: str | None
    email: str | None
    phone: str | None
    notes: str | None
    status: str
    created_at: datetime


def build_contact_router(model, prefix: str, not_found_detail: str) -> APIRouter:
    router = APIRouter(prefix=f"/{prefix}", tags=[prefix])

    def _get(db: Session, org_id: str, contact_id: str):
        contact = (
            db.query(model)
            .filter(
                model.id == contact_id,
                model.organization_id == org_id,
                model.deleted_at.is_(None),
            )
            .first()
        )
        if contact is None:
            raise HTTPException(status_code=404, detail=not_found_detail)
        return contact

    @router.get("")
    def list_contacts(
        q: str | None = Query(default=None, max_length=100),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        db: Session = Depends(get_db),
        org_id: str = Depends(get_current_org_id),
    ):
        query = db.query(model).filter(
            model.organization_id == org_id,
            model.deleted_at.is_(None),
        )
        if q:
            pattern = f"%{q}%"
            query = query.filter(or_(model.name.ilike(pattern), model.legal_name.ilike(pattern)))
        query = query.order_by(model.name)
        return paginate(query, limit, offset, ContactRead)

    @router.post("", response_model=ContactRead, status_code=201)
    def create_contact(
        payload: ContactCreate,
        db: Session = Depends(get_db),
        org_id: str = Depends(get_current_org_id),
        _membership=Depends(require_role(WRITE_ROLES)),
    ):
        contact = model(organization_id=org_id, **payload.model_dump())
        db.add(contact)
        db.commit()
        db.refresh(contact)
        return ContactRead.model_validate(contact)

    @router.get("/{contact_id}", response_model=ContactRead)
    def get_contact(
        contact_id: str,
        db: Session = Depends(get_db),
        org_id: str = Depends(get_current_org_id),
    ):
        return ContactRead.model_validate(_get(db, org_id, contact_id))

    @router.patch("/{contact_id}", response_model=ContactRead)
    def update_contact(
        contact_id: str,
        payload: ContactUpdate,
        db: Session = Depends(get_db),
        org_id: str = Depends(get_current_org_id),
        _membership=Depends(require_role(WRITE_ROLES)),
    ):
        contact = _get(db, org_id, contact_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(contact, field, value)
        db.commit()
        db.refresh(contact)
        return ContactRead.model_validate(contact)

    @router.delete("/{contact_id}", status_code=204)
    def delete_contact(
        contact_id: str,
        db: Session = Depends(get_db),
        org_id: str = Depends(get_current_org_id),
        _membership=Depends(require_role(WRITE_ROLES)),
    ):
        contact = _get(db, org_id, contact_id)
        contact.deleted_at = datetime.now(timezone.utc)
        contact.status = "INACTIVE"
        db.commit()

    return router


customers_router = build_contact_router(Customer, "customers", "El cliente no existe.")
vendors_router = build_contact_router(Vendor, "vendors", "El proveedor no existe.")
