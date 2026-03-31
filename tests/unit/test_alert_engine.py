"""
VyapaarBandhu — Alert Engine Unit Tests
Tests for compliance alert generation logic.
"""
from __future__ import annotations

import sys
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock out model and compliance imports to avoid Python 3.9 type annotation issues
_mock = MagicMock()
for mod in [
    "app.models", "app.models.client", "app.models.invoice",
    "app.models.ca_account", "app.models.base", "app.models.audit_log",
    "app.models.classification_feedback", "app.models.monthly_summary",
    "app.models.refresh_token", "app.models.reminder_log",
    "app.services.compliance.deadline_calculator",
]:
    sys.modules.setdefault(mod, _mock)

from app.services.dashboard import alert_engine
from app.services.dashboard.alert_engine import generate_alerts


def _make_row(
    client_id=None,
    business_name="Test Business",
    owner_name="Test Owner",
    total_invoices=5,
    flagged_count=0,
    pending_count=0,
):
    """Create a mock row matching the query result shape."""
    row = MagicMock()
    row.id = client_id or uuid.uuid4()
    row.business_name = business_name
    row.owner_name = owner_name
    row.total_invoices = total_invoices
    row.flagged_count = flagged_count
    row.pending_count = pending_count
    return row


class TestDeadlineAlerts:
    @pytest.mark.asyncio
    async def test_critical_deadline_alert_when_3_days_or_less(self):
        """Should generate red alert when deadline <= 3 days."""
        ca_id = uuid.uuid4()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.all.return_value = [_make_row()]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch.object(alert_engine, "select", return_value=MagicMock()), \
             patch.object(alert_engine, "get_gstr3b_deadline", return_value=date(2026, 4, 20)), \
             patch.object(alert_engine, "date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 18)

            alerts = await generate_alerts(mock_db, ca_id=ca_id)

        deadline_alerts = [a for a in alerts if a["type"] == "deadline_critical"]
        assert len(deadline_alerts) == 1
        assert deadline_alerts[0]["severity"] == "red"
        assert "2 days" in deadline_alerts[0]["message"]

    @pytest.mark.asyncio
    async def test_warning_deadline_alert_when_4_to_7_days(self):
        """Should generate yellow alert when deadline 4-7 days away."""
        ca_id = uuid.uuid4()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.all.return_value = [_make_row()]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch.object(alert_engine, "select", return_value=MagicMock()), \
             patch.object(alert_engine, "get_gstr3b_deadline", return_value=date(2026, 4, 20)), \
             patch.object(alert_engine, "date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 14)

            alerts = await generate_alerts(mock_db, ca_id=ca_id)

        warning_alerts = [a for a in alerts if a["type"] == "deadline_warning"]
        assert len(warning_alerts) == 1
        assert warning_alerts[0]["severity"] == "yellow"

    @pytest.mark.asyncio
    async def test_no_deadline_alert_when_more_than_7_days(self):
        """Should NOT generate deadline alert when > 7 days away."""
        ca_id = uuid.uuid4()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.all.return_value = [_make_row()]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch.object(alert_engine, "select", return_value=MagicMock()), \
             patch.object(alert_engine, "get_gstr3b_deadline", return_value=date(2026, 4, 20)), \
             patch.object(alert_engine, "date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 1)

            alerts = await generate_alerts(mock_db, ca_id=ca_id)

        deadline_alerts = [
            a for a in alerts
            if a["type"] in ("deadline_critical", "deadline_warning")
        ]
        assert len(deadline_alerts) == 0


class TestClientAlerts:
    @pytest.mark.asyncio
    async def test_flagged_invoices_alert(self):
        """Should generate alert for flagged invoices."""
        ca_id = uuid.uuid4()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.all.return_value = [
            _make_row(business_name="Flagged Biz", flagged_count=3)
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch.object(alert_engine, "select", return_value=MagicMock()), \
             patch.object(alert_engine, "get_gstr3b_deadline", return_value=date(2026, 4, 20)), \
             patch.object(alert_engine, "date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 1)

            alerts = await generate_alerts(mock_db, ca_id=ca_id)

        flagged_alerts = [a for a in alerts if a["type"] == "flagged_invoices"]
        assert len(flagged_alerts) == 1
        assert "Flagged Biz" in flagged_alerts[0]["message"]
        assert "3 invoice(s)" in flagged_alerts[0]["message"]

    @pytest.mark.asyncio
    async def test_no_invoices_alert(self):
        """Should generate alert when client has zero invoices."""
        ca_id = uuid.uuid4()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.all.return_value = [
            _make_row(business_name="Empty Biz", total_invoices=0)
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch.object(alert_engine, "select", return_value=MagicMock()), \
             patch.object(alert_engine, "get_gstr3b_deadline", return_value=date(2026, 4, 20)), \
             patch.object(alert_engine, "date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 1)

            alerts = await generate_alerts(mock_db, ca_id=ca_id)

        no_inv_alerts = [a for a in alerts if a["type"] == "no_invoices"]
        assert len(no_inv_alerts) == 1
        assert "Empty Biz" in no_inv_alerts[0]["message"]

    @pytest.mark.asyncio
    async def test_high_pending_alert(self):
        """Should generate alert when > 10 pending invoices."""
        ca_id = uuid.uuid4()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.all.return_value = [
            _make_row(business_name="Busy Biz", pending_count=15)
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch.object(alert_engine, "select", return_value=MagicMock()), \
             patch.object(alert_engine, "get_gstr3b_deadline", return_value=date(2026, 4, 20)), \
             patch.object(alert_engine, "date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 1)

            alerts = await generate_alerts(mock_db, ca_id=ca_id)

        high_pending = [a for a in alerts if a["type"] == "high_pending"]
        assert len(high_pending) == 1
        assert "15 invoices" in high_pending[0]["message"]

    @pytest.mark.asyncio
    async def test_no_alert_for_low_pending(self):
        """Should NOT generate high_pending alert when <= 10 pending."""
        ca_id = uuid.uuid4()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.all.return_value = [
            _make_row(business_name="Small Biz", pending_count=5)
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch.object(alert_engine, "select", return_value=MagicMock()), \
             patch.object(alert_engine, "get_gstr3b_deadline", return_value=date(2026, 4, 20)), \
             patch.object(alert_engine, "date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 1)

            alerts = await generate_alerts(mock_db, ca_id=ca_id)

        high_pending = [a for a in alerts if a["type"] == "high_pending"]
        assert len(high_pending) == 0

    @pytest.mark.asyncio
    async def test_alerts_sorted_by_severity(self):
        """Red alerts should come before yellow alerts."""
        ca_id = uuid.uuid4()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.all.return_value = [
            _make_row(business_name="Flagged", flagged_count=2),
            _make_row(business_name="Empty", total_invoices=0),
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch.object(alert_engine, "select", return_value=MagicMock()), \
             patch.object(alert_engine, "get_gstr3b_deadline", return_value=date(2026, 4, 20)), \
             patch.object(alert_engine, "date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 18)

            alerts = await generate_alerts(mock_db, ca_id=ca_id)

        # Red alerts should come first
        red_indices = [i for i, a in enumerate(alerts) if a["severity"] == "red"]
        yellow_indices = [i for i, a in enumerate(alerts) if a["severity"] == "yellow"]
        if red_indices and yellow_indices:
            assert max(red_indices) < min(yellow_indices)

    @pytest.mark.asyncio
    async def test_empty_client_list(self):
        """Should handle no clients gracefully."""
        ca_id = uuid.uuid4()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch.object(alert_engine, "select", return_value=MagicMock()), \
             patch.object(alert_engine, "get_gstr3b_deadline", return_value=date(2026, 4, 20)), \
             patch.object(alert_engine, "date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 1)

            alerts = await generate_alerts(mock_db, ca_id=ca_id)

        # Only deadline alerts possible (if applicable), no client-specific
        client_alerts = [a for a in alerts if a.get("client_id") is not None]
        assert len(client_alerts) == 0
