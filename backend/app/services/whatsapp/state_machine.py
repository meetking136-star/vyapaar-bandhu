"""
VyapaarBandhu -- WhatsApp Conversation State Machine
All conversation logic lives here. webhook_handler.py only routes to this.

States:
  IDLE -> AWAITING_CONSENT -> CONSENT_GIVEN -> AWAITING_INVOICE_IMAGE
  -> PROCESSING -> COMPLETED | AWAITING_CLARIFICATION

RULE 1: Consent gate -- NEVER process data without consent.
RULE 2: Hindi + English support via language detection.
RULE 3: No business logic in webhook_handler.py -- it all lives here.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

import structlog

from app.services.whatsapp.session_store import SessionStore

logger = structlog.get_logger()

# ── State constants ────────────────────────────────────────────────────
IDLE = "IDLE"
AWAITING_CONSENT = "AWAITING_CONSENT"
CONSENT_GIVEN = "CONSENT_GIVEN"
AWAITING_INVOICE_IMAGE = "AWAITING_INVOICE_IMAGE"
PROCESSING = "PROCESSING"
AWAITING_CLARIFICATION = "AWAITING_CLARIFICATION"
COMPLETED = "COMPLETED"

# ── Consent keywords (case-insensitive) ────────────────────────────────
CONSENT_YES = {"yes", "haan", "ha", "agree", "ok"}
CONSENT_NO = {"no", "nahi", "disagree", "nah"}
STOP_WORDS = {"stop", "cancel", "ruko", "band"}
INVOICE_KEYWORDS = {"invoice", "upload", "bill", "challan", "photo", "bhejo"}
STATUS_KEYWORDS = {"status", "kya hua", "update"}
HELP_KEYWORDS = {"help", "madad"}

# Hindi character range for language detection (Devanagari block)
HINDI_RE = re.compile(r"[\u0900-\u097F]")


def detect_language(text: str) -> str:
    """
    Detect language preference from message text.
    RULE 2: If Hindi characters present, prefer Hindi.
    """
    if HINDI_RE.search(text):
        return "hi"
    return "en"


class StateMachineResult:
    """Result from state machine processing -- contains reply and side effects."""

    def __init__(self):
        self.reply: str | None = None
        self.should_queue_ocr: bool = False
        self.media_id: str | None = None
        self.client_id: str | None = None
        self.ca_id: str | None = None
        self.should_record_consent: bool = False
        self.should_withdraw_consent: bool = False

    def with_reply(self, msg: str) -> "StateMachineResult":
        self.reply = msg
        return self


class ConversationStateMachine:
    """
    Per-phone-number conversation state machine.
    All decisions about what to do with an incoming message live here.
    """

    def __init__(self, session_store: SessionStore, templates: dict):
        self._store = session_store
        self._t = templates  # bilingual message templates

    async def handle_message(
        self,
        phone: str,
        message_type: str,
        text: str,
        media_id: str | None,
        is_known_client: bool,
        client_has_consent: bool,
        client_consent_withdrawn: bool,
        client_id: str | None = None,
        ca_id: str | None = None,
    ) -> StateMachineResult:
        """
        Process an incoming message and return the result.

        This is the single entry point for all message handling logic.
        webhook_handler.py calls this and acts on the result.
        """
        result = StateMachineResult()
        session = await self._store.get_session(phone)
        state = session.get("state", IDLE)
        lang = session.get("lang", "en")

        text_lower = text.strip().lower() if text else ""

        # Detect language from first meaningful message
        if text and state == IDLE:
            lang = detect_language(text)
            session["lang"] = lang

        # ── STOP/CANCEL from any state -> IDLE ─────────────────────
        if text_lower in STOP_WORDS:
            await self._store.clear_session(phone)
            result.reply = self._msg("cancelled", lang)
            return result

        # ── Unknown client ─────────────────────────────────────────
        if not is_known_client:
            return await self._transition_to_awaiting_consent(session, phone, lang, result)

        # ── Consent withdrawn -- silently ignore ───────────────────
        if client_consent_withdrawn:
            return result  # No reply

        # ── State dispatch ─────────────────────────────────────────
        if state == IDLE:
            if not client_has_consent:
                return await self._transition_to_awaiting_consent(
                    session, phone, lang, result
                )
            # Client has consent -- treat as CONSENT_GIVEN
            session["state"] = CONSENT_GIVEN
            session["lang"] = lang
            state = CONSENT_GIVEN

        if state == AWAITING_CONSENT:
            return await self._handle_awaiting_consent(
                session, phone, lang, text_lower, result
            )

        if state == CONSENT_GIVEN:
            return await self._handle_consent_given(
                session, phone, lang, text_lower, message_type, media_id,
                client_id, ca_id, result,
            )

        if state == AWAITING_INVOICE_IMAGE:
            return await self._handle_awaiting_image(
                session, phone, lang, message_type, media_id,
                client_id, ca_id, result,
            )

        if state == PROCESSING:
            result.reply = self._msg("still_processing", lang)
            return result

        if state == AWAITING_CLARIFICATION:
            return await self._handle_awaiting_clarification(
                session, phone, lang, message_type, media_id,
                client_id, ca_id, result,
            )

        if state == COMPLETED:
            # Reset to CONSENT_GIVEN for next interaction
            session["state"] = CONSENT_GIVEN
            await self._store.set_session(phone, session)
            return await self._handle_consent_given(
                session, phone, lang, text_lower, message_type, media_id,
                client_id, ca_id, result,
            )

        # Fallback
        result.reply = self._msg("help", lang)
        return result

    # ── State handlers ─────────────────────────────────────────────────

    async def _transition_to_awaiting_consent(
        self, session: dict, phone: str, lang: str, result: StateMachineResult
    ) -> StateMachineResult:
        session["state"] = AWAITING_CONSENT
        session["lang"] = lang
        await self._store.set_session(phone, session)
        result.reply = self._msg("consent_request", lang)
        return result

    async def _handle_awaiting_consent(
        self, session: dict, phone: str, lang: str,
        text_lower: str, result: StateMachineResult,
    ) -> StateMachineResult:
        """RULE 1: Consent gate. Only YES/HAAN proceeds."""
        if text_lower in CONSENT_YES:
            session["state"] = CONSENT_GIVEN
            await self._store.set_session(phone, session)
            result.should_record_consent = True
            result.reply = self._msg("consent_given", lang)
            return result

        if text_lower in CONSENT_NO:
            await self._store.clear_session(phone)
            result.reply = self._msg("consent_denied", lang)
            return result

        # Any other message -- repeat consent request
        result.reply = self._msg("consent_request", lang)
        return result

    async def _handle_consent_given(
        self, session: dict, phone: str, lang: str,
        text_lower: str, message_type: str, media_id: str | None,
        client_id: str | None, ca_id: str | None,
        result: StateMachineResult,
    ) -> StateMachineResult:
        # Image received directly -> process it
        if message_type in ("image", "document") and media_id:
            return await self._start_ocr(
                session, phone, lang, media_id, client_id, ca_id, result
            )

        # Text commands
        if any(kw in text_lower for kw in INVOICE_KEYWORDS):
            session["state"] = AWAITING_INVOICE_IMAGE
            await self._store.set_session(phone, session)
            result.reply = self._msg("send_invoice_image", lang)
            return result

        if any(kw in text_lower for kw in STATUS_KEYWORDS):
            result.reply = self._msg("status_check", lang)
            return result

        if any(kw in text_lower for kw in HELP_KEYWORDS):
            result.reply = self._msg("help", lang)
            return result

        if text_lower in ("withdraw consent", "delete mera data"):
            result.should_withdraw_consent = True
            await self._store.clear_session(phone)
            result.reply = self._msg("consent_withdrawn", lang)
            return result

        # Unrecognised
        result.reply = self._msg("help", lang)
        return result

    async def _handle_awaiting_image(
        self, session: dict, phone: str, lang: str,
        message_type: str, media_id: str | None,
        client_id: str | None, ca_id: str | None,
        result: StateMachineResult,
    ) -> StateMachineResult:
        if message_type in ("image", "document") and media_id:
            return await self._start_ocr(
                session, phone, lang, media_id, client_id, ca_id, result
            )

        # Not an image -- remind them
        result.reply = self._msg("send_invoice_image", lang)
        return result

    async def _handle_awaiting_clarification(
        self, session: dict, phone: str, lang: str,
        message_type: str, media_id: str | None,
        client_id: str | None, ca_id: str | None,
        result: StateMachineResult,
    ) -> StateMachineResult:
        """User resends image after low-confidence OCR."""
        if message_type in ("image", "document") and media_id:
            return await self._start_ocr(
                session, phone, lang, media_id, client_id, ca_id, result
            )

        result.reply = self._msg("ocr_low_confidence", lang)
        return result

    async def _start_ocr(
        self, session: dict, phone: str, lang: str,
        media_id: str, client_id: str | None, ca_id: str | None,
        result: StateMachineResult,
    ) -> StateMachineResult:
        """Transition to PROCESSING and signal OCR task queue."""
        session["state"] = PROCESSING
        session["media_id"] = media_id
        await self._store.set_session(phone, session)

        result.reply = self._msg("invoice_received", lang)
        result.should_queue_ocr = True
        result.media_id = media_id
        result.client_id = client_id
        result.ca_id = ca_id
        return result

    # ── Template helper ────────────────────────────────────────────────

    def _msg(self, key: str, lang: str) -> str:
        """Get a bilingual message template."""
        templates = self._t.get(key, {})
        return templates.get(lang, templates.get("en", f"[{key}]"))
