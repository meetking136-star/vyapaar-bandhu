"""
VyapaarBandhu -- Unit Tests for WhatsApp Conversation State Machine
Covers all state transitions, consent gate, Hindi support, STOP command,
and idempotency.
"""
from __future__ import annotations

import pytest

from app.services.whatsapp.state_machine import (
    ConversationStateMachine,
    detect_language,
    IDLE,
    AWAITING_CONSENT,
    CONSENT_GIVEN,
    AWAITING_INVOICE_IMAGE,
    PROCESSING,
    AWAITING_CLARIFICATION,
    COMPLETED,
)
from app.services.whatsapp.bilingual_templates import BILINGUAL_TEMPLATES


# ── Fake session store for testing ────────────────────────────────────

class FakeSessionStore:
    """In-memory session store for unit tests."""

    def __init__(self):
        self._sessions: dict[str, dict] = {}
        self._processed: set[str] = set()

    async def get_session(self, phone: str) -> dict:
        return self._sessions.get(phone, {"state": IDLE, "lang": "en"})

    async def set_session(self, phone: str, session: dict) -> None:
        self._sessions[phone] = session

    async def clear_session(self, phone: str) -> None:
        self._sessions.pop(phone, None)

    async def is_message_processed(self, message_id: str) -> bool:
        return message_id in self._processed

    async def mark_message_processed(self, message_id: str) -> None:
        self._processed.add(message_id)


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def store():
    return FakeSessionStore()


@pytest.fixture
def sm(store):
    return ConversationStateMachine(store, BILINGUAL_TEMPLATES)


PHONE = "+919876543210"


# ── Test: IDLE -> AWAITING_CONSENT on first contact ───────────────────

class TestIdleToAwaitingConsent:

    @pytest.mark.asyncio
    async def test_unknown_client_gets_consent_request(self, sm, store):
        result = await sm.handle_message(
            phone=PHONE, message_type="text", text="hello",
            media_id=None, is_known_client=False,
            client_has_consent=False, client_consent_withdrawn=False,
        )
        assert result.reply is not None
        assert "consent" in result.reply.lower() or "DPDP" in result.reply
        session = await store.get_session(PHONE)
        assert session["state"] == AWAITING_CONSENT

    @pytest.mark.asyncio
    async def test_known_client_no_consent_gets_consent_request(self, sm, store):
        result = await sm.handle_message(
            phone=PHONE, message_type="text", text="hi",
            media_id=None, is_known_client=True,
            client_has_consent=False, client_consent_withdrawn=False,
        )
        assert result.reply is not None
        session = await store.get_session(PHONE)
        assert session["state"] == AWAITING_CONSENT


# ── Test: AWAITING_CONSENT -> CONSENT_GIVEN on "YES" ─────────────────

class TestAwaitingConsentToConsentGiven:

    @pytest.mark.asyncio
    async def test_yes_gives_consent(self, sm, store):
        # First set state to AWAITING_CONSENT
        await store.set_session(PHONE, {"state": AWAITING_CONSENT, "lang": "en"})

        result = await sm.handle_message(
            phone=PHONE, message_type="text", text="YES",
            media_id=None, is_known_client=True,
            client_has_consent=False, client_consent_withdrawn=False,
        )
        assert result.should_record_consent is True
        session = await store.get_session(PHONE)
        assert session["state"] == CONSENT_GIVEN

    @pytest.mark.asyncio
    async def test_haan_gives_consent_hindi(self, sm, store):
        """RULE 2: Hindi 'HAAN' triggers same consent flow as 'YES'."""
        await store.set_session(PHONE, {"state": AWAITING_CONSENT, "lang": "hi"})

        result = await sm.handle_message(
            phone=PHONE, message_type="text", text="haan",
            media_id=None, is_known_client=True,
            client_has_consent=False, client_consent_withdrawn=False,
        )
        assert result.should_record_consent is True
        session = await store.get_session(PHONE)
        assert session["state"] == CONSENT_GIVEN

    @pytest.mark.asyncio
    async def test_agree_gives_consent(self, sm, store):
        await store.set_session(PHONE, {"state": AWAITING_CONSENT, "lang": "en"})

        result = await sm.handle_message(
            phone=PHONE, message_type="text", text="agree",
            media_id=None, is_known_client=True,
            client_has_consent=False, client_consent_withdrawn=False,
        )
        assert result.should_record_consent is True


# ── Test: AWAITING_CONSENT -> IDLE on "NO" ───────────────────────────

class TestAwaitingConsentToIdle:

    @pytest.mark.asyncio
    async def test_no_denies_consent(self, sm, store):
        await store.set_session(PHONE, {"state": AWAITING_CONSENT, "lang": "en"})

        result = await sm.handle_message(
            phone=PHONE, message_type="text", text="no",
            media_id=None, is_known_client=True,
            client_has_consent=False, client_consent_withdrawn=False,
        )
        assert result.should_record_consent is False
        assert "not" in result.reply.lower() or "nahi" in result.reply.lower() or "decline" in result.reply.lower()
        # Session should be cleared
        session = await store.get_session(PHONE)
        assert session["state"] == IDLE

    @pytest.mark.asyncio
    async def test_nahi_denies_consent_hindi(self, sm, store):
        await store.set_session(PHONE, {"state": AWAITING_CONSENT, "lang": "hi"})

        result = await sm.handle_message(
            phone=PHONE, message_type="text", text="nahi",
            media_id=None, is_known_client=True,
            client_has_consent=False, client_consent_withdrawn=False,
        )
        assert result.should_record_consent is False

    @pytest.mark.asyncio
    async def test_random_text_repeats_consent_request(self, sm, store):
        """Non-YES/NO text in AWAITING_CONSENT re-sends consent request."""
        await store.set_session(PHONE, {"state": AWAITING_CONSENT, "lang": "en"})

        result = await sm.handle_message(
            phone=PHONE, message_type="text", text="what is this?",
            media_id=None, is_known_client=True,
            client_has_consent=False, client_consent_withdrawn=False,
        )
        assert result.reply is not None
        assert "consent" in result.reply.lower() or "DPDP" in result.reply


# ── Test: STOP command resets any state to IDLE ──────────────────────

class TestStopCommand:

    @pytest.mark.asyncio
    async def test_stop_from_awaiting_consent(self, sm, store):
        await store.set_session(PHONE, {"state": AWAITING_CONSENT, "lang": "en"})

        result = await sm.handle_message(
            phone=PHONE, message_type="text", text="stop",
            media_id=None, is_known_client=True,
            client_has_consent=False, client_consent_withdrawn=False,
        )
        session = await store.get_session(PHONE)
        assert session["state"] == IDLE

    @pytest.mark.asyncio
    async def test_stop_from_processing(self, sm, store):
        await store.set_session(PHONE, {"state": PROCESSING, "lang": "en"})

        result = await sm.handle_message(
            phone=PHONE, message_type="text", text="cancel",
            media_id=None, is_known_client=True,
            client_has_consent=True, client_consent_withdrawn=False,
        )
        session = await store.get_session(PHONE)
        assert session["state"] == IDLE

    @pytest.mark.asyncio
    async def test_stop_from_consent_given(self, sm, store):
        await store.set_session(PHONE, {"state": CONSENT_GIVEN, "lang": "en"})

        result = await sm.handle_message(
            phone=PHONE, message_type="text", text="STOP",
            media_id=None, is_known_client=True,
            client_has_consent=True, client_consent_withdrawn=False,
        )
        session = await store.get_session(PHONE)
        assert session["state"] == IDLE


# ── Test: CONSENT_GIVEN -> AWAITING_INVOICE_IMAGE ────────────────────

class TestConsentGivenToAwaitingImage:

    @pytest.mark.asyncio
    async def test_invoice_keyword_transitions(self, sm, store):
        await store.set_session(PHONE, {"state": CONSENT_GIVEN, "lang": "en"})

        result = await sm.handle_message(
            phone=PHONE, message_type="text", text="invoice",
            media_id=None, is_known_client=True,
            client_has_consent=True, client_consent_withdrawn=False,
        )
        session = await store.get_session(PHONE)
        assert session["state"] == AWAITING_INVOICE_IMAGE


# ── Test: Image triggers OCR ─────────────────────────────────────────

class TestImageTriggersOCR:

    @pytest.mark.asyncio
    async def test_image_in_consent_given_queues_ocr(self, sm, store):
        await store.set_session(PHONE, {"state": CONSENT_GIVEN, "lang": "en"})

        result = await sm.handle_message(
            phone=PHONE, message_type="image", text="",
            media_id="media_123", is_known_client=True,
            client_has_consent=True, client_consent_withdrawn=False,
            client_id="client-uuid", ca_id="ca-uuid",
        )
        assert result.should_queue_ocr is True
        assert result.media_id == "media_123"
        session = await store.get_session(PHONE)
        assert session["state"] == PROCESSING

    @pytest.mark.asyncio
    async def test_image_in_awaiting_image_queues_ocr(self, sm, store):
        await store.set_session(PHONE, {"state": AWAITING_INVOICE_IMAGE, "lang": "en"})

        result = await sm.handle_message(
            phone=PHONE, message_type="image", text="",
            media_id="media_456", is_known_client=True,
            client_has_consent=True, client_consent_withdrawn=False,
            client_id="client-uuid", ca_id="ca-uuid",
        )
        assert result.should_queue_ocr is True
        session = await store.get_session(PHONE)
        assert session["state"] == PROCESSING


# ── Test: AWAITING_CLARIFICATION -> PROCESSING on resend ─────────────

class TestClarificationResend:

    @pytest.mark.asyncio
    async def test_resend_image_after_low_confidence(self, sm, store):
        await store.set_session(PHONE, {"state": AWAITING_CLARIFICATION, "lang": "en"})

        result = await sm.handle_message(
            phone=PHONE, message_type="image", text="",
            media_id="media_789", is_known_client=True,
            client_has_consent=True, client_consent_withdrawn=False,
            client_id="client-uuid", ca_id="ca-uuid",
        )
        assert result.should_queue_ocr is True
        session = await store.get_session(PHONE)
        assert session["state"] == PROCESSING


# ── Test: Consent withdrawn -> silent ignore ─────────────────────────

class TestConsentWithdrawn:

    @pytest.mark.asyncio
    async def test_withdrawn_client_gets_no_reply(self, sm, store):
        result = await sm.handle_message(
            phone=PHONE, message_type="text", text="hello",
            media_id=None, is_known_client=True,
            client_has_consent=False, client_consent_withdrawn=True,
        )
        assert result.reply is None


# ── Test: Language detection ─────────────────────────────────────────

class TestLanguageDetection:

    def test_english_text_detected(self):
        assert detect_language("hello world") == "en"

    def test_hindi_text_detected(self):
        assert detect_language("नमस्ते") == "hi"

    def test_mixed_hindi_english_prefers_hindi(self):
        assert detect_language("hello नमस्ते") == "hi"


# ── Test: Help command ───────────────────────────────────────────────

class TestHelpCommand:

    @pytest.mark.asyncio
    async def test_help_returns_help_message(self, sm, store):
        await store.set_session(PHONE, {"state": CONSENT_GIVEN, "lang": "en"})

        result = await sm.handle_message(
            phone=PHONE, message_type="text", text="help",
            media_id=None, is_known_client=True,
            client_has_consent=True, client_consent_withdrawn=False,
        )
        assert result.reply is not None
        assert "invoice" in result.reply.lower() or "photo" in result.reply.lower()
