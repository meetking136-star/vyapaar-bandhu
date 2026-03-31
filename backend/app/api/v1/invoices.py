"""
VyapaarBandhu -- Invoice Endpoints
Upload, status, raw URL, list, detail, approve, reject, override.
CA-scoped with audit trail.
"""

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.dependencies import CurrentCA
from app.models.invoice import Invoice
from app.models.classification_feedback import ClassificationFeedback
from app.schemas.invoice import (
    InvoiceApproveRequest,
    InvoiceOverrideRequest,
    InvoiceRejectRequest,
    InvoiceResponse,
    InvoiceUploadResponse,
    InvoiceStatusResponse,
    InvoiceRawURLResponse,
)
from app.schemas.summary import BulkActionRequest, BulkActionResponse
from app.utils.audit import write_audit_log

logger = structlog.get_logger()
router = APIRouter()

# Allowed file types for invoice upload
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "application/pdf",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


# ── Phase 3: Upload, Status, Raw endpoints ────────────────────────────

@router.post("/upload", response_model=InvoiceUploadResponse, status_code=202)
async def upload_invoice(
    ca: CurrentCA,
    db: AsyncSession = Depends(get_async_session),
    file: UploadFile = File(...),
    client_id: uuid.UUID = Form(...),
    filing_period: str = Form(...),
):
    """
    Upload an invoice image for OCR processing.
    Auth: CA JWT required.
    Body: multipart/form-data (file + client_id + filing_period).
    Returns 202 with invoice_id and status=queued.
    """
    from app.models.client import Client
    from app.utils.consent import assert_client_consent
    from app.services.storage.s3_client import upload_invoice_image
    from app.utils.dedup import compute_dedup_hash

    # Validate file type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{file.content_type}' not allowed. "
                   f"Accepted: {', '.join(ALLOWED_CONTENT_TYPES)}",
        )

    # Read file bytes and check size
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB",
        )

    # Verify client belongs to this CA
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.ca_id == ca.id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found or not owned by this CA")

    # Assert client consent (DPDP Act -- RULE 5)
    from app.utils.consent import ConsentNotGivenError, ConsentWithdrawnError
    try:
        await assert_client_consent(db, client_id)
    except (ConsentNotGivenError, ConsentWithdrawnError) as e:
        raise HTTPException(status_code=403, detail=str(e))

    # Upload raw file to S3
    s3_key = await upload_invoice_image(file_bytes, client_id)

    # Create a temporary dedup hash (will be updated after OCR extracts fields)
    temp_dedup = compute_dedup_hash(None, None, client_id, s3_key)

    # Create invoice record in "queued" state
    invoice = Invoice(
        client_id=client_id,
        ca_id=ca.id,
        image_s3_key=s3_key,
        source_type="api_upload",
        filing_period=filing_period,
        status="queued",
        dedup_hash=temp_dedup,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)

    # Queue Celery task for OCR processing
    from app.tasks.ocr_tasks import process_invoice
    process_invoice.delay(
        invoice_id=str(invoice.id),
        client_id=str(client_id),
        ca_id=str(ca.id),
        filing_period=filing_period,
        image_s3_key=s3_key,
    )

    logger.info(
        "invoice.upload.queued",
        invoice_id=str(invoice.id),
        client_id=str(client_id),
        ca_id=str(ca.id),
        file_size=len(file_bytes),
    )

    return InvoiceUploadResponse(
        invoice_id=invoice.id,
        status="queued",
        estimated_seconds=30,
    )


@router.get("/{invoice_id}/status", response_model=InvoiceStatusResponse)
async def get_invoice_status(
    invoice_id: uuid.UUID,
    ca: CurrentCA,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get processing status of an invoice.
    Returns extracted fields if processing is complete.
    """
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.ca_id == ca.id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return InvoiceStatusResponse(
        invoice_id=invoice.id,
        status=invoice.status,
        extracted_fields=invoice.extracted_fields_json,
        confidence_scores=invoice.ocr_confidence_json,
        low_confidence_fields=invoice.low_confidence_fields,
        classification=invoice.classification_json,
        is_rcm=invoice.is_rcm,
        rcm_category=invoice.rcm_category,
        ocr_provider=invoice.ocr_engine_used,
        processing_attempts=invoice.processing_attempts or 0,
        last_error_message=invoice.last_error_message,
        created_at=invoice.created_at,
        processed_at=invoice.ca_reviewed_at,
    )


@router.get("/{invoice_id}/raw", response_model=InvoiceRawURLResponse)
async def get_invoice_raw_url(
    invoice_id: uuid.UUID,
    ca: CurrentCA,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get a presigned S3 URL to the raw invoice image.
    Never streams the file through the API server.
    Expiry: 1 hour.
    """
    from app.services.storage.s3_client import generate_presigned_url
    from app.config import settings

    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.ca_id == ca.id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    presigned_url = generate_presigned_url(
        bucket=settings.S3_BUCKET_INVOICES,
        key=invoice.image_s3_key,
        expiry=3600,  # 1 hour
    )

    return InvoiceRawURLResponse(
        invoice_id=invoice.id,
        presigned_url=presigned_url,
        expires_in_seconds=3600,
    )


# ── Existing endpoints (from Phase 2) ────────────────────────────────

@router.get("/", response_model=list[InvoiceResponse])
async def list_invoices(
    ca: CurrentCA,
    db: AsyncSession = Depends(get_async_session),
    status: str | None = Query(None),
    client_id: uuid.UUID | None = Query(None),
    skip: int = 0,
    limit: int = 50,
):
    """List invoices with optional filters. CA-scoped."""
    query = select(Invoice).where(Invoice.ca_id == ca.id)

    if status:
        query = query.where(Invoice.status == status)
    if client_id:
        query = query.where(Invoice.client_id == client_id)

    query = query.offset(skip).limit(min(limit, 100)).order_by(Invoice.created_at.desc())

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: uuid.UUID,
    ca: CurrentCA,
    db: AsyncSession = Depends(get_async_session),
):
    """Get invoice detail with OCR confidence + flags. CA-scoped."""
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.ca_id == ca.id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.post("/{invoice_id}/approve", response_model=InvoiceResponse)
async def approve_invoice(
    invoice_id: uuid.UUID,
    req: InvoiceApproveRequest,
    ca: CurrentCA,
    db: AsyncSession = Depends(get_async_session),
):
    """CA approves invoice with optional category/ITC override."""
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.ca_id == ca.id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    old_status = invoice.status
    old_category = invoice.category
    old_itc = invoice.is_itc_eligible_draft

    invoice.status = "ca_approved"
    invoice.ca_reviewed_by = ca.id
    invoice.ca_reviewed_at = datetime.now(timezone.utc)

    if req.override_category:
        invoice.ca_override_category = req.override_category
        invoice.category = req.override_category
    if req.override_itc_eligible is not None:
        invoice.ca_override_itc_eligible = req.override_itc_eligible
        invoice.is_itc_eligible_draft = req.override_itc_eligible
    if req.notes:
        invoice.ca_override_notes = req.notes

    # Log classification feedback if category was overridden
    if req.override_category and old_category and req.override_category != old_category:
        feedback = ClassificationFeedback(
            invoice_id=invoice.id,
            original_category=old_category,
            corrected_category=req.override_category,
            original_method=invoice.classification_method or "unknown",
            ca_id=ca.id,
        )
        db.add(feedback)

    await write_audit_log(
        db,
        actor_type="ca",
        actor_id=ca.id,
        action="invoice.approved",
        entity_type="invoice",
        entity_id=invoice.id,
        old_value={"status": old_status, "category": old_category, "itc_eligible": old_itc},
        new_value={
            "status": "ca_approved",
            "category": invoice.category,
            "itc_eligible": invoice.is_itc_eligible_draft,
            "override_notes": req.notes,
        },
    )
    await db.commit()
    await db.refresh(invoice)
    return invoice


@router.post("/{invoice_id}/reject", response_model=InvoiceResponse)
async def reject_invoice(
    invoice_id: uuid.UUID,
    req: InvoiceRejectRequest,
    ca: CurrentCA,
    db: AsyncSession = Depends(get_async_session),
):
    """CA rejects invoice. Reason required."""
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.ca_id == ca.id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    old_status = invoice.status
    invoice.status = "ca_rejected"
    invoice.ca_reviewed_by = ca.id
    invoice.ca_reviewed_at = datetime.now(timezone.utc)
    invoice.ca_override_notes = req.reason

    await write_audit_log(
        db,
        actor_type="ca",
        actor_id=ca.id,
        action="invoice.rejected",
        entity_type="invoice",
        entity_id=invoice.id,
        old_value={"status": old_status},
        new_value={"status": "ca_rejected", "reason": req.reason},
    )
    await db.commit()
    await db.refresh(invoice)
    return invoice


@router.patch("/{invoice_id}/override", response_model=InvoiceResponse)
async def override_invoice(
    invoice_id: uuid.UUID,
    req: InvoiceOverrideRequest,
    ca: CurrentCA,
    db: AsyncSession = Depends(get_async_session),
):
    """CA overrides category + ITC eligibility. Logs to classification_feedback."""
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.ca_id == ca.id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    old_category = invoice.category
    old_itc = invoice.is_itc_eligible_draft

    invoice.status = "ca_overridden"
    invoice.ca_reviewed_by = ca.id
    invoice.ca_reviewed_at = datetime.now(timezone.utc)
    invoice.ca_override_category = req.category
    invoice.ca_override_itc_eligible = req.itc_eligible
    invoice.ca_override_notes = req.notes
    invoice.category = req.category
    invoice.is_itc_eligible_draft = req.itc_eligible
    invoice.classification_method = "ca_override"

    # Log for retraining pipeline
    if old_category and req.category != old_category:
        feedback = ClassificationFeedback(
            invoice_id=invoice.id,
            original_category=old_category,
            corrected_category=req.category,
            original_method=invoice.classification_method or "unknown",
            ca_id=ca.id,
        )
        db.add(feedback)

    await write_audit_log(
        db,
        actor_type="ca",
        actor_id=ca.id,
        action="invoice.overridden",
        entity_type="invoice",
        entity_id=invoice.id,
        old_value={"category": old_category, "itc_eligible": old_itc},
        new_value={
            "category": req.category,
            "itc_eligible": req.itc_eligible,
            "notes": req.notes,
        },
    )
    await db.commit()
    await db.refresh(invoice)
    return invoice


# ── Phase 5: Bulk action endpoint ─────────────────────────────────────

BULK_ACTION_STATUS_MAP = {
    "approve": "ca_approved",
    "reject": "ca_rejected",
    "flag": "flagged_low_confidence",
}
MAX_BULK_SIZE = 50


@router.post("/bulk-action", response_model=BulkActionResponse)
async def bulk_action_invoices(
    req: BulkActionRequest,
    ca: CurrentCA,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Bulk approve/reject/flag invoices.
    Max 50 invoices per request -- rejects 400 if more.
    CA isolation check on every invoice_id.
    """
    if len(req.invoice_ids) > MAX_BULK_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_BULK_SIZE} invoices per bulk action request",
        )

    target_status = BULK_ACTION_STATUS_MAP.get(req.action)
    if not target_status:
        raise HTTPException(status_code=400, detail=f"Invalid action: {req.action}")

    # Fetch all invoices in one query, filtered by CA
    result = await db.execute(
        select(Invoice).where(
            Invoice.id.in_(req.invoice_ids),
            Invoice.ca_id == ca.id,
        )
    )
    invoices = result.scalars().all()

    # Build a set of found IDs for error reporting
    found_ids = {inv.id for inv in invoices}
    now = datetime.now(timezone.utc)

    processed = 0
    failed = 0
    results = []

    for invoice_id in req.invoice_ids:
        if invoice_id not in found_ids:
            failed += 1
            results.append({
                "invoice_id": str(invoice_id),
                "success": False,
                "error": "Invoice not found or not owned by this CA",
            })
            continue

        # Find the invoice object
        invoice = next(inv for inv in invoices if inv.id == invoice_id)
        old_status = invoice.status
        invoice.status = target_status
        invoice.ca_reviewed_by = ca.id
        invoice.ca_reviewed_at = now

        await write_audit_log(
            db,
            actor_type="ca",
            actor_id=ca.id,
            action=f"invoice.bulk_{req.action}",
            entity_type="invoice",
            entity_id=invoice.id,
            old_value={"status": old_status},
            new_value={"status": target_status},
        )

        processed += 1
        results.append({
            "invoice_id": str(invoice_id),
            "success": True,
            "new_status": target_status,
        })

    await db.commit()

    logger.info(
        "invoices.bulk_action",
        ca_id=str(ca.id),
        action=req.action,
        processed=processed,
        failed=failed,
    )

    return BulkActionResponse(
        processed=processed,
        failed=failed,
        results=results,
    )
