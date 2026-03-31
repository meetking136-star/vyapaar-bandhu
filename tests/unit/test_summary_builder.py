"""
VyapaarBandhu — Summary Builder Unit Tests
Tests for aggregated ITC summary generation.
"""
from __future__ import annotations

import sys
import uuid
from decimal import Decimal, ROUND_HALF_UP
from unittest.mock import MagicMock

import pytest

# Mock out model imports before importing the module under test
_mock = MagicMock()
for mod in [
    "app.models", "app.models.client", "app.models.invoice",
    "app.models.ca_account", "app.models.base", "app.models.audit_log",
    "app.models.classification_feedback", "app.models.monthly_summary",
    "app.models.refresh_token", "app.models.reminder_log",
]:
    sys.modules.setdefault(mod, _mock)

from app.services.dashboard.summary_builder import _q, format_summary_row


def _make_row(
    cgst_confirmed=Decimal("0"),
    sgst_confirmed=Decimal("0"),
    igst_confirmed=Decimal("0"),
    total_pending=Decimal("0"),
    total_rejected=Decimal("0"),
    rcm_liability=Decimal("0"),
    invoice_count=0,
):
    row = MagicMock()
    row.cgst_confirmed = cgst_confirmed
    row.sgst_confirmed = sgst_confirmed
    row.igst_confirmed = igst_confirmed
    row.total_pending = total_pending
    row.total_rejected = total_rejected
    row.rcm_liability = rcm_liability
    row.invoice_count = invoice_count
    return row


class TestQuantize:
    def test_quantize_normal_value(self):
        assert _q(Decimal("1234.567")) == "1234.57"

    def test_quantize_half_up(self):
        """ROUND_HALF_UP: 0.005 -> 0.01"""
        assert _q(Decimal("0.005")) == "0.01"

    def test_quantize_none(self):
        assert _q(None) == "0.00"

    def test_quantize_zero(self):
        assert _q(Decimal("0")) == "0.00"

    def test_quantize_large_value(self):
        assert _q(Decimal("9999999999.995")) == "10000000000.00"

    def test_quantize_negative(self):
        assert _q(Decimal("-100.555")) == "-100.56"

    def test_quantize_returns_string(self):
        result = _q(Decimal("42.00"))
        assert isinstance(result, str)

    def test_quantize_round_half_up_boundary(self):
        """0.015 rounds to 0.02 with ROUND_HALF_UP."""
        assert _q(Decimal("0.015")) == "0.02"

    def test_quantize_many_decimals(self):
        assert _q(Decimal("100.999999")) == "101.00"


class TestFormatSummaryRow:
    def test_basic_summary(self):
        row = _make_row(
            cgst_confirmed=Decimal("1000.00"),
            sgst_confirmed=Decimal("1000.00"),
            igst_confirmed=Decimal("500.00"),
            total_pending=Decimal("300.00"),
            total_rejected=Decimal("50.00"),
            rcm_liability=Decimal("200.00"),
            invoice_count=25,
        )
        summary = format_summary_row(row, "03-2026")

        assert summary["period"] == "03-2026"
        assert summary["cgst_confirmed"] == "1000.00"
        assert summary["sgst_confirmed"] == "1000.00"
        assert summary["igst_confirmed"] == "500.00"
        assert summary["total_confirmed"] == "2500.00"
        assert summary["total_pending"] == "300.00"
        assert summary["total_rejected"] == "50.00"
        assert summary["rcm_liability"] == "200.00"
        assert summary["invoice_count"] == 25

    def test_zero_values(self):
        row = _make_row()
        summary = format_summary_row(row, "01-2026")

        assert summary["total_confirmed"] == "0.00"
        assert summary["total_pending"] == "0.00"
        assert summary["total_rejected"] == "0.00"
        assert summary["rcm_liability"] == "0.00"
        assert summary["invoice_count"] == 0

    def test_none_values_treated_as_zero(self):
        row = _make_row(
            cgst_confirmed=None,
            sgst_confirmed=None,
            igst_confirmed=None,
            total_pending=None,
            total_rejected=None,
            rcm_liability=None,
            invoice_count=None,
        )
        summary = format_summary_row(row, "02-2026")

        assert summary["total_confirmed"] == "0.00"
        assert summary["invoice_count"] == 0

    def test_decimal_precision(self):
        row = _make_row(
            cgst_confirmed=Decimal("100.555"),
            sgst_confirmed=Decimal("200.445"),
            igst_confirmed=Decimal("0.005"),
            total_pending=Decimal("50.995"),
            total_rejected=Decimal("10.004"),
            rcm_liability=Decimal("25.555"),
            invoice_count=3,
        )
        summary = format_summary_row(row, "03-2026")

        # ROUND_HALF_UP
        assert summary["cgst_confirmed"] == "100.56"
        assert summary["sgst_confirmed"] == "200.45"
        assert summary["igst_confirmed"] == "0.01"
        # Sum raw (100.555+200.445+0.005=301.005) then round: 301.01
        assert summary["total_confirmed"] == "301.01"
        assert summary["total_pending"] == "51.00"
        assert summary["total_rejected"] == "10.00"
        assert summary["rcm_liability"] == "25.56"

    def test_values_are_strings_not_floats(self):
        """CRITICAL: All monetary values must be strings, never float."""
        row = _make_row(
            cgst_confirmed=Decimal("100.00"),
            sgst_confirmed=Decimal("100.00"),
            igst_confirmed=Decimal("0"),
            total_pending=Decimal("50.00"),
            total_rejected=Decimal("10.00"),
            rcm_liability=Decimal("25.00"),
            invoice_count=5,
        )
        summary = format_summary_row(row, "03-2026")

        for key in [
            "cgst_confirmed", "sgst_confirmed", "igst_confirmed",
            "total_confirmed", "total_pending", "total_rejected", "rcm_liability",
        ]:
            assert isinstance(summary[key], str), f"{key} should be str, got {type(summary[key])}"
            assert "e" not in summary[key].lower()

    def test_total_confirmed_is_sum_of_components(self):
        """total_confirmed = cgst + sgst + igst."""
        row = _make_row(
            cgst_confirmed=Decimal("333.33"),
            sgst_confirmed=Decimal("444.44"),
            igst_confirmed=Decimal("555.55"),
        )
        summary = format_summary_row(row, "03-2026")

        expected = Decimal("333.33") + Decimal("444.44") + Decimal("555.55")
        assert summary["total_confirmed"] == str(
            expected.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )
