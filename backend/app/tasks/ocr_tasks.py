"""
VyapaarBandhu -- Celery OCR Processing Tasks

Task: process_invoice
  Queue: ocr_queue
  Max retries: 3
  Retry backoff: exponential (30s, 120s, 480s)
  acks_late: True
  task_reject_on_worker_lost: True

RULE 5: Consent gate is the FIRST operation before reading any image data.
"""
from __future__ import annotations

import uuid
import json

import structlog
from celery import shared_task

from app.tasks.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(
    bind=True,
    name="app.tasks.ocr_tasks.process_invoice",
    max_retries=3,
    default_retry_delay=30,
    soft_time_limit=60,
    time_limit=90,
    acks_late=True,
    reject_on_worker_lost=True,
    queue="ocr",
)
def process_invoice(
    self,
    invoice_id: str,
    client_id: str,
    ca_id: str,
    filing_period: str,
    image_s3_key: str,
):
    """
    Process an uploaded invoice image through OCR + classification pipeline.

    Steps:
      1. Assert client consent (DPDP Act -- RULE 5)
      2. Download image from S3
      3. Run OCR pipeline (Vision API -> Tesseract fallback)
      4. Run invoice classification (B2B/B2C, interstate, RCM)
      5. Run compliance evaluation
      6. Update invoice record with extracted data
      7. On failure after 3 retries: move to dead-letter queue

    Retry backoff: 30s, 120s, 480s (exponential)
    """
    import asyncio

    try:
        asyncio.run(_process_invoice_async(
            self, invoice_id, client_id, ca_id, filing_period, image_s3_key,
        ))
    except Exception as exc:
        retry_delay = 30 * (4 ** self.request.retries)  # 30, 120, 480
        logger.error(
            "ocr_task.failed",
            invoice_id=invoice_id,
            attempt=self.request.retries + 1,
            error=str(exc),
        )
        try:
            self.retry(exc=exc, countdown=retry_delay)
        except self.MaxRetriesExceededError:
            # Move to dead-letter queue
            _handle_max_retries(invoice_id, client_id, ca_id, str(exc))


async def _process_invoice_async(
    task,
    invoice_id: str,
    client_id: str,
    ca_id: str,
    filing_period: str,
    image_s3_key: str,
):
    """Async implementation of invoice processing pipeline."""
    from decimal import Decimal
    from datetime import datetime, date, timezone

    from sqlalchemy import select

    from app.db.session import async_session_factory
    from app.models.invoice import Invoice
    from app.utils.consent import assert_client_consent, ConsentNotGivenError, ConsentWithdrawnError
    from app.services.storage.s3_client import download
    from app.services.ocr.pipeline import process_invoice_image, OCRFailedError
    from app.services.classification.invoice_classifier import classify_invoice
    from app.services.compliance.engine import evaluate_invoice_itc, InvoiceData, ClientData
    from app.models.client import Client
    from app.config import settings

    async with async_session_factory() as db:
        # ── Step 1: CONSENT GATE (RULE 5) ────────────────────────────
        # This MUST be the first operation before any data processing.
        try:
            client = await assert_client_consent(db, uuid.UUID(client_id))
        except (ConsentNotGivenError, ConsentWithdrawnError) as e:
            logger.warning(
                "ocr_task.consent_denied",
                invoice_id=invoice_id,
                client_id=client_id,
                reason=str(e),
            )
            # Update invoice status and stop processing
            result = await db.execute(
                select(Invoice).where(Invoice.id == uuid.UUID(invoice_id))
            )
            invoice = result.scalar_one_or_none()
            if invoice:
                invoice.status = "failed"
                invoice.last_error_message = f"Consent denied: {str(e)}"
                await db.commit()
            raise

        # ── Step 2: Download image from S3 ────────────────────────────
        image_bytes = await download(settings.S3_BUCKET_INVOICES, image_s3_key)

        # ── Step 3: Update processing attempts ────────────────────────
        result = await db.execute(
            select(Invoice).where(Invoice.id == uuid.UUID(invoice_id))
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            raise RuntimeError(f"Invoice {invoice_id} not found")

        invoice.processing_attempts = (invoice.processing_attempts or 0) + 1
        invoice.status = "processing"
        await db.commit()

        # ── Step 4: OCR pipeline ──────────────────────────────────────
        try:
            ocr_result = await process_invoice_image(image_bytes, image_s3_key)
        except OCRFailedError:
            invoice.status = "manual_review_required"
            invoice.ocr_engine_used = "failed"
            invoice.last_error_message = "Both OCR engines failed"
            await db.commit()
            logger.error("ocr_task.ocr_failed", invoice_id=invoice_id)
            return

        fields = ocr_result.fields

        # ── Step 5: Invoice classification ────────────────────────────
        classification = classify_invoice(
            gstin_supplier=fields.gstin_supplier,
            gstin_recipient=fields.gstin_recipient,
            hsn_sac_codes=fields.hsn_sac_codes,
            description=fields.product_description,
            igst_amount=fields.igst_amount,
            cgst_amount=fields.cgst_amount,
            sgst_amount=fields.sgst_amount,
            place_of_supply=fields.place_of_supply,
        )

        # ── Step 6: Compliance evaluation ─────────────────────────────
        invoice_data = InvoiceData(
            seller_gstin=fields.gstin_supplier,
            category=None,  # From existing classification pipeline
            product_description=fields.product_description,
            taxable_amount=fields.taxable_value or Decimal("0"),
            cgst_amount=fields.cgst_amount or Decimal("0"),
            sgst_amount=fields.sgst_amount or Decimal("0"),
            igst_amount=fields.igst_amount or Decimal("0"),
            total_amount=fields.total_amount or Decimal("0"),
        )
        client_data = ClientData(
            gstin=client.gstin,
            business_type=client.business_type,
            primary_activity=client.primary_activity,
            is_composition=client.is_composition,
        )
        evaluation = evaluate_invoice_itc(invoice_data, client_data)

        # ── Step 7: Determine invoice status ──────────────────────────
        if ocr_result.requires_manual_review:
            status = "manual_review_required"
        elif ocr_result.confidence_level == "red":
            status = "flagged_low_confidence"
        elif classification.requires_ca_review:
            status = "flagged_classification"
        else:
            status = "pending_ca_review"

        # ── Step 8: Parse date ────────────────────────────────────────
        invoice_date = None
        if fields.invoice_date:
            try:
                parts = fields.invoice_date.split("-")
                if len(parts) == 3:
                    invoice_date = date(int(parts[2]), int(parts[1]), int(parts[0]))
            except (ValueError, IndexError):
                pass

        # ── Step 9: Update invoice record ─────────────────────────────
        invoice.seller_gstin = fields.gstin_supplier
        invoice.seller_name = fields.seller_name
        invoice.invoice_number = fields.invoice_number
        invoice.invoice_date = invoice_date
        invoice.taxable_amount = fields.taxable_value or Decimal("0")
        invoice.cgst_amount = fields.cgst_amount or Decimal("0")
        invoice.sgst_amount = fields.sgst_amount or Decimal("0")
        invoice.igst_amount = fields.igst_amount or Decimal("0")
        invoice.total_amount = fields.total_amount or Decimal("0")
        invoice.product_description = fields.product_description

        # OCR metadata
        invoice.ocr_confidence_score = Decimal(str(ocr_result.confidence_score))
        invoice.ocr_provider = ocr_result.provider
        invoice.ocr_engine_used = ocr_result.provider
        invoice.ocr_raw_text = ocr_result.raw_text
        invoice.ocr_confidence_json = ocr_result.confidence_report.to_json()
        invoice.extracted_fields_json = fields.to_dict()
        invoice.low_confidence_fields = ocr_result.low_confidence_fields

        # GSTIN autocorrection
        invoice.gstin_was_autocorrected = fields.gstin_was_autocorrected
        invoice.gstin_original_ocr = fields.gstin_original_ocr

        # Classification
        invoice.classification_json = classification.to_json()
        invoice.is_rcm = classification.rcm_applicable
        invoice.rcm_category = classification.rcm_category

        # Compliance
        invoice.is_itc_eligible_draft = evaluation.is_eligible
        invoice.blocked_reason = evaluation.blocked_reason

        # Recalculate dedup hash now that we have real seller_gstin + invoice_number
        from app.utils.dedup import compute_dedup_hash
        invoice.dedup_hash = compute_dedup_hash(
            fields.gstin_supplier, fields.invoice_number,
            uuid.UUID(client_id), image_s3_key,
        )

        # Status
        invoice.status = status

        await db.commit()

        logger.info(
            "ocr_task.complete",
            invoice_id=invoice_id,
            status=status,
            provider=ocr_result.provider,
            confidence=ocr_result.confidence_score,
            b2b=classification.is_b2b,
            rcm=classification.rcm_applicable,
        )


def _handle_max_retries(
    invoice_id: str,
    client_id: str,
    ca_id: str,
    error_message: str,
):
    """
    Handle invoice after max retries exceeded.
    Moves to dead-letter queue, marks as failed, logs with PII masking.
    """
    import asyncio
    asyncio.run(_async_handle_max_retries(invoice_id, client_id, ca_id, error_message))


async def _async_handle_max_retries(
    invoice_id: str,
    client_id: str,
    ca_id: str,
    error_message: str,
):
    from sqlalchemy import select
    from app.db.session import async_session_factory
    from app.models.invoice import Invoice

    async with async_session_factory() as db:
        result = await db.execute(
            select(Invoice).where(Invoice.id == uuid.UUID(invoice_id))
        )
        invoice = result.scalar_one_or_none()
        if invoice:
            invoice.status = "failed"
            invoice.last_error_message = error_message[:500]
            await db.commit()

    # PII-masked logging
    masked_client = f"{client_id[:8]}...{client_id[-4:]}" if len(client_id) > 12 else "***"
    logger.error(
        "ocr_task.dead_letter",
        invoice_id=invoice_id,
        client_id_masked=masked_client,
        ca_id=ca_id,
        error=error_message[:200],
    )


@celery_app.task(
    name="app.tasks.ocr_tasks.reprocess_failed_invoices",
    soft_time_limit=300,
    time_limit=360,
)
def reprocess_failed_invoices():
    """
    Celery Beat task -- daily at 2 AM IST (20:30 UTC).
    Re-queues failed invoices from the last 7 days.
    Max 50 per run to avoid thundering herd.
    """
    import asyncio
    asyncio.run(_async_reprocess_failed())


async def _async_reprocess_failed():
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select
    from app.db.session import async_session_factory
    from app.models.invoice import Invoice

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    max_per_run = 50

    async with async_session_factory() as db:
        result = await db.execute(
            select(Invoice).where(
                Invoice.status == "failed",
                Invoice.created_at > cutoff,
                Invoice.processing_attempts < 6,  # Don't retry indefinitely
            ).order_by(Invoice.created_at.desc()).limit(max_per_run)
        )
        invoices = result.scalars().all()

        requeued = 0
        for inv in invoices:
            process_invoice.delay(
                invoice_id=str(inv.id),
                client_id=str(inv.client_id),
                ca_id=str(inv.ca_id),
                filing_period=inv.filing_period,
                image_s3_key=inv.image_s3_key,
            )
            requeued += 1

        logger.info(
            "reprocess.complete",
            total_failed=len(invoices),
            requeued=requeued,
        )
