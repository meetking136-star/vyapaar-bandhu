"""
VyapaarBandhu — Summary Builder
Builds aggregated ITC summary for a CA across all clients for a period.
Uses single aggregation query -- no N+1 loops.

CRITICAL: This file must never import any ML/AI library.
CRITICAL: All monetary values use Python Decimal with ROUND_HALF_UP.
"""
from __future__ import annotations

import uuid
from decimal import Decimal, ROUND_HALF_UP

import structlog
from sqlalchemy import func, select, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.invoice import Invoice

logger = structlog.get_logger()

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")


def _q(val: Decimal | None) -> str:
    """Quantize a Decimal to 2 places with ROUND_HALF_UP, return as string."""
    if val is None:
        return str(ZERO)
    return str(Decimal(str(val)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP))


async def build_period_summary(
    db: AsyncSession,
    *,
    ca_id: uuid.UUID,
    period: str,
) -> dict:
    """
    Build aggregated ITC summary for all clients of a CA for a given period.

    Uses single aggregation query -- no N+1 loops.
    Period format: MM-YYYY

    ITC formula:
        confirmed = sum(cgst+sgst+igst) WHERE status IN (ca_approved, ca_overridden)
                    AND is_itc_eligible_draft=True
                    AND ca_override_itc_eligible IS NOT False
        pending = same but status=processing OR pending_ca_review
        rejected = is_itc_eligible_draft=False OR ca_override_itc_eligible=False
        rcm_liability = sum(taxable_value) WHERE is_rcm=True
    """
    # Convert MM-YYYY to match filing_period stored as MM-YYYY
    # (some records may store as YYYY-MM, handle both)
    filing_period = period  # MM-YYYY as provided

    # Single aggregation query
    result = await db.execute(
        select(
            # Confirmed ITC (approved + eligible)
            func.coalesce(func.sum(case(
                (and_(
                    Invoice.status.in_(["ca_approved", "ca_overridden"]),
                    Invoice.is_itc_eligible_draft == True,
                    Invoice.ca_override_itc_eligible != False,
                ), Invoice.cgst_amount),
                else_=Decimal("0"),
            )), Decimal("0")).label("cgst_confirmed"),

            func.coalesce(func.sum(case(
                (and_(
                    Invoice.status.in_(["ca_approved", "ca_overridden"]),
                    Invoice.is_itc_eligible_draft == True,
                    Invoice.ca_override_itc_eligible != False,
                ), Invoice.sgst_amount),
                else_=Decimal("0"),
            )), Decimal("0")).label("sgst_confirmed"),

            func.coalesce(func.sum(case(
                (and_(
                    Invoice.status.in_(["ca_approved", "ca_overridden"]),
                    Invoice.is_itc_eligible_draft == True,
                    Invoice.ca_override_itc_eligible != False,
                ), Invoice.igst_amount),
                else_=Decimal("0"),
            )), Decimal("0")).label("igst_confirmed"),

            # Pending ITC
            func.coalesce(func.sum(case(
                (and_(
                    Invoice.status.in_(["processing", "pending_ca_review", "pending_client_confirmation"]),
                    Invoice.is_itc_eligible_draft == True,
                ), Invoice.cgst_amount + Invoice.sgst_amount + Invoice.igst_amount),
                else_=Decimal("0"),
            )), Decimal("0")).label("total_pending"),

            # Rejected ITC
            func.coalesce(func.sum(case(
                (and_(
                    Invoice.status.in_(["ca_approved", "ca_overridden", "ca_rejected"]),
                    (Invoice.is_itc_eligible_draft == False) | (Invoice.ca_override_itc_eligible == False),
                ), Invoice.cgst_amount + Invoice.sgst_amount + Invoice.igst_amount),
                else_=Decimal("0"),
            )), Decimal("0")).label("total_rejected"),

            # RCM liability
            func.coalesce(func.sum(case(
                (Invoice.is_rcm == True, Invoice.taxable_amount),
                else_=Decimal("0"),
            )), Decimal("0")).label("rcm_liability"),

            # Invoice count
            func.count(Invoice.id).label("invoice_count"),
        )
        .join(Client, Client.id == Invoice.client_id)
        .where(
            Invoice.ca_id == ca_id,
            Invoice.filing_period == filing_period,
            Client.is_active == True,
        )
    )
    row = result.one()
    summary = format_summary_row(row, period)

    logger.info(
        "summary.built",
        ca_id=str(ca_id),
        period=period,
        invoice_count=summary["invoice_count"],
        total_confirmed=summary["total_confirmed"],
    )

    return summary


def format_summary_row(row, period: str) -> dict:
    """
    Convert a raw aggregation row into a summary dict.
    All monetary values as string Decimal with ROUND_HALF_UP, never float.
    Extracted for testability without requiring a real DB.
    """
    cgst_confirmed = Decimal(str(row.cgst_confirmed or 0))
    sgst_confirmed = Decimal(str(row.sgst_confirmed or 0))
    igst_confirmed = Decimal(str(row.igst_confirmed or 0))
    total_confirmed = cgst_confirmed + sgst_confirmed + igst_confirmed
    total_pending = Decimal(str(row.total_pending or 0))
    total_rejected = Decimal(str(row.total_rejected or 0))
    rcm_liability = Decimal(str(row.rcm_liability or 0))
    invoice_count = row.invoice_count or 0

    return {
        "period": period,
        "cgst_confirmed": _q(cgst_confirmed),
        "sgst_confirmed": _q(sgst_confirmed),
        "igst_confirmed": _q(igst_confirmed),
        "total_confirmed": _q(total_confirmed),
        "total_pending": _q(total_pending),
        "total_rejected": _q(total_rejected),
        "rcm_liability": _q(rcm_liability),
        "invoice_count": invoice_count,
    }
