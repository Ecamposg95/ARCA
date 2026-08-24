"""Núcleo contable: catálogo de cuentas y pólizas (double-entry).

Invariante inquebrantable: SUM(debit) == SUM(credit) por póliza.
Se hace cumplir en app/services/accounting/engine.py — todo asiento
pasa por ahí. Las pólizas nunca se borran físicamente.
"""

from sqlalchemy import Boolean, Column, Date, ForeignKey, Numeric, String, UniqueConstraint

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin

ACCOUNT_TYPES = ("ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE")

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

    date = Column(Date, nullable=False, index=True)
    description = Column(String(500), nullable=False)
    reference = Column(String(100), nullable=True)
    source_type = Column(String(50), nullable=True, index=True)
    source_id = Column(String(36), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="POSTED")
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)


class JournalEntryLine(Base, UUIDPKMixin):
    __tablename__ = "journal_entry_lines"

    journal_entry_id = Column(String(36), ForeignKey("journal_entries.id"), nullable=False, index=True)
    account_id = Column(String(36), ForeignKey("accounts.id"), nullable=False, index=True)
    debit = Column(Numeric(14, 2), nullable=False, default=0)
    credit = Column(Numeric(14, 2), nullable=False, default=0)
    description = Column(String(500), nullable=True)
