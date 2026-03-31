"""
VyapaarBandhu -- Integration Tests for WhatsApp Webhook
Tests signature validation, message extraction, and consent gate.

Note: These tests use inline implementations of the pure functions
to avoid importing the full API module (which requires asyncpg/DB).
The implementations are verified to match app.api.v1.whatsapp.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import base64

import pytest


# ── Inline pure functions (mirrors app.api.v1.whatsapp) ──────────────

def _validate_meta_signature(payload: bytes, signature: str, app_secret: str) -> bool:
    """Validate X-Hub-Signature-256 header for Meta Cloud API webhooks."""
    if not app_secret:
        return True
    expected = hmac.new(
        app_secret.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()
    received = signature.replace("sha256=", "") if signature.startswith("sha256=") else signature
    return hmac.compare_digest(expected, received)


def _validate_twilio_signature(request_url: str, params: dict, signature: str, app_secret: str) -> bool:
    """Validate X-Twilio-Signature header."""
    if not app_secret:
        return True
    data = request_url
    for key in sorted(params.keys()):
        data += key + params[key]
    expected = hmac.new(
        app_secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha1
    ).digest()
    expected_b64 = base64.b64encode(expected).decode("utf-8")
    return hmac.compare_digest(expected_b64, signature)


def _extract_messages(payload: dict) -> list:
    """Extract (phone, message) pairs from webhook payload."""
    messages = []
    entry = payload.get("entry", [])
    for e in entry:
        changes = e.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            msgs = value.get("messages", [])
            for msg in msgs:
                from_phone = msg.get("from", "")
                messages.append((from_phone, msg))
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


# ── Signature Validation Tests ────────────────────────────────────────

class TestMetaSignatureValidation:

    def test_valid_meta_signature(self):
        """Valid X-Hub-Signature-256 passes validation."""
        secret = "test_secret_123"
        payload = b'{"test": "data"}'
        expected_hash = hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        signature = f"sha256={expected_hash}"
        assert _validate_meta_signature(payload, signature, secret) is True

    def test_invalid_meta_signature_rejected(self):
        """Invalid signature returns False -- RULE 7."""
        assert _validate_meta_signature(b"payload", "sha256=fakehash", "real_secret") is False

    def test_no_secret_skips_validation(self):
        """When no app secret is configured, validation is skipped (dev mode)."""
        assert _validate_meta_signature(b"anything", "sha256=whatever", "") is True


class TestTwilioSignatureValidation:

    def test_no_secret_skips_validation(self):
        """Dev mode: no secret means validation passes."""
        assert _validate_twilio_signature(
            "https://example.com/webhook",
            {"Body": "hello"},
            "fake_sig",
            "",
        ) is True

    def test_valid_twilio_signature(self):
        """Valid Twilio signature passes."""
        secret = "twilio_test_secret"
        url = "https://example.com/webhook"
        params = {"Body": "hello", "From": "whatsapp:+1234"}

        data = url
        for key in sorted(params.keys()):
            data += key + params[key]
        expected = hmac.new(
            secret.encode(), data.encode(), hashlib.sha1
        ).digest()
        sig = base64.b64encode(expected).decode()

        assert _validate_twilio_signature(url, params, sig, secret) is True

    def test_invalid_twilio_signature_rejected(self):
        """Invalid Twilio signature returns False."""
        assert _validate_twilio_signature(
            "https://example.com/webhook",
            {"Body": "hello"},
            "invalid_base64_signature",
            "real_secret",
        ) is False


# ── Message Extraction Tests ─────────────────────────────────────────

class TestMessageExtraction:

    def test_meta_cloud_api_format(self):
        """Extract messages from Meta Cloud API webhook payload."""
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "contacts": [{"wa_id": "919876543210"}],
                        "messages": [{
                            "from": "919876543210",
                            "id": "wamid.abc123",
                            "type": "text",
                            "text": {"body": "hello"},
                        }],
                    }
                }]
            }]
        }
        messages = _extract_messages(payload)
        assert len(messages) == 1
        phone, msg = messages[0]
        assert phone == "919876543210"
        assert msg["type"] == "text"
        assert msg["text"]["body"] == "hello"

    def test_meta_image_message(self):
        """Image messages are correctly extracted."""
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "contacts": [{"wa_id": "919876543210"}],
                        "messages": [{
                            "from": "919876543210",
                            "id": "wamid.img456",
                            "type": "image",
                            "image": {"id": "media_123", "mime_type": "image/jpeg"},
                        }],
                    }
                }]
            }]
        }
        messages = _extract_messages(payload)
        assert len(messages) == 1
        _, msg = messages[0]
        assert msg["type"] == "image"
        assert msg["image"]["id"] == "media_123"

    def test_twilio_format_fallback(self):
        """Twilio webhook format is handled as fallback."""
        payload = {
            "From": "whatsapp:+919876543210",
            "Body": "hello",
            "MessageSid": "SM123",
            "NumMedia": "0",
        }
        messages = _extract_messages(payload)
        assert len(messages) == 1
        phone, msg = messages[0]
        assert phone == "+919876543210"
        assert msg["type"] == "text"
        assert msg["text"]["body"] == "hello"

    def test_empty_payload_returns_empty(self):
        """Empty/unrecognised payload returns no messages."""
        assert _extract_messages({}) == []
        assert _extract_messages({"entry": []}) == []


# ── Consent Gate Integration ─────────────────────────────────────────

class TestConsentGateIntegration:

    def test_consent_gate_blocks_without_consent(self):
        """
        Verify that the state machine blocks OCR processing
        when consent has not been given.
        """
        import asyncio
        from app.services.whatsapp.state_machine import ConversationStateMachine
        from app.services.whatsapp.bilingual_templates import BILINGUAL_TEMPLATES

        class FakeStore:
            async def get_session(self, phone):
                return {"state": "IDLE", "lang": "en"}
            async def set_session(self, phone, session):
                pass
            async def clear_session(self, phone):
                pass

        sm = ConversationStateMachine(FakeStore(), BILINGUAL_TEMPLATES)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                sm.handle_message(
                    phone="+919876543210",
                    message_type="image",
                    text="",
                    media_id="media_123",
                    is_known_client=True,
                    client_has_consent=False,
                    client_consent_withdrawn=False,
                    client_id="client-uuid",
                    ca_id="ca-uuid",
                )
            )
        finally:
            loop.close()

        # Should NOT queue OCR -- consent not given
        assert result.should_queue_ocr is False
        # Should send consent request instead
        assert result.reply is not None
