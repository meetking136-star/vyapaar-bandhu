"""
VyapaarBandhu -- Dead Letter Queue Handler
Handles invoices that have exhausted all retry attempts.

Responsibilities:
  1. Log failed invoice with PII-masked client info
  2. Update invoice status to "failed"
  3. Record error details for debugging
  4. (Phase 8) Trigger CA notification webhook
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()


def handle_dead_letter(
    invoice_id: str,
    client_id: str,
    ca_id: str,
    error_message: str,
    task_name: str = "unknown",
    attempts: int = 0,
):
    """
    Process a dead-letter queue entry.
    Called when a Celery task has exhausted all retries.

    Logs with PII masking: client_id is partially masked to prevent
    accidental PII exposure in log aggregation systems.
    """
    # PII masking: show only first 8 and last 4 chars of UUIDs
    masked_client = _mask_uuid(client_id)

    logger.error(
        "dlq.entry",
        invoice_id=invoice_id,
        client_id_masked=masked_client,
        ca_id=ca_id,
        task=task_name,
        attempts=attempts,
        error=_truncate(error_message, 500),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Update invoice in database
    import asyncio
    asyncio.run(_update_failed_invoice(invoice_id, error_message))


async def _update_failed_invoice(invoice_id: str, error_message: str):
    """Mark invoice as failed in database."""
    from sqlalchemy import select
    from app.db.session import async_session_factory
    from app.models.invoice import Invoice

    try:
        async with async_session_factory() as db:
            result = await db.execute(
                select(Invoice).where(Invoice.id == uuid.UUID(invoice_id))
            )
            invoice = result.scalar_one_or_none()
            if invoice:
                invoice.status = "failed"
                invoice.last_error_message = _truncate(error_message, 500)
                await db.commit()
                logger.info("dlq.invoice_updated", invoice_id=invoice_id, status="failed")
    except Exception as e:
        logger.error("dlq.db_update_failed", invoice_id=invoice_id, error=str(e))


def _mask_uuid(raw: str) -> str:
    """Mask a UUID string for PII-safe logging."""
    if not raw or len(raw) < 12:
        return "***"
    return f"{raw[:8]}...{raw[-4:]}"


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len characters."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."
