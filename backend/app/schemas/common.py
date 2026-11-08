"""Pydantic API schemas."""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator("*", mode="before")
    @classmethod
    def _enum_to_value(cls, v):
        # DB enums (Role, Severity, ...) are exposed as their plain string values
        return v.value if isinstance(v, enum.Enum) else v


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------- auth / users
class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class SetupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    full_name: str = Field(min_length=1, max_length=255)


class UserOut(ORM):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=200)
    role: Literal["admin", "reviewer", "viewer"] = "viewer"


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    role: Literal["admin", "reviewer", "viewer"] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=8, max_length=200)


# ---------------------------------------------------------------- documents / jobs
class HistoryOut(ORM):
    id: uuid.UUID
    stage: str
    status: str
    message: str | None
    duration_ms: int | None
    created_at: datetime


class JobOut(ORM):
    id: uuid.UUID
    document_id: uuid.UUID
    status: str
    current_stage: str
    progress: int
    attempts: int
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class JobDetail(JobOut):
    document_name: str | None = None
    history: list[HistoryOut] = []


class InvoiceBrief(ORM):
    id: uuid.UUID
    invoice_number: str | None
    total: Decimal | None
    currency: str | None
    validation_status: str
    supplier_name: str | None


class DocumentOut(ORM):
    id: uuid.UUID
    original_name: str
    file_kind: str
    mime_type: str
    size_bytes: int
    doc_type: str | None
    is_scanned: bool | None
    page_count: int | None
    status: str
    error: str | None
    is_demo: bool
    created_at: datetime
    updated_at: datetime
    invoices: list[InvoiceBrief] = []


class UploadResult(BaseModel):
    filename: str
    ok: bool
    document_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    duplicate_of: uuid.UUID | None = None
    error: str | None = None


# ---------------------------------------------------------------- invoices
class LineItemOut(ORM):
    id: uuid.UUID
    position: int
    description: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    tax: Decimal | None
    line_total: Decimal | None
    confidence: float | None


class ValidationOut(ORM):
    id: uuid.UUID
    invoice_id: uuid.UUID
    rule: str
    field: str | None
    message: str
    expected: str | None
    extracted: str | None
    difference: str | None
    severity: str
    related_document_id: uuid.UUID | None
    review_status: str
    reviewed_at: datetime | None
    review_note: str | None
    created_at: datetime


class CorrectionOut(ORM):
    id: uuid.UUID
    field_path: str
    old_value: str | None
    new_value: str | None
    reason: str | None
    user_id: uuid.UUID | None
    created_at: datetime


class InvoiceOut(ORM):
    id: uuid.UUID
    document_id: uuid.UUID
    source_ref: dict | None
    invoice_number: str | None
    invoice_date: date | None
    supplier_name: str | None
    customer_name: str | None
    subtotal: Decimal | None
    tax: Decimal | None
    tax_rate: Decimal | None
    total: Decimal | None
    currency: str | None
    confidence: dict
    field_sources: dict
    engine: str
    validation_status: str
    needs_review: bool
    created_at: datetime
    updated_at: datetime


class InvoiceListItem(InvoiceOut):
    document_name: str | None = None
    is_demo: bool = False


class InvoiceDetail(InvoiceOut):
    line_items: list[LineItemOut] = []
    validations: list[ValidationOut] = []
    corrections: list[CorrectionOut] = []
    raw_extraction: dict = {}


class LineItemPatch(BaseModel):
    id: uuid.UUID | None = None  # None -> new line
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    tax: Decimal | None = None
    line_total: Decimal | None = None
    delete: bool = False


class InvoicePatch(BaseModel):
    invoice_number: str | None = None
    invoice_date: date | None = None
    supplier_name: str | None = None
    customer_name: str | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    tax_rate: Decimal | None = None
    total: Decimal | None = None
    currency: str | None = Field(default=None, max_length=8)
    line_items: list[LineItemPatch] | None = None
    reason: str | None = Field(default=None, max_length=1000)
    # explicit list of fields to set to null (so "not sent" and "clear it" are different)
    clear_fields: list[str] = []


class DocumentDetail(DocumentOut):
    invoices_detail: list[InvoiceDetail] = []
    jobs: list[JobDetail] = []
    page_texts: list[dict] = []
    cross_verification: list[dict] = []


class ReviewIn(BaseModel):
    review_status: Literal["approved", "rejected", "pending"]
    note: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------- settings / api keys
class AISettingsIn(BaseModel):
    llm_enabled: bool = False
    provider: Literal["anthropic", "openai"] | None = None
    model: str | None = Field(default=None, max_length=100)
    api_key: str | None = Field(default=None, max_length=500)
    clear_api_key: bool = False
    fallback_to_builtin: bool = True
    timeout_s: int = Field(default=60, ge=5, le=300)


class AITestIn(BaseModel):
    provider: Literal["anthropic", "openai"]
    model: str | None = None
    api_key: str | None = None  # if omitted, the stored key is used


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ApiKeyOut(ORM):
    id: uuid.UUID
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreated(ApiKeyOut):
    key: str


class SemanticSearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    limit: int = Field(default=25, ge=1, le=100)
