"""
VyapaarBandhu — Export Endpoints
GSTR-3B JSON, PDF filing summary, Tally XML (stub).
Phase 6: Proper Decimal math, S3 upload, presigned URLs, audit logging.

CRITICAL: Never use float for tax calculations.
CRITICAL: PDF never streams through API server -- presigned URL only.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal, ROUND_HALF_UP

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.dependencies import CurrentCA
from app.models.client import Client
from app.models.invoice import Invoice
from app.services.exports.gstr3b_builder import GSTR3BInput, build_gstr3b_json, _fmt
from app.services.exports.pdf_generator import generate_filing_pdf
from app.utils.audit import write_audit_log

logger = structlog.get_logger()
router = APIRouter()

ZERO = Decimal("0.00")


# ── GSTR-3B JSON Export ───────────────────────────────────────────────

@router.get("/gstr3b")
async def export_gstr3b(
    ca: CurrentCA,
    db: AsyncSession = Depends(get_async_session),
    client_id: uuid.UUID = Query(...),
    period: str = Query(..., regex=r"^\d{2}-\d{4}$", description="MM-YYYY"),
):
    """
    Generate GSTR-3B JSON for a client+period.
    Auth: CA JWT. CA isolation enforced.
    Returns: JSON response (application/json).
    Also saves JSON to S3: exports/{ca_id}/{client_id}/{period}/gstr3b.json
    """
    client = await _get_client_or_404(client_id, ca.id, db)
    itc_data = await _compute_itc_aggregates(client_id, ca.id, period, db)

    gstr3b_input = GSTR3BInput(
        gstin=client.gstin or "",
        period=period,
        cgst_confirmed=itc_data["cgst_confirmed"],
        sgst_confirmed=itc_data["sgst_confirmed"],
        igst_confirmed=itc_data["igst_confirmed"],
        cgst_rejected=itc_data["cgst_rejected"],
        sgst_rejected=itc_data["sgst_rejected"],
        igst_rejected=itc_data["igst_rejected"],
        rcm_taxable=itc_data["rcm_taxable"],
        rcm_cgst=itc_data["rcm_cgst"],
        rcm_sgst=itc_data["rcm_sgst"],
        rcm_igst=itc_data["rcm_igst"],
    )

    gstr3b = build_gstr3b_json(gstr3b_input)

    # Upload to S3
    try:
        from app.services.storage.s3_client import upload_export
        s3_key = f"{ca.id}/{client_id}/{period}/gstr3b.json"
        json_bytes = json.dumps(gstr3b, indent=2).encode("utf-8")
        await upload_export(
            data=json_bytes,
            client_id=client_id,
            filename=f"{ca.id}/{client_id}/{period}/gstr3b.json",
            content_type="application/json",
        )
    except Exception as e:
        logger.warning("export.gstr3b.s3_upload_failed", error=str(e))

    # Audit log
    await write_audit_log(
        db,
        actor_type="ca",
        actor_id=ca.id,
        action="gstr3b_export",
        entity_type="client",
        entity_id=client_id,
        new_value={"period": period, "gstin": client.gstin},
    )
    await db.commit()

    return JSONResponse(content=gstr3b)


# ── PDF Export ────────────────────────────────────────────────────────

@router.get("/pdf")
async def export_pdf(
    ca: CurrentCA,
    db: AsyncSession = Depends(get_async_session),
    client_id: uuid.UUID = Query(...),
    period: str = Query(..., regex=r"^\d{2}-\d{4}$", description="MM-YYYY"),
):
    """
    Generate PDF, upload to S3, return presigned URL.
    NEVER streams PDF through API server.
    Presigned URL expiry: 1 hour.
    """
    client = await _get_client_or_404(client_id, ca.id, db)
    itc_data = await _compute_itc_aggregates(client_id, ca.id, period, db)
    invoices = await _get_period_invoices(client_id, ca.id, period, db)

    # Separate flagged invoices
    flagged = [i for i in invoices if i.status in (
        "flagged_low_confidence", "flagged_classification", "flagged_anomaly"
    )]
    pending_count = sum(
        1 for i in invoices
        if i.status not in ("ca_approved", "ca_rejected", "ca_overridden")
    )

    pdf_bytes = await generate_filing_pdf(
        ca_firm_name=ca.firm_name,
        ca_proprietor_name=ca.proprietor_name,
        client_name=client.business_name,
        client_gstin=client.gstin,
        tax_period=period,
        invoices=invoices,
        confirmed_cgst_itc=_fmt(itc_data["cgst_confirmed"]),
        confirmed_sgst_itc=_fmt(itc_data["sgst_confirmed"]),
        confirmed_igst_itc=_fmt(itc_data["igst_confirmed"]),
        confirmed_total_itc=_fmt(
            itc_data["cgst_confirmed"] + itc_data["sgst_confirmed"] + itc_data["igst_confirmed"]
        ),
        pending_cgst_itc=_fmt(itc_data.get("cgst_pending", ZERO)),
        pending_sgst_itc=_fmt(itc_data.get("sgst_pending", ZERO)),
        pending_igst_itc=_fmt(itc_data.get("igst_pending", ZERO)),
        pending_total_itc=_fmt(itc_data.get("total_pending", ZERO)),
        rejected_cgst_itc=_fmt(itc_data["cgst_rejected"]),
        rejected_sgst_itc=_fmt(itc_data["sgst_rejected"]),
        rejected_igst_itc=_fmt(itc_data["igst_rejected"]),
        rejected_total_itc=_fmt(
            itc_data["cgst_rejected"] + itc_data["sgst_rejected"] + itc_data["igst_rejected"]
        ),
        rcm_liability=itc_data["rcm_taxable"],  # Decimal, not string
        pending_count=pending_count,
        flagged_invoices=flagged,
        invoice_count=len(invoices),
    )

    # Upload to S3 and get presigned URL
    from app.services.storage.s3_client import upload_export, generate_presigned_url
    from app.config import settings

    s3_filename = f"{ca.id}/{client_id}/{period}/report.pdf"
    await upload_export(
        data=pdf_bytes,
        client_id=client_id,
        filename=s3_filename,
        content_type="application/pdf",
    )

    presigned_url = generate_presigned_url(
        bucket=settings.S3_BUCKET_EXPORTS,
        key=f"exports/{client_id}/{s3_filename}",
        expiry=3600,
    )

    # Audit log
    await write_audit_log(
        db,
        actor_type="ca",
        actor_id=ca.id,
        action="pdf_export",
        entity_type="client",
        entity_id=client_id,
        new_value={"period": period, "size_bytes": len(pdf_bytes)},
    )
    await db.commit()

    return JSONResponse(content={
        "presigned_url": presigned_url,
        "expires_in_seconds": 3600,
        "size_bytes": len(pdf_bytes),
    })


# ── PDF Download (presigned URL only) ─────────────────────────────────

@router.get("/pdf/download")
async def export_pdf_download(
    ca: CurrentCA,
    db: AsyncSession = Depends(get_async_session),
    client_id: uuid.UUID = Query(...),
    period: str = Query(..., regex=r"^\d{2}-\d{4}$", description="MM-YYYY"),
):
    """
    Returns presigned S3 URL only. Client downloads directly from S3.
    Does NOT regenerate PDF -- returns URL to existing export.
    """
    client = await _get_client_or_404(client_id, ca.id, db)

    from app.services.storage.s3_client import generate_presigned_url
    from app.config import settings

    s3_key = f"exports/{client_id}/{ca.id}/{client_id}/{period}/report.pdf"
    presigned_url = generate_presigned_url(
        bucket=settings.S3_BUCKET_EXPORTS,
        key=s3_key,
        expiry=3600,
    )

    return JSONResponse(content={
        "presigned_url": presigned_url,
        "expires_in_seconds": 3600,
    })


# ── Tally XML (stub) ─────────────────────────────────────────────────

@router.get("/tally")
async def export_tally(
    ca: CurrentCA,
    client_id: uuid.UUID = Query(...),
    period: str = Query(...),
):
    """TallyPrime XML export -- roadmap Q3 2026."""
    raise HTTPException(
        status_code=501,
        detail="TallyPrime XML export is on the roadmap for Q3 2026.",
    )


# ── Legacy endpoints (kept for backward compatibility) ────────────────

@router.get("/{client_id}/pdf/{period}")
async def download_pdf_legacy(
    client_id: uuid.UUID,
    period: str,
    ca: CurrentCA,
    db: AsyncSession = Depends(get_async_session),
):
    """Legacy PDF endpoint. Redirects to new flow."""
    raise HTTPException(
        status_code=301,
        detail="Use GET /api/v1/exports/pdf?client_id=&period= instead",
        headers={"Location": f"/api/v1/exports/pdf?client_id={client_id}&period={period}"},
    )


@router.get("/{client_id}/gstr3b/{period}")
async def download_gstr3b_legacy(
    client_id: uuid.UUID,
    period: str,
    ca: CurrentCA,
    db: AsyncSession = Depends(get_async_session),
):
    """Legacy GSTR-3B endpoint. Redirects to new flow."""
    raise HTTPException(
        status_code=301,
        detail="Use GET /api/v1/exports/gstr3b?client_id=&period= instead",
        headers={"Location": f"/api/v1/exports/gstr3b?client_id={client_id}&period={period}"},
    )


@router.get("/{client_id}/tally/{period}")
async def download_tally_legacy(
    client_id: uuid.UUID,
    period: str,
    ca: CurrentCA,
):
    """TallyPrime XML export -- roadmap Q3 2026."""
    raise HTTPException(
        status_code=501,
        detail="TallyPrime XML export is on the roadmap for Q3 2026.",
    )


# ── Helpers ───────────────────────────────────────────────────────────

async def _get_client_or_404(
    client_id: uuid.UUID, ca_id: uuid.UUID, db: AsyncSession
) -> Client:
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.ca_id == ca_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


async def _get_period_invoices(
    client_id: uuid.UUID, ca_id: uuid.UUID, period: str, db: AsyncSession
) -> list[Invoice]:
    """Get invoices for a client in a specific filing period (MM-YYYY). CA-scoped."""
    result = await db.execute(
        select(Invoice).where(
            Invoice.client_id == client_id,
            Invoice.ca_id == ca_id,
            Invoice.filing_period == period,
        ).order_by(Invoice.total_amount.desc().nullslast())
    )
    return result.scalars().all()


async def _compute_itc_aggregates(
    client_id: uuid.UUID,
    ca_id: uuid.UUID,
    period: str,
    db: AsyncSession,
) -> dict:
    """
    Compute ITC aggregates for GSTR-3B and PDF generation.
    All values are Decimal, never float.
    Uses single aggregation query.
    """
    result = await db.execute(
        select(
            # Confirmed CGST
            func.coalesce(func.sum(case(
                (and_(
                    Invoice.status.in_(["ca_approved", "ca_overridden"]),
                    Invoice.is_itc_eligible_draft == True,
                    Invoice.ca_override_itc_eligible != False,
                ), Invoice.cgst_amount),
                else_=Decimal("0"),
            )), Decimal("0")).label("cgst_confirmed"),
            # Confirmed SGST
            func.coalesce(func.sum(case(
                (and_(
                    Invoice.status.in_(["ca_approved", "ca_overridden"]),
                    Invoice.is_itc_eligible_draft == True,
                    Invoice.ca_override_itc_eligible != False,
                ), Invoice.sgst_amount),
                else_=Decimal("0"),
            )), Decimal("0")).label("sgst_confirmed"),
            # Confirmed IGST
            func.coalesce(func.sum(case(
                (and_(
                    Invoice.status.in_(["ca_approved", "ca_overridden"]),
                    Invoice.is_itc_eligible_draft == True,
                    Invoice.ca_override_itc_eligible != False,
                ), Invoice.igst_amount),
                else_=Decimal("0"),
            )), Decimal("0")).label("igst_confirmed"),
            # Rejected CGST
            func.coalesce(func.sum(case(
                (and_(
                    Invoice.status.in_(["ca_approved", "ca_overridden", "ca_rejected"]),
                    (Invoice.is_itc_eligible_draft == False) | (Invoice.ca_override_itc_eligible == False),
                ), Invoice.cgst_amount),
                else_=Decimal("0"),
            )), Decimal("0")).label("cgst_rejected"),
            # Rejected SGST
            func.coalesce(func.sum(case(
                (and_(
                    Invoice.status.in_(["ca_approved", "ca_overridden", "ca_rejected"]),
                    (Invoice.is_itc_eligible_draft == False) | (Invoice.ca_override_itc_eligible == False),
                ), Invoice.sgst_amount),
                else_=Decimal("0"),
            )), Decimal("0")).label("sgst_rejected"),
            # Rejected IGST
            func.coalesce(func.sum(case(
                (and_(
                    Invoice.status.in_(["ca_approved", "ca_overridden", "ca_rejected"]),
                    (Invoice.is_itc_eligible_draft == False) | (Invoice.ca_override_itc_eligible == False),
                ), Invoice.igst_amount),
                else_=Decimal("0"),
            )), Decimal("0")).label("igst_rejected"),
            # Pending total
            func.coalesce(func.sum(case(
                (and_(
                    Invoice.status.in_(["processing", "pending_ca_review", "pending_client_confirmation"]),
                    Invoice.is_itc_eligible_draft == True,
                ), Invoice.cgst_amount + Invoice.sgst_amount + Invoice.igst_amount),
                else_=Decimal("0"),
            )), Decimal("0")).label("total_pending"),
            # RCM taxable
            func.coalesce(func.sum(case(
                (Invoice.is_rcm == True, Invoice.taxable_amount),
                else_=Decimal("0"),
            )), Decimal("0")).label("rcm_taxable"),
            # RCM CGST
            func.coalesce(func.sum(case(
                (Invoice.is_rcm == True, Invoice.cgst_amount),
                else_=Decimal("0"),
            )), Decimal("0")).label("rcm_cgst"),
            # RCM SGST
            func.coalesce(func.sum(case(
                (Invoice.is_rcm == True, Invoice.sgst_amount),
                else_=Decimal("0"),
            )), Decimal("0")).label("rcm_sgst"),
            # RCM IGST
            func.coalesce(func.sum(case(
                (Invoice.is_rcm == True, Invoice.igst_amount),
                else_=Decimal("0"),
            )), Decimal("0")).label("rcm_igst"),
        )
        .where(
            Invoice.client_id == client_id,
            Invoice.ca_id == ca_id,
            Invoice.filing_period == period,
        )
    )
    row = result.one()

    return {
        "cgst_confirmed": Decimal(str(row.cgst_confirmed or 0)),
        "sgst_confirmed": Decimal(str(row.sgst_confirmed or 0)),
        "igst_confirmed": Decimal(str(row.igst_confirmed or 0)),
        "cgst_rejected": Decimal(str(row.cgst_rejected or 0)),
        "sgst_rejected": Decimal(str(row.sgst_rejected or 0)),
        "igst_rejected": Decimal(str(row.igst_rejected or 0)),
        "total_pending": Decimal(str(row.total_pending or 0)),
        "rcm_taxable": Decimal(str(row.rcm_taxable or 0)),
        "rcm_cgst": Decimal(str(row.rcm_cgst or 0)),
        "rcm_sgst": Decimal(str(row.rcm_sgst or 0)),
        "rcm_igst": Decimal(str(row.rcm_igst or 0)),
    }
