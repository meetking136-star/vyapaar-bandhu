"""
VyapaarBandhu -- Redis-backed WhatsApp Session Store
Stores conversation state per phone number with 24-hour TTL.
Provides idempotency tracking for processed message IDs.

RULE 4: Duplicate message_ids are tracked here to prevent reprocessing.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()

SESSION_TTL = 86400  # 24 hours in seconds
MESSAGE_ID_TTL = 86400  # 24 hours -- matches WhatsApp retry window
SESSION_PREFIX = "wa_session:"
MSG_ID_PREFIX = "wa_msg_id:"


class SessionStore:
    """
    Redis-backed session store for WhatsApp conversations.
    Each phone number has one session dict stored as JSON.
    """

    def __init__(self, redis_client):
        self._redis = redis_client

    async def get_session(self, phone: str) -> dict:
        """
        Get conversation session for a phone number.
        Returns default IDLE session if none exists.
        """
        data = await self._redis.get(f"{SESSION_PREFIX}{phone}")
        if data:
            return json.loads(data)
        return {"state": "IDLE", "lang": "en"}

    async def set_session(self, phone: str, session: dict) -> None:
        """Set conversation session with 24-hour TTL."""
        session["last_updated"] = datetime.now(timezone.utc).isoformat()
        await self._redis.set(
            f"{SESSION_PREFIX}{phone}",
            json.dumps(session),
            ex=SESSION_TTL,
        )

    async def clear_session(self, phone: str) -> None:
        """Clear conversation session (reset to IDLE on next access)."""
        await self._redis.delete(f"{SESSION_PREFIX}{phone}")

    async def is_message_processed(self, message_id: str) -> bool:
        """
        Check if a WhatsApp message ID has already been processed.
        RULE 4: Idempotent webhook -- prevents duplicate processing.
        """
        if not message_id:
            return False
        return await self._redis.exists(f"{MSG_ID_PREFIX}{message_id}") > 0

    async def mark_message_processed(self, message_id: str) -> None:
        """Mark a message ID as processed with 24-hour TTL."""
        if message_id:
            await self._redis.set(
                f"{MSG_ID_PREFIX}{message_id}",
                "1",
                ex=MESSAGE_ID_TTL,
            )
