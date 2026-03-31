"""
VyapaarBandhu -- WhatsApp Webhook API Endpoints (Phase 4)
POST /webhook  -- receive inbound messages (Twilio signature validated)
GET  /webhook  -- Twilio/Meta verification handshake

RULE 7: Every incoming POST must validate X-Twilio-Signature.
Response is always 200 to prevent Twilio retries.
"""
from __future__ import annotations

import hashlib
import hmac

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_async_session

logger = structlog.get_logger()
router = APIRouter()


def _validate_twilio_signature(request_url: str, params: dict, signature: str) -> bool:
    """
    Validate X-Twilio-Signature header per Twilio's algorithm.
    RULE 7: Reject with 403 if signature is invalid.
    """
    if not settings.WA_APP_SECRET:
        # In development, skip validation if no secret configured
        logger.warning("webhook.signature_validation_skipped", reason="no_app_secret")
        return True

    # Twilio signature: HMAC-SHA1 of (URL + sorted POST params)
    data = request_url
    for key in sorted(params.keys()):
        data += key + params[key]

    expected = hmac.new(
        settings.WA_APP_SECRET.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha1,
    ).digest()

    import base64
    expected_b64 = base64.b64encode(expected).decode("utf-8")
    return hmac.compare_digest(expected_b64, signature)


def _validate_meta_signature(payload: bytes, signature: str) -> bool:
    """
    Validate X-Hub-Signature-256 header for Meta Cloud API webhooks.
    Falls back to this if using Meta instead of Twilio.
    """
    if not settings.WA_APP_SECRET:
        logger.warning("webhook.signature_validation_skipped", reason="no_app_secret")
        return True

    expected = hmac.new(
        settings.WA_APP_SECRET.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    received = signature.replace("sha256=", "") if signature.startswith("sha256=") else signature
    return hmac.compare_digest(expected, received)


@router.get("/webhook")
async def webhook_verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    """
    GET /webhook -- Twilio/Meta verification handshake.
    Returns hub.challenge if verify_token matches.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.WA_VERIFY_TOKEN:
        logger.info("webhook.verified")
        return PlainTextResponse(content=hub_challenge or "")

    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def webhook_receive(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
):
    """
    POST /webhook -- Receive inbound WhatsApp messages.
    RULE 7: Validates signature before processing.
    Always returns 200 to prevent Twilio/Meta retries.
    """
    body = await request.body()

    # ── Signature validation ──────────────────────────────────────
    meta_sig = request.headers.get("X-Hub-Signature-256", "")
    twilio_sig = request.headers.get("X-Twilio-Signature", "")

    if meta_sig:
        if not _validate_meta_signature(body, meta_sig):
            logger.warning("webhook.invalid_meta_signature")
            raise HTTPException(status_code=403, detail="Invalid signature")
    elif twilio_sig:
        form_data = await request.form()
        params = {k: v for k, v in form_data.items()}
        request_url = str(request.url)
        if not _validate_twilio_signature(request_url, params, twilio_sig):
            logger.warning("webhook.invalid_twilio_signature")
            raise HTTPException(status_code=403, detail="Invalid signature")
    elif settings.WA_APP_SECRET:
        # Secret is configured but no signature header present
        logger.warning("webhook.missing_signature")
        raise HTTPException(status_code=403, detail="Missing signature")

    # ── Parse payload ─────────────────────────────────────────────
    try:
        payload = await request.json()
    except Exception:
        # Return 200 even on parse failure to prevent retries
        return {"status": "ok"}

    # ── Extract messages from Meta Cloud API format ───────────────
    messages = _extract_messages(payload)
    if not messages:
        return {"status": "ok"}

    # ── Process each message ──────────────────────────────────────
    from app.services.whatsapp.webhook_handler import handle_incoming_message
    from app.services.whatsapp.session_store import SessionStore
    import redis.asyncio as aioredis

    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    session_store = SessionStore(redis_client)

    try:
        for phone, message in messages:
            try:
                await handle_incoming_message(phone, message, db, session_store)
            except Exception as exc:
                logger.error(
                    "webhook.message_error",
                    phone_masked=phone[:5] + "XXXXX" if phone else "unknown",
                    error=str(exc)[:200],
                )
    finally:
        await redis_client.close()

    # Always return 200
    return {"status": "ok"}


def _extract_messages(payload: dict) -> list[tuple[str, dict]]:
    """
    Extract (phone, message) pairs from Meta Cloud API webhook payload.
    Returns empty list if payload format is not recognised.
    """
    messages = []

    # Meta Cloud API format
    entry = payload.get("entry", [])
    for e in entry:
        changes = e.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            contacts = value.get("contacts", [])
            msgs = value.get("messages", [])
            # Build phone lookup from contacts
            phone_map = {}
            for contact in contacts:
                wa_id = contact.get("wa_id", "")
                phone_map[wa_id] = wa_id

            for msg in msgs:
                from_phone = msg.get("from", "")
                messages.append((from_phone, msg))

    # Twilio format fallback
    if not messages and "From" in payload:
        phone = payload.get("From", "").replace("whatsapp:", "")
        msg = {
            "id": payload.get("MessageSid", ""),
            "type": "image" if payload.get("NumMedia", "0") != "0" else "text",
            "text": {"body": payload.get("Body", "")},
        }
        if payload.get("NumMedia", "0") != "0":
            msg["image"] = {"id": payload.get("MediaUrl0", "")}
        messages.append((phone, msg))

    return messages
