"""
VyapaarBandhu — ITC Amount Calculator
Decimal math with ROUND_HALF_UP. No floating point anywhere.

CRITICAL: This file must never import any ML/AI library.
Reference: GST Act Section 16 — Eligibility and conditions for ITC.

This module provides:
1. Per-invoice ITC calculation (interstate vs intrastate)
2. ITC eligibility determination (confirmed/pending/rejected)
3. Aggregate ITC summary computation from invoice lists
4. RCM liability calculation
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Sequence

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")


def _q(val: Decimal) -> Decimal:
    """Quantize to 2 decimal places with ROUND_HALF_UP."""
    return val.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass
class ITCAmounts:
    """Per-invoice ITC breakdown."""
    cgst: Decimal = ZERO
    sgst: Decimal = ZERO
    igst: Decimal = ZERO
    total: Decimal = ZERO


@dataclass
class AggregateITC:
    """
    Aggregate ITC summary for a client/period.
    All values are Decimal with ROUND_HALF_UP to 2 places.

    ITC Formula (GST Act Section 16):
        confirmed = sum(cgst+sgst+igst) WHERE status IN (ca_approved, ca_overridden)
                    AND is_itc_eligible_draft=True
                    AND ca_override_itc_eligible IS NOT False
        pending   = same eligibility but status IN (processing, pending_ca_review,
                    pending_client_confirmation)
        rejected  = is_itc_eligible_draft=False OR ca_override_itc_eligible=False
        rcm_liability = sum(taxable_value) WHERE is_rcm=True
    """
    cgst_confirmed: Decimal = ZERO
    sgst_confirmed: Decimal = ZERO
    igst_confirmed: Decimal = ZERO
    total_confirmed: Decimal = ZERO
    total_pending: Decimal = ZERO
    total_rejected: Decimal = ZERO
    rcm_liability: Decimal = ZERO
    invoice_count: int = 0


# Statuses that count as "confirmed" for ITC purposes
CONFIRMED_STATUSES = frozenset({"ca_approved", "ca_overridden"})

# Statuses that count as "pending" for ITC purposes
PENDING_STATUSES = frozenset({
    "processing", "pending_ca_review", "pending_client_confirmation",
})

# Statuses included when checking rejected ITC
REVIEWED_STATUSES = frozenset({"ca_approved", "ca_overridden", "ca_rejected"})


def calculate_itc_amounts(
    cgst: Decimal | None,
    sgst: Decimal | None,
    igst: Decimal | None,
    is_interstate: bool,
) -> ITCAmounts:
    """
    Calculate ITC amounts from invoice tax components.

    For inter-state transactions: ITC = IGST amount
    For intra-state transactions: ITC = CGST + SGST amounts

    All amounts rounded to 2 decimal places with ROUND_HALF_UP.

    Reference: GST Act Section 16 + IGST Act Section 5
    """
    cgst_val = _to_decimal(cgst)
    sgst_val = _to_decimal(sgst)
    igst_val = _to_decimal(igst)

    if is_interstate:
        return ITCAmounts(
            cgst=ZERO,
            sgst=ZERO,
            igst=_q(igst_val),
            total=_q(igst_val),
        )
    else:
        total = _q(cgst_val + sgst_val)
        return ITCAmounts(
            cgst=_q(cgst_val),
            sgst=_q(sgst_val),
            igst=ZERO,
            total=total,
        )


def is_itc_eligible(invoice: Any) -> bool:
    """
    Determine if an invoice is ITC-eligible based on draft + CA override.

    Rules:
    - is_itc_eligible_draft must be True
    - ca_override_itc_eligible must NOT be False (None is OK -- means no override)

    Reference: GST Act Section 16(2) — conditions for ITC claim.
    """
    draft_eligible = getattr(invoice, "is_itc_eligible_draft", None)
    ca_override = getattr(invoice, "ca_override_itc_eligible", None)

    if draft_eligible is not True:
        return False
    if ca_override is False:
        return False
    return True


def is_itc_rejected(invoice: Any) -> bool:
    """
    Determine if an invoice has rejected ITC.
    True if draft=False OR CA explicitly overrode to False.
    """
    draft_eligible = getattr(invoice, "is_itc_eligible_draft", None)
    ca_override = getattr(invoice, "ca_override_itc_eligible", None)

    return draft_eligible is False or ca_override is False


def compute_aggregate_itc(invoices: Sequence[Any]) -> AggregateITC:
    """
    Compute aggregate ITC summary from a sequence of invoice objects.

    Each invoice must have attributes:
    - status: str
    - cgst_amount, sgst_amount, igst_amount: Decimal | None
    - taxable_amount: Decimal | None
    - is_itc_eligible_draft: bool | None
    - ca_override_itc_eligible: bool | None
    - is_rcm: bool

    ITC Formula:
        confirmed = sum(cgst+sgst+igst) WHERE status=confirmed AND eligible
        pending = sum(cgst+sgst+igst) WHERE status=pending AND draft eligible
        rejected = sum(cgst+sgst+igst) WHERE reviewed AND not eligible
        rcm_liability = sum(taxable_value) WHERE is_rcm=True

    All monetary values use ROUND_HALF_UP. Zero float anywhere.
    """
    cgst_confirmed = ZERO
    sgst_confirmed = ZERO
    igst_confirmed = ZERO
    total_pending = ZERO
    total_rejected = ZERO
    rcm_liability = ZERO

    for inv in invoices:
        status = getattr(inv, "status", "")
        cgst = _to_decimal(getattr(inv, "cgst_amount", None))
        sgst = _to_decimal(getattr(inv, "sgst_amount", None))
        igst = _to_decimal(getattr(inv, "igst_amount", None))
        taxable = _to_decimal(getattr(inv, "taxable_amount", None))
        tax_total = cgst + sgst + igst

        # Confirmed ITC
        if status in CONFIRMED_STATUSES and is_itc_eligible(inv):
            cgst_confirmed += cgst
            sgst_confirmed += sgst
            igst_confirmed += igst

        # Pending ITC
        if status in PENDING_STATUSES and getattr(inv, "is_itc_eligible_draft", None) is True:
            total_pending += tax_total

        # Rejected ITC
        if status in REVIEWED_STATUSES and is_itc_rejected(inv):
            total_rejected += tax_total

        # RCM liability (always on taxable_value, not tax amount)
        if getattr(inv, "is_rcm", False) is True:
            rcm_liability += taxable

    total_confirmed = cgst_confirmed + sgst_confirmed + igst_confirmed

    return AggregateITC(
        cgst_confirmed=_q(cgst_confirmed),
        sgst_confirmed=_q(sgst_confirmed),
        igst_confirmed=_q(igst_confirmed),
        total_confirmed=_q(total_confirmed),
        total_pending=_q(total_pending),
        total_rejected=_q(total_rejected),
        rcm_liability=_q(rcm_liability),
        invoice_count=len(invoices),
    )


def _to_decimal(value: Decimal | float | int | None) -> Decimal:
    """Safely convert to Decimal. None and negative values become 0."""
    if value is None:
        return ZERO
    d = Decimal(str(value))
    return max(d, ZERO)
