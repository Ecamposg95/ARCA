"""Núcleo contable: catálogo de cuentas y pólizas (double-entry).

Invariante inquebrantable: SUM(debit) == SUM(credit) por póliza.
Se hace cumplir en app/services/accounting/engine.py — todo asiento
pasa por ahí. Las pólizas nunca se borran físicamente.
"""

from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin

ACCOUNT_TYPES = ("ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE")

# Naturaleza de la póliza (convención mexicana). El folio la lleva como prefijo.
ENTRY_KINDS = ("INGRESO", "EGRESO", "DIARIO")

# Tipos con naturaleza deudora (su saldo crece con débitos)
DEBIT_NORMAL_TYPES = ("ASSET", "EXPENSE")


class Account(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_account_org_code"),)

    code = Column(String(10), nullable=False)
    name = Column(String(255), nullable=False)
    type = Column(String(10), nullable=False)  # ACCOUNT_TYPES
    parent_id = Column(String(36), ForeignKey("accounts.id"), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    system = Column(Boolean, nullable=False, default=False)


class JournalEntry(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    __tablename__ = "journal_entries"
    __table_args__ = (UniqueConstraint("organization_id", "folio", name="uq_journal_entry_org_folio"),)

    # Folio inmutable asignado al contabilizar: Ig-2026-08-0001 (ver services/accounting/folios.py)
    folio = Column(String(20), nullable=False)
    kind = Column(String(10), nullable=False, default="DIARIO")  # ENTRY_KINDS
    date = Column(Date, nullable=False, index=True)
    description = Column(String(500), nullable=False)
    reference = Column(String(100), nullable=True)
    source_type = Column(String(50), nullable=True, index=True)
    # 64, no 36: las claves de idempotencia de procesos periódicos son
    # compuestas (`{entidad}:{AAAA-MM}`) y no caben en un UUID pelón.
    source_id = Column(String(64), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="POSTED")
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)


class FolioCounter(Base, UUIDPKMixin, AuditMixin):
    """Consecutivo por organización, tipo de póliza y mes.

    Vive en su propia tabla para poder tomar un lock de fila al asignar folio:
    dos operaciones simultáneas nunca reciben el mismo número.
    """

    __tablename__ = "folio_counters"
    __table_args__ = (
        UniqueConstraint("organization_id", "kind", "period", name="uq_folio_counter_scope"),
    )

    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    kind = Column(String(10), nullable=False)  # ENTRY_KINDS
    period = Column(String(7), nullable=False)  # AAAA-MM
    next_number = Column(Integer, nullable=False, default=1)


class JournalEntryLine(Base, UUIDPKMixin):
    __tablename__ = "journal_entry_lines"

    journal_entry_id = Column(String(36), ForeignKey("journal_entries.id"), nullable=False, index=True)
    account_id = Column(String(36), ForeignKey("accounts.id"), nullable=False, index=True)
    debit = Column(Numeric(14, 2), nullable=False, default=0)
    credit = Column(Numeric(14, 2), nullable=False, default=0)
    description = Column(String(500), nullable=True)
