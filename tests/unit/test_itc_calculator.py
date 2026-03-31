"""
VyapaarBandhu — ITC Calculator Unit Tests
Decimal precision tests for tax amount calculations.
Covers per-invoice calculation, eligibility, and aggregate ITC.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest

from app.services.compliance.itc_calculator import (
    ITCAmounts,
    AggregateITC,
    calculate_itc_amounts,
    is_itc_eligible,
    is_itc_rejected,
    compute_aggregate_itc,
    _to_decimal,
    ZERO,
    CONFIRMED_STATUSES,
    PENDING_STATUSES,
)


# ── Helper: fake invoice object ───────────────────────────────────────

@dataclass
class FakeInvoice:
    status: str = "ca_approved"
    cgst_amount: Decimal = Decimal("0")
    sgst_amount: Decimal = Decimal("0")
    igst_amount: Decimal = Decimal("0")
    taxable_amount: Decimal = Decimal("0")
    is_itc_eligible_draft: bool = True
    ca_override_itc_eligible: bool = None
    is_rcm: bool = False


# ── Per-Invoice ITC Calculation ───────────────────────────────────────

class TestIntraStateITC:
    def test_basic_cgst_sgst(self):
        result = calculate_itc_amounts(
            cgst=Decimal("900"), sgst=Decimal("900"), igst=Decimal("0"),
            is_interstate=False,
        )
        assert result.cgst == Decimal("900.00")
        assert result.sgst == Decimal("900.00")
        assert result.igst == Decimal("0.00")
        assert result.total == Decimal("1800.00")

    def test_decimal_precision(self):
        result = calculate_itc_amounts(
            cgst=Decimal("450.555"), sgst=Decimal("450.555"), igst=None,
            is_interstate=False,
        )
        # ROUND_HALF_UP: 450.555 -> 450.56
        assert result.cgst == Decimal("450.56")
        assert result.sgst == Decimal("450.56")
        # Sum raw (450.555+450.555=901.110) then round: 901.11
        assert result.total == Decimal("901.11")

    def test_none_values_become_zero(self):
        result = calculate_itc_amounts(
            cgst=None, sgst=None, igst=None,
            is_interstate=False,
        )
        assert result.total == Decimal("0.00")


class TestInterStateITC:
    def test_basic_igst(self):
        result = calculate_itc_amounts(
            cgst=Decimal("0"), sgst=Decimal("0"), igst=Decimal("1800"),
            is_interstate=True,
        )
        assert result.igst == Decimal("1800.00")
        assert result.cgst == Decimal("0.00")
        assert result.sgst == Decimal("0.00")
        assert result.total == Decimal("1800.00")

    def test_igst_with_decimal(self):
        result = calculate_itc_amounts(
            cgst=Decimal("0"), sgst=Decimal("0"), igst=Decimal("6062.035"),
            is_interstate=True,
        )
        # ROUND_HALF_UP: 6062.035 -> 6062.04
        assert result.igst == Decimal("6062.04")
        assert result.total == Decimal("6062.04")

    def test_interstate_ignores_cgst_sgst(self):
        """Even if CGST/SGST are provided, interstate uses IGST only."""
        result = calculate_itc_amounts(
            cgst=Decimal("500"), sgst=Decimal("500"), igst=Decimal("1000"),
            is_interstate=True,
        )
        assert result.igst == Decimal("1000.00")
        assert result.cgst == Decimal("0.00")
        assert result.total == Decimal("1000.00")


class TestEdgeCases:
    def test_negative_values_become_zero(self):
        result = calculate_itc_amounts(
            cgst=Decimal("-100"), sgst=Decimal("200"), igst=Decimal("0"),
            is_interstate=False,
        )
        assert result.cgst == Decimal("0.00")
        assert result.sgst == Decimal("200.00")
        assert result.total == Decimal("200.00")

    def test_zero_amounts(self):
        result = calculate_itc_amounts(
            cgst=Decimal("0"), sgst=Decimal("0"), igst=Decimal("0"),
            is_interstate=False,
        )
        assert result.total == Decimal("0.00")

    def test_large_amounts(self):
        result = calculate_itc_amounts(
            cgst=Decimal("9999999999999.99"),
            sgst=Decimal("0.01"),
            igst=Decimal("0"),
            is_interstate=False,
        )
        assert result.total == Decimal("10000000000000.00")


# ── _to_decimal ───────────────────────────────────────────────────────

class TestToDecimal:
    def test_none_returns_zero(self):
        assert _to_decimal(None) == ZERO

    def test_negative_returns_zero(self):
        assert _to_decimal(Decimal("-50")) == ZERO

    def test_float_converted(self):
        result = _to_decimal(100.5)
        assert result == Decimal("100.5")

    def test_int_converted(self):
        assert _to_decimal(42) == Decimal("42")


# ── ITC Eligibility ──────────────────────────────────────────────────

class TestITCEligibility:
    def test_eligible_when_draft_true_no_override(self):
        inv = FakeInvoice(is_itc_eligible_draft=True, ca_override_itc_eligible=None)
        assert is_itc_eligible(inv) is True

    def test_not_eligible_when_draft_false(self):
        inv = FakeInvoice(is_itc_eligible_draft=False)
        assert is_itc_eligible(inv) is False

    def test_not_eligible_when_draft_none(self):
        inv = FakeInvoice(is_itc_eligible_draft=None)
        assert is_itc_eligible(inv) is False

    def test_not_eligible_when_ca_override_false(self):
        inv = FakeInvoice(is_itc_eligible_draft=True, ca_override_itc_eligible=False)
        assert is_itc_eligible(inv) is False

    def test_eligible_when_ca_override_true(self):
        inv = FakeInvoice(is_itc_eligible_draft=True, ca_override_itc_eligible=True)
        assert is_itc_eligible(inv) is True

    def test_rejected_when_draft_false(self):
        inv = FakeInvoice(is_itc_eligible_draft=False)
        assert is_itc_rejected(inv) is True

    def test_rejected_when_ca_override_false(self):
        inv = FakeInvoice(is_itc_eligible_draft=True, ca_override_itc_eligible=False)
        assert is_itc_rejected(inv) is True

    def test_not_rejected_when_eligible(self):
        inv = FakeInvoice(is_itc_eligible_draft=True, ca_override_itc_eligible=None)
        assert is_itc_rejected(inv) is False


# ── Aggregate ITC Computation ─────────────────────────────────────────

class TestAggregateITC:
    def test_confirmed_itc_approved_eligible(self):
        """Confirmed = ca_approved + eligible."""
        invoices = [
            FakeInvoice(
                status="ca_approved",
                cgst_amount=Decimal("900"),
                sgst_amount=Decimal("900"),
                igst_amount=Decimal("0"),
                is_itc_eligible_draft=True,
            ),
        ]
        result = compute_aggregate_itc(invoices)
        assert result.cgst_confirmed == Decimal("900.00")
        assert result.sgst_confirmed == Decimal("900.00")
        assert result.total_confirmed == Decimal("1800.00")

    def test_confirmed_itc_overridden_eligible(self):
        """ca_overridden also counts as confirmed."""
        invoices = [
            FakeInvoice(
                status="ca_overridden",
                cgst_amount=Decimal("500"),
                sgst_amount=Decimal("500"),
                igst_amount=Decimal("200"),
                is_itc_eligible_draft=True,
            ),
        ]
        result = compute_aggregate_itc(invoices)
        assert result.total_confirmed == Decimal("1200.00")

    def test_confirmed_excludes_ca_override_false(self):
        """If CA explicitly overrode to False, not confirmed."""
        invoices = [
            FakeInvoice(
                status="ca_approved",
                cgst_amount=Decimal("500"),
                sgst_amount=Decimal("500"),
                igst_amount=Decimal("0"),
                is_itc_eligible_draft=True,
                ca_override_itc_eligible=False,
            ),
        ]
        result = compute_aggregate_itc(invoices)
        assert result.total_confirmed == Decimal("0.00")
        assert result.total_rejected == Decimal("1000.00")

    def test_pending_itc(self):
        """Pending = processing/pending_ca_review + draft eligible."""
        invoices = [
            FakeInvoice(
                status="pending_ca_review",
                cgst_amount=Decimal("300"),
                sgst_amount=Decimal("300"),
                igst_amount=Decimal("0"),
                is_itc_eligible_draft=True,
            ),
            FakeInvoice(
                status="processing",
                cgst_amount=Decimal("200"),
                sgst_amount=Decimal("200"),
                igst_amount=Decimal("0"),
                is_itc_eligible_draft=True,
            ),
        ]
        result = compute_aggregate_itc(invoices)
        assert result.total_pending == Decimal("1000.00")
        assert result.total_confirmed == Decimal("0.00")

    def test_rejected_itc(self):
        """Rejected = reviewed + not eligible."""
        invoices = [
            FakeInvoice(
                status="ca_rejected",
                cgst_amount=Decimal("100"),
                sgst_amount=Decimal("100"),
                igst_amount=Decimal("0"),
                is_itc_eligible_draft=False,
            ),
        ]
        result = compute_aggregate_itc(invoices)
        assert result.total_rejected == Decimal("200.00")
        assert result.total_confirmed == Decimal("0.00")

    def test_rcm_liability_uses_taxable_value(self):
        """RCM liability = sum of taxable_value, NOT tax amounts."""
        invoices = [
            FakeInvoice(
                status="ca_approved",
                cgst_amount=Decimal("900"),
                sgst_amount=Decimal("900"),
                igst_amount=Decimal("0"),
                taxable_amount=Decimal("10000"),
                is_itc_eligible_draft=True,
                is_rcm=True,
            ),
        ]
        result = compute_aggregate_itc(invoices)
        assert result.rcm_liability == Decimal("10000.00")
        # RCM liability is taxable, not tax
        assert result.rcm_liability != Decimal("1800.00")

    def test_rcm_liability_non_rcm_ignored(self):
        """Non-RCM invoices should not add to RCM liability."""
        invoices = [
            FakeInvoice(
                status="ca_approved",
                taxable_amount=Decimal("50000"),
                is_rcm=False,
            ),
        ]
        result = compute_aggregate_itc(invoices)
        assert result.rcm_liability == Decimal("0.00")

    def test_mixed_invoices(self):
        """Mix of confirmed, pending, rejected, RCM."""
        invoices = [
            # Confirmed eligible
            FakeInvoice(
                status="ca_approved",
                cgst_amount=Decimal("450"),
                sgst_amount=Decimal("450"),
                igst_amount=Decimal("0"),
                is_itc_eligible_draft=True,
            ),
            # Pending
            FakeInvoice(
                status="pending_ca_review",
                cgst_amount=Decimal("200"),
                sgst_amount=Decimal("200"),
                igst_amount=Decimal("0"),
                is_itc_eligible_draft=True,
            ),
            # Rejected
            FakeInvoice(
                status="ca_rejected",
                cgst_amount=Decimal("100"),
                sgst_amount=Decimal("50"),
                igst_amount=Decimal("0"),
                is_itc_eligible_draft=False,
            ),
            # RCM
            FakeInvoice(
                status="ca_approved",
                cgst_amount=Decimal("180"),
                sgst_amount=Decimal("180"),
                igst_amount=Decimal("0"),
                taxable_amount=Decimal("2000"),
                is_itc_eligible_draft=True,
                is_rcm=True,
            ),
        ]
        result = compute_aggregate_itc(invoices)
        # Confirmed: 450+450+180+180 = 1260
        assert result.total_confirmed == Decimal("1260.00")
        assert result.cgst_confirmed == Decimal("630.00")
        assert result.sgst_confirmed == Decimal("630.00")
        # Pending: 200+200 = 400
        assert result.total_pending == Decimal("400.00")
        # Rejected: 100+50 = 150
        assert result.total_rejected == Decimal("150.00")
        # RCM: 2000
        assert result.rcm_liability == Decimal("2000.00")
        assert result.invoice_count == 4

    def test_empty_invoice_list(self):
        result = compute_aggregate_itc([])
        assert result.total_confirmed == Decimal("0.00")
        assert result.total_pending == Decimal("0.00")
        assert result.total_rejected == Decimal("0.00")
        assert result.rcm_liability == Decimal("0.00")
        assert result.invoice_count == 0

    def test_decimal_precision_in_aggregate(self):
        """All aggregate values use ROUND_HALF_UP."""
        invoices = [
            FakeInvoice(
                status="ca_approved",
                cgst_amount=Decimal("100.555"),
                sgst_amount=Decimal("200.445"),
                igst_amount=Decimal("0.005"),
                is_itc_eligible_draft=True,
            ),
        ]
        result = compute_aggregate_itc(invoices)
        assert result.cgst_confirmed == Decimal("100.56")
        assert result.sgst_confirmed == Decimal("200.45")
        assert result.igst_confirmed == Decimal("0.01")
        # total_confirmed = 100.555+200.445+0.005 = 301.005 -> 301.01
        assert result.total_confirmed == Decimal("301.01")

    def test_igst_confirmed_interstate(self):
        """IGST invoices should contribute to igst_confirmed."""
        invoices = [
            FakeInvoice(
                status="ca_approved",
                cgst_amount=Decimal("0"),
                sgst_amount=Decimal("0"),
                igst_amount=Decimal("1800"),
                is_itc_eligible_draft=True,
            ),
        ]
        result = compute_aggregate_itc(invoices)
        assert result.cgst_confirmed == Decimal("0.00")
        assert result.sgst_confirmed == Decimal("0.00")
        assert result.igst_confirmed == Decimal("1800.00")
        assert result.total_confirmed == Decimal("1800.00")
