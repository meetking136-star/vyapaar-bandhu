"""
VyapaarBandhu -- Invoice Pydantic Schemas
Request/response validation for invoice operations.
Phase 3: Added upload, status, and OCR-related schemas.
"""

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ── Phase 3: Upload & Status schemas ──────────────────────────────────

class InvoiceUploadResponse(BaseModel):
    """Response for POST /invoices/upload (202 Accepted)."""
    invoice_id: uuid.UUID
    status: str = "queued"
    estimated_seconds: int = 30


class InvoiceStatusResponse(BaseModel):
    """Response for GET /invoices/{id}/status."""
    invoice_id: uuid.UUID
    status: str
    extracted_fields: dict | None = None
    confidence_scores: dict | None = None
    low_confidence_fields: list[str] | None = None
    classification: dict | None = None
    is_rcm: bool = False
    rcm_category: str | None = None
    ocr_provider: str | None = None
    processing_attempts: int = 0
    last_error_message: str | None = None
    created_at: datetime
    processed_at: datetime | None = None

    model_config = {"from_attributes": True}


class InvoiceRawURLResponse(BaseModel):
    """Response for GET /invoices/{id}/raw."""
    invoice_id: uuid.UUID
    presigned_url: str
    expires_in_seconds: int = 3600


# ── Existing schemas (from Phase 2) ──────────────────────────────────

class InvoiceResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    ca_id: uuid.UUID
    source_type: str
    seller_gstin: str | None
    seller_name: str | None
    invoice_number: str | None
    invoice_date: date | None
    taxable_amount: Decimal | None
    cgst_amount: Decimal | None
    sgst_amount: Decimal | None
    igst_amount: Decimal | None
    total_amount: Decimal | None
    product_description: str | None
    ocr_confidence_score: Decimal | None
    ocr_provider: str | None
    gstin_was_autocorrected: bool
    category: str | None
    classification_method: str | None
    classification_confidence: Decimal | None
    is_itc_eligible_draft: bool | None
    blocked_reason: str | None
    is_rcm: bool
    rcm_category: str | None
    status: str
    ca_reviewed_at: datetime | None
    ca_override_notes: str | None
    ca_override_category: str | None
    ca_override_itc_eligible: bool | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InvoiceApproveRequest(BaseModel):
    override_category: str | None = None
    override_itc_eligible: bool | None = None
    notes: str | None = Field(None, max_length=500)

    @field_validator("notes")
    @classmethod
    def sanitise_notes(cls, v: str | None) -> str | None:
        if v is None:
            return None
        # Strip control characters
        v = re.sub(r"[\x00-\x1f\x7f]", "", v)
        if len(v) > 500:
            raise ValueError("Notes too long (max 500 chars)")
        return v


class InvoiceRejectRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def sanitise_reason(cls, v: str) -> str:
        v = re.sub(r"[\x00-\x1f\x7f]", "", v)
        return v


class InvoiceOverrideRequest(BaseModel):
    category: str
    itc_eligible: bool
    notes: str = Field(..., min_length=5, max_length=500)

    @field_validator("notes")
    @classmethod
    def sanitise_notes(cls, v: str) -> str:
        v = re.sub(r"[\x00-\x1f\x7f]", "", v)
        return v


class InvoiceConfirmation(BaseModel):
    """WhatsApp user confirmation of extracted invoice data."""
    invoice_id: uuid.UUID
    action: Literal["confirm", "edit", "cancel"]
    edit_field: str | None = None
    edit_value: str | None = None

    @field_validator("edit_value")
    @classmethod
    def sanitise_edit_value(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = re.sub(r"[\x00-\x1f\x7f]", "", v)
        if len(v) > 200:
            raise ValueError("Edit value too long (max 200 chars)")
        return v
