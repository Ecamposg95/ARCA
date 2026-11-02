from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, String

from app.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDPKMixin

IMPORT_KINDS = ("TORONJA", "INCOMES", "EXPENSES", "CASH")
IMPORT_BATCH_STATUSES = ("PREVIEW", "CONFIRMED", "DISCARDED")
IMPORT_ROW_STATUSES = ("OK", "ERROR", "DUPLICATE", "SKIPPED", "CREATED")


class ImportBatch(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Un archivo subido: Toronja o un Excel/CSV de ingresos, gastos o efectivo.

    Vive en PREVIEW hasta que el usuario confirma (CONFIRMED) o lo descarta
    (DISCARDED). Las operaciones se crean sólo al confirmar, todas o ninguna.
    """

    __tablename__ = "import_batches"

    kind = Column(String(20), nullable=False)  # IMPORT_KINDS
    filename = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="PREVIEW")  # IMPORT_BATCH_STATUSES
    # Genérico: columna del archivo → campo (fecha, concepto, monto, ...).
    mapping = Column(JSON, nullable=False, default=dict)
    # Genérico: columnas detectadas, hoja, categoría/cuenta por defecto del lote.
    options = Column(JSON, nullable=False, default=dict)
    # {rows, ok, errors, duplicates, skipped, created}
    summary = Column(JSON, nullable=False, default=dict)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)


class ImportRow(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    """Una fila del archivo, ya leída y clasificada.

    `external_id` identifica la fila fuera de ONE Finance (folio de Toronja o
    hash de fecha+monto+concepto): un `external_id` ya CREATED en la empresa es
    un duplicado. La unicidad es lógica (la valida el service), porque las
    filas ERROR/DUPLICATE de otros lotes repiten el mismo valor a propósito.

    `payload` guarda lo leído: NUNCA nombres de pacientes ni estudios.
    """

    __tablename__ = "import_rows"
    __table_args__ = (
        Index("ix_import_rows_org_kind_external", "organization_id", "kind", "external_id"),
        Index("ix_import_rows_batch_status", "batch_id", "status"),
    )

    batch_id = Column(String(36), ForeignKey("import_batches.id"), nullable=False, index=True)
    # Copia del `kind` del lote: la búsqueda de duplicados no necesita el join.
    kind = Column(String(20), nullable=False)
    row_number = Column(Integer, nullable=False)
    external_id = Column(String(120), nullable=True)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="OK")  # IMPORT_ROW_STATUSES
    message = Column(String(500), nullable=True)
    # Qué creó al confirmar: income | receivable | expense, y su id.
    result_type = Column(String(30), nullable=True)
    result_id = Column(String(36), nullable=True)
