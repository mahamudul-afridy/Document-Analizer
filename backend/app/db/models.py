"""SQLAlchemy ORM models.

Money is stored as NUMERIC(18,4) and handled as Decimal everywhere. Extracted values are never
modified by validation; user edits are recorded in `manual_corrections`.
"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.config import settings

EMBED_DIM = settings.embedding_dim
Money = Numeric(18, 4)


class Base(DeclarativeBase):
    pass


def _enum(e: type[enum.Enum], name: str):
    return Enum(e, name=name, native_enum=False, length=32, values_callable=lambda x: [m.value for m in x])


class TimestampMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------- enums
class Role(str, enum.Enum):
    admin = "admin"
    reviewer = "reviewer"
    viewer = "viewer"


class DocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    queued = "queued"
    processing = "processing"
    completed = "completed"
    needs_review = "needs_review"
    failed = "failed"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class Severity(str, enum.Enum):
    passed = "passed"
    warning = "warning"
    failed = "failed"
    review = "review"


class ReviewStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    corrected = "corrected"


# ---------------------------------------------------------------- users & access
class User(TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    role: Mapped[Role] = mapped_column(_enum(Role, "role"), nullable=False, default=Role.viewer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiKey(TimestampMixin, Base):
    __tablename__ = "api_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


class SystemSetting(Base):
    """Key/value settings editable from the UI (e.g. AI engine). Secrets are stored encrypted."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


# ---------------------------------------------------------------- documents
class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_status", "status"),
        Index("ix_documents_created_at", "created_at"),
        Index("ix_documents_name_trgm", "original_name", postgresql_using="gin",
              postgresql_ops={"original_name": "gin_trgm_ops"}),
    )

    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    original_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_kind: Mapped[str] = mapped_column(String(32), nullable=False)  # pdf | image | spreadsheet | csv
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    doc_type: Mapped[str | None] = mapped_column(String(32))  # invoice | receipt | statement | other
    is_scanned: Mapped[bool | None] = mapped_column(Boolean)
    page_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[DocumentStatus] = mapped_column(
        _enum(DocumentStatus, "document_status"), nullable=False, default=DocumentStatus.uploaded
    )
    error: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    files: Mapped[list["DocumentFile"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    pages: Mapped[list["ExtractedText"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="ExtractedText.page_no"
    )
    # usually one invoice; spreadsheet registers produce one invoice per row
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="document", cascade="all, delete-orphan",
                                                     order_by="Invoice.created_at")
    jobs: Mapped[list["ProcessingJob"]] = relationship(back_populates="document", cascade="all, delete-orphan",
                                                       order_by="ProcessingJob.created_at.desc()")
    owner: Mapped[User | None] = relationship()


class DocumentFile(TimestampMixin, Base):
    __tablename__ = "document_files"

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
                                                   index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # original | page_image
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer)

    document: Mapped[Document] = relationship(back_populates="files")


class ExtractedText(TimestampMixin, Base):
    __tablename__ = "extracted_text"
    __table_args__ = (
        UniqueConstraint("document_id", "page_no", name="uq_extracted_text_doc_page"),
        Index("ix_extracted_text_embedding", "embedding", postgresql_using="hnsw",
              postgresql_ops={"embedding": "vector_cosine_ops"}),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)  # pdf_text | tesseract | sheet
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    words: Mapped[list | None] = mapped_column(JSONB)  # [{t, x0, y0, x1, y1, c}] normalised 0..1
    width: Mapped[float | None] = mapped_column(Float)
    height: Mapped[float | None] = mapped_column(Float)
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    embedding = mapped_column(Vector(EMBED_DIM), nullable=True)

    document: Mapped[Document] = relationship(back_populates="pages")


# ---------------------------------------------------------------- invoices
class Invoice(TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_supplier_number", "supplier_name", "invoice_number"),
        Index("ix_invoices_invoice_date", "invoice_date"),
        Index("ix_invoices_total", "total"),
        Index("ix_invoices_supplier_trgm", "supplier_name", postgresql_using="gin",
              postgresql_ops={"supplier_name": "gin_trgm_ops"}),
        Index("ix_invoices_customer_trgm", "customer_name", postgresql_using="gin",
              postgresql_ops={"customer_name": "gin_trgm_ops"}),
        Index("ix_invoices_embedding", "embedding", postgresql_using="hnsw",
              postgresql_ops={"embedding": "vector_cosine_ops"}),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
                                                   index=True)
    source_ref: Mapped[dict | None] = mapped_column(JSONB)  # e.g. {"sheet": "Sheet1", "row": 4}
    invoice_number: Mapped[str | None] = mapped_column(String(128))
    invoice_number_norm: Mapped[str | None] = mapped_column(String(128), index=True)
    invoice_date: Mapped[date | None] = mapped_column(Date)
    supplier_name: Mapped[str | None] = mapped_column(String(255))
    customer_name: Mapped[str | None] = mapped_column(String(255))
    subtotal: Mapped[Decimal | None] = mapped_column(Money)
    tax: Mapped[Decimal | None] = mapped_column(Money)
    total: Mapped[Decimal | None] = mapped_column(Money)
    currency: Mapped[str | None] = mapped_column(String(8))
    tax_rate: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    confidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    field_sources: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # field -> {page, bbox}
    raw_extraction: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # untouched engine output
    engine: Mapped[str] = mapped_column(String(64), nullable=False, default="builtin")
    validation_status: Mapped[Severity] = mapped_column(_enum(Severity, "severity"), nullable=False,
                                                        default=Severity.review)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    embedding = mapped_column(Vector(EMBED_DIM), nullable=True)

    document: Mapped[Document] = relationship(back_populates="invoices")
    line_items: Mapped[list["InvoiceLineItem"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLineItem.position"
    )
    validations: Mapped[list["ValidationResult"]] = relationship(back_populates="invoice",
                                                                 cascade="all, delete-orphan")


class InvoiceLineItem(TimestampMixin, Base):
    __tablename__ = "invoice_line_items"

    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False,
                                                  index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal | None] = mapped_column(Money)
    unit_price: Mapped[Decimal | None] = mapped_column(Money)
    tax: Mapped[Decimal | None] = mapped_column(Money)
    line_total: Mapped[Decimal | None] = mapped_column(Money)
    confidence: Mapped[float | None] = mapped_column(Float)

    invoice: Mapped[Invoice] = relationship(back_populates="line_items")


# ---------------------------------------------------------------- processing
class ProcessingJob(TimestampMixin, Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        # Only one active job per document -> duplicate processing prevention at DB level
        Index("uq_processing_jobs_active", "document_id", unique=True,
              postgresql_where=text("status IN ('queued','running')")),
        Index("ix_processing_jobs_status", "status"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    celery_task_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[JobStatus] = mapped_column(_enum(JobStatus, "job_status"), nullable=False, default=JobStatus.queued)
    current_stage: Mapped[str] = mapped_column(String(64), nullable=False, default="uploaded")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped[Document] = relationship(back_populates="jobs")
    history: Mapped[list["ProcessingHistory"]] = relationship(back_populates="job", cascade="all, delete-orphan",
                                                              order_by="ProcessingHistory.created_at")


class ProcessingHistory(TimestampMixin, Base):
    __tablename__ = "processing_history"

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False,
                                              index=True)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # started | completed | failed | skipped
    message: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    job: Mapped[ProcessingJob] = relationship(back_populates="history")


# ---------------------------------------------------------------- validation
class ValidationResult(TimestampMixin, Base):
    __tablename__ = "validation_results"
    __table_args__ = (Index("ix_validation_results_severity", "severity"),)

    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False,
                                                  index=True)
    rule: Mapped[str] = mapped_column(String(64), nullable=False)
    field: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected: Mapped[str | None] = mapped_column(String(255))
    extracted: Mapped[str | None] = mapped_column(String(255))
    difference: Mapped[str | None] = mapped_column(String(64))
    severity: Mapped[Severity] = mapped_column(_enum(Severity, "severity"), nullable=False)
    related_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    review_status: Mapped[ReviewStatus] = mapped_column(_enum(ReviewStatus, "review_status"), nullable=False,
                                                        default=ReviewStatus.pending)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)

    invoice: Mapped[Invoice] = relationship(back_populates="validations")


class CrossVerificationResult(TimestampMixin, Base):
    __tablename__ = "cross_verification_results"

    source_document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"),
                                                          nullable=False, index=True)
    # which invoice of the source document this comparison belongs to (registers hold many invoices)
    source_invoice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"),
                                                                index=True)
    target_document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"),
                                                          nullable=False, index=True)
    comparison_type: Mapped[str] = mapped_column(String(32), nullable=False)  # pdf_pdf | pdf_excel | excel_csv ...
    match_basis: Mapped[str] = mapped_column(String(64), nullable=False)  # invoice_number | supplier_total_date
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    source_value: Mapped[str | None] = mapped_column(String(255))
    target_value: Mapped[str | None] = mapped_column(String(255))
    difference: Mapped[str | None] = mapped_column(String(64))
    is_match: Mapped[bool] = mapped_column(Boolean, nullable=False)
    severity: Mapped[Severity] = mapped_column(_enum(Severity, "severity"), nullable=False)


class ManualCorrection(TimestampMixin, Base):
    __tablename__ = "manual_corrections"

    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False,
                                                  index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    field_path: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g. total, line_items[2].quantity
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_created_at", "created_at"), Index("ix_audit_logs_entity", "entity_type",
                                                                             "entity_id"))

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
