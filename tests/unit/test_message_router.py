"""
VyapaarBandhu -- Unit Tests for Webhook Handler (Message Router)
Tests idempotency, client lookup, and delegation to state machine.
"""
from __future__ import annotations

import pytest

from app.services.whatsapp.session_store import SessionStore


# ── Session Store Tests ──────────────────────────────────────────────

class FakeRedis:
    """Minimal fake Redis for testing SessionStore."""

    def __init__(self):
        self._data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: int = None) -> None:
        self._data[key] = value

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def exists(self, key: str) -> int:
        return 1 if key in self._data else 0


@pytest.fixture
def redis():
    return FakeRedis()


@pytest.fixture
def session_store(redis):
    return SessionStore(redis)


PHONE = "+919876543210"


class TestSessionStore:

    @pytest.mark.asyncio
    async def test_get_default_session(self, session_store):
        """Empty store returns IDLE session."""
        session = await session_store.get_session(PHONE)
        assert session["state"] == "IDLE"
        assert session["lang"] == "en"

    @pytest.mark.asyncio
    async def test_set_and_get_session(self, session_store):
        await session_store.set_session(PHONE, {
            "state": "AWAITING_CONSENT", "lang": "hi"
        })
        session = await session_store.get_session(PHONE)
        assert session["state"] == "AWAITING_CONSENT"
        assert session["lang"] == "hi"
        assert "last_updated" in session

    @pytest.mark.asyncio
    async def test_clear_session(self, session_store):
        await session_store.set_session(PHONE, {"state": "PROCESSING", "lang": "en"})
        await session_store.clear_session(PHONE)
        session = await session_store.get_session(PHONE)
        assert session["state"] == "IDLE"

    @pytest.mark.asyncio
    async def test_message_idempotency(self, session_store):
        """RULE 4: Duplicate message_id detection."""
        msg_id = "wamid.abc123"
        assert await session_store.is_message_processed(msg_id) is False
        await session_store.mark_message_processed(msg_id)
        assert await session_store.is_message_processed(msg_id) is True

    @pytest.mark.asyncio
    async def test_empty_message_id_not_processed(self, session_store):
        """Empty message_id should not be considered processed."""
        assert await session_store.is_message_processed("") is False


# ── Bilingual Templates Tests ────────────────────────────────────────

class TestBilingualTemplates:

    def test_all_templates_have_both_languages(self):
        from app.services.whatsapp.bilingual_templates import BILINGUAL_TEMPLATES
        for key, translations in BILINGUAL_TEMPLATES.items():
            assert "en" in translations, f"Template '{key}' missing English"
            assert "hi" in translations, f"Template '{key}' missing Hindi"

    def test_consent_request_contains_dpdp(self):
        from app.services.whatsapp.bilingual_templates import BILINGUAL_TEMPLATES
        assert "DPDP" in BILINGUAL_TEMPLATES["consent_request"]["en"]
        assert "DPDP" in BILINGUAL_TEMPLATES["consent_request"]["hi"]

    def test_deadline_reminder_has_placeholders(self):
        from app.services.whatsapp.bilingual_templates import BILINGUAL_TEMPLATES
        en = BILINGUAL_TEMPLATES["deadline_reminder"]["en"]
        assert "{days}" in en
        assert "{count}" in en


# ── Media Downloader Tests ───────────────────────────────────────────

class TestMediaDownloaderConstants:

    def test_timeout_is_30_seconds(self):
        from app.services.whatsapp.media_downloader import MEDIA_DOWNLOAD_TIMEOUT
        assert MEDIA_DOWNLOAD_TIMEOUT == 30

    def test_exceptions_hierarchy(self):
        from app.services.whatsapp.media_downloader import (
            MediaDownloadError,
            MediaDownloadTimeout,
        )
        assert issubclass(MediaDownloadTimeout, MediaDownloadError)
