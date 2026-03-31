"""
VyapaarBandhu -- WhatsApp Webhook Handler
Routes inbound messages to the state machine. NO business logic here.

RULE 3: This module only parses the webhook payload and delegates
to state_machine.py for all decisions.
RULE 4: Idempotent -- checks message_id before processing.
"""
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.services.whatsapp.session_store import SessionStore
from app.services.whatsapp.state_machine import ConversationStateMachine
from app.services.whatsapp import client as wa_client
from app.services.whatsapp.bilingual_templates import BILINGUAL_TEMPLATES
from app.utils.phone import normalize_phone

logger = structlog.get_logger()


async def handle_incoming_message(
    phone: str,
    message: dict,
    db: AsyncSession,
    session_store: SessionStore,
) -> None:
    """
    Handle a single inbound WhatsApp message.
    Parses the message, checks idempotency, looks up client,
    delegates to state machine, and executes side effects.

    RULE 3: No business logic -- just routing and side effects.
    """
    message_id = message.get("id", "")
    message_type = message.get("type", "")
    normalized_phone = normalize_phone(phone)

    # ── RULE 4: Idempotency check ─────────────────────────────────
    if await session_store.is_message_processed(message_id):
        logger.debug("webhook.duplicate_message", message_id=message_id)
        return

    # Mark as processed immediately to prevent races
    await session_store.mark_message_processed(message_id)

    # ── Extract text and media_id from message ────────────────────
    text = ""
    media_id = None

    if message_type == "text":
        text = message.get("text", {}).get("body", "")
    elif message_type in ("image", "document"):
        media_data = message.get(message_type, {})
        media_id = media_data.get("id")

    # ── Client lookup ─────────────────────────────────────────────
    result = await db.execute(
        select(Client).where(Client.whatsapp_phone == normalized_phone)
    )
    client = result.scalar_one_or_none()

    is_known = client is not None
    has_consent = bool(client and client.consent_given_at and not client.consent_withdrawn_at)
    consent_withdrawn = bool(client and client.consent_withdrawn_at)
    client_id = str(client.id) if client else None
    ca_id = str(client.ca_id) if client else None

    # ── Delegate to state machine ─────────────────────────────────
    sm = ConversationStateMachine(session_store, BILINGUAL_TEMPLATES)
    sm_result = await sm.handle_message(
        phone=normalized_phone,
        message_type=message_type,
        text=text,
        media_id=media_id,
        is_known_client=is_known,
        client_has_consent=has_consent,
        client_consent_withdrawn=consent_withdrawn,
        client_id=client_id,
        ca_id=ca_id,
    )

    # ── Execute side effects ──────────────────────────────────────

    # Send reply
    if sm_result.reply:
        await wa_client.send_text(normalized_phone, sm_result.reply)

    # Record consent
    if sm_result.should_record_consent and client:
        from app.utils.consent import record_consent
        await record_consent(db, client.id)
        await db.commit()

    # Withdraw consent
    if sm_result.should_withdraw_consent and client:
        from app.utils.consent import withdraw_consent
        await withdraw_consent(db, client.id)
        await db.commit()

    # Queue OCR task
    if sm_result.should_queue_ocr and sm_result.media_id:
        from app.tasks.ocr_tasks import process_invoice
        from app.services.whatsapp.media_downloader import (
            download_whatsapp_media,
            MediaDownloadTimeout,
            MediaDownloadError,
        )
        from app.services.storage.s3_client import upload_invoice_image
        from app.utils.dedup import compute_dedup_hash
        from app.models.invoice import Invoice
        import uuid as uuid_mod

        try:
            image_bytes = await download_whatsapp_media(sm_result.media_id)
        except MediaDownloadTimeout:
            # RULE 5: Reset state and ask user to resend
            await session_store.set_session(normalized_phone, {
                "state": "AWAITING_INVOICE_IMAGE",
                "lang": (await session_store.get_session(normalized_phone)).get("lang", "en"),
            })
            lang = (await session_store.get_session(normalized_phone)).get("lang", "en")
            from app.services.whatsapp.bilingual_templates import BILINGUAL_TEMPLATES as bt
            timeout_msg = bt.get("media_timeout", {}).get(lang, "Image download timed out. Please resend.")
            await wa_client.send_text(normalized_phone, timeout_msg)
            return
        except MediaDownloadError:
            lang = (await session_store.get_session(normalized_phone)).get("lang", "en")
            from app.services.whatsapp.bilingual_templates import BILINGUAL_TEMPLATES as bt
            fail_msg = bt.get("ocr_failed", {}).get(lang, "Could not download image. Please try again.")
            await wa_client.send_text(normalized_phone, fail_msg)
            return

        # Upload to S3
        client_uuid = uuid_mod.UUID(sm_result.client_id)
        s3_key = await upload_invoice_image(image_bytes, client_uuid)

        # Create invoice record
        filing_period = f"{__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%m-%Y')}"
        temp_dedup = compute_dedup_hash(None, None, client_uuid, s3_key)

        invoice = Invoice(
            client_id=client_uuid,
            ca_id=uuid_mod.UUID(sm_result.ca_id),
            image_s3_key=s3_key,
            source_type="whatsapp_photo",
            filing_period=filing_period,
            status="queued",
            dedup_hash=temp_dedup,
            whatsapp_message_id=message_id,
        )
        db.add(invoice)
        await db.commit()
        await db.refresh(invoice)

        # Dispatch Celery task
        process_invoice.delay(
            invoice_id=str(invoice.id),
            client_id=sm_result.client_id,
            ca_id=sm_result.ca_id,
            filing_period=filing_period,
            image_s3_key=s3_key,
        )

    # Mark as read
    if message_id and client:
        await wa_client.mark_as_read(message_id)
