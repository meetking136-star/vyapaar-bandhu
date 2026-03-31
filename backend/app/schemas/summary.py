"""
VyapaarBandhu — Summary Pydantic Schemas
Response models for dashboard overview and monthly summaries.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ClientStatusItem(BaseModel):
    """Single client in the traffic light overview grid."""
    client_id: uuid.UUID
    business_name: str
    owner_name: str
    status_color: Literal["green", "yellow", "red"]
    status_reason: str
    invoice_count: int
    pending_ca_review_count: int
    flagged_low_confidence_count: int
    draft_itc_total: Decimal
    confirmed_itc_total: Decimal
    gstr3b_deadline: date
    days_to_deadline: int


class DashboardOverviewResponse(BaseModel):
    """CA dashboard overview — traffic light grid."""
    clients: list[ClientStatusItem]
    total_clients: int
    total_invoices: int
    total_draft_itc: Decimal
    total_confirmed_itc: Decimal


class MonthlySummaryResponse(BaseModel):
    """Monthly ITC summary for a single client."""
    id: uuid.UUID
    client_id: uuid.UUID
    tax_period: str
    draft_total_taxable: Decimal
    draft_cgst_itc: Decimal
    draft_sgst_itc: Decimal
    draft_igst_itc: Decimal
    draft_total_itc: Decimal
    confirmed_total_taxable: Decimal | None
    confirmed_cgst_itc: Decimal | None
    confirmed_sgst_itc: Decimal | None
    confirmed_igst_itc: Decimal | None
    confirmed_total_itc: Decimal | None
    draft_rcm_liability: Decimal
    confirmed_rcm_liability: Decimal | None
    invoice_count: int
    approved_count: int
    flagged_count: int
    rejected_count: int
    is_filed: bool

    model_config = {"from_attributes": True}


class DashboardSummaryResponse(BaseModel):
    """Aggregated ITC summary across all clients for a period."""
    period: str
    cgst_confirmed: str  # Decimal as string, never float
    sgst_confirmed: str
    igst_confirmed: str
    total_confirmed: str
    total_pending: str
    total_rejected: str
    rcm_liability: str
    invoice_count: int


class AlertItem(BaseModel):
    """Single compliance alert."""
    type: str
    severity: Literal["red", "yellow", "green"]
    message: str
    client_id: str | None = None
    client_name: str | None = None
    created_at: str


class AlertsResponse(BaseModel):
    """List of compliance alerts."""
    alerts: list[AlertItem]
    total: int


class ITCSummaryResponse(BaseModel):
    """ITC summary for a single client for a period."""
    client_id: uuid.UUID
    period: str
    cgst_confirmed: str
    sgst_confirmed: str
    igst_confirmed: str
    total_confirmed: str
    total_pending: str
    total_rejected: str
    rcm_liability: str
    invoice_count: int


class BulkActionRequest(BaseModel):
    """Request body for bulk invoice actions."""
    invoice_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=50)
    action: Literal["approve", "reject", "flag"]

    @field_validator("invoice_ids")
    @classmethod
    def validate_invoice_count(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(v) > 50:
            raise ValueError("Maximum 50 invoices per bulk action request")
        return v


class BulkActionResponse(BaseModel):
    """Response for bulk invoice actions."""
    processed: int
    failed: int
    results: list[dict]
