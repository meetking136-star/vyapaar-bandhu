"""
VyapaarBandhu — GSTR-3B Builder Unit Tests
Tests for GSTR-3B JSON generation per GSTN portal spec.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.exports.gstr3b_builder import (
    GSTR3BInput,
    build_gstr3b_json,
    _fmt,
    _make_itc_row,
    ZERO,
)


class TestFormatAmount:
    def test_zero(self):
        assert _fmt(ZERO) == "0.00"

    def test_none(self):
        assert _fmt(None) == "0.00"

    def test_normal_value(self):
        assert _fmt(Decimal("1234.56")) == "1234.56"

    def test_round_half_up(self):
        assert _fmt(Decimal("100.555")) == "100.56"

    def test_string_input(self):
        assert _fmt("999.99") == "999.99"

    def test_returns_string_not_float(self):
        result = _fmt(Decimal("42.00"))
        assert isinstance(result, str)
        assert result == "42.00"

    def test_zero_is_not_zero_or_zero_dot_zero(self):
        """GSTN requires '0.00' not '0' or '0.0'."""
        result = _fmt(Decimal("0"))
        assert result == "0.00"
        assert result != "0"
        assert result != "0.0"

    def test_large_value(self):
        assert _fmt(Decimal("99999999.99")) == "99999999.99"


class TestMakeITCRow:
    def test_zero_row(self):
        row = _make_itc_row("IMPG")
        assert row == {
            "ty": "IMPG",
            "samt": "0.00",
            "camt": "0.00",
            "iamt": "0.00",
            "csamt": "0.00",
        }

    def test_with_values(self):
        row = _make_itc_row(
            "OTH",
            samt=Decimal("100.50"),
            camt=Decimal("200.75"),
            iamt=Decimal("300.00"),
        )
        assert row["ty"] == "OTH"
        assert row["samt"] == "100.50"
        assert row["camt"] == "200.75"
        assert row["iamt"] == "300.00"
        assert row["csamt"] == "0.00"


class TestBuildGSTR3BJSON:
    def _default_input(self, **overrides) -> GSTR3BInput:
        defaults = dict(
            gstin="27AAPFU0939F1ZV",
            period="03-2026",
            cgst_confirmed=Decimal("1000.00"),
            sgst_confirmed=Decimal("1000.00"),
            igst_confirmed=Decimal("500.00"),
            cgst_rejected=Decimal("50.00"),
            sgst_rejected=Decimal("50.00"),
            igst_rejected=Decimal("25.00"),
            rcm_taxable=Decimal("5000.00"),
            rcm_cgst=Decimal("450.00"),
            rcm_sgst=Decimal("450.00"),
            rcm_igst=Decimal("0.00"),
        )
        defaults.update(overrides)
        return GSTR3BInput(**defaults)

    def test_gstin_in_output(self):
        data = self._default_input()
        result = build_gstr3b_json(data)
        assert result["gstin"] == "27AAPFU0939F1ZV"

    def test_ret_period_format_mmyyyy(self):
        """ret_period must be MMYYYY (032026 not 03-2026)."""
        data = self._default_input(period="03-2026")
        result = build_gstr3b_json(data)
        assert result["ret_period"] == "032026"

    def test_ret_period_different_month(self):
        data = self._default_input(period="12-2025")
        result = build_gstr3b_json(data)
        assert result["ret_period"] == "122025"

    def test_all_amounts_are_strings(self):
        """CRITICAL: Every amount in GSTR-3B must be a string, never float."""
        data = self._default_input()
        result = build_gstr3b_json(data)

        def check_strings(obj, path=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ("gstin", "ret_period", "ty"):
                        continue
                    check_strings(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    check_strings(item, f"{path}[{i}]")
            elif isinstance(obj, (int, float)):
                pytest.fail(f"Found numeric value at {path}: {obj} (type={type(obj).__name__})")

        check_strings(result)

    def test_itc_avl_oth_has_confirmed_values(self):
        """itc_avl OTH should have confirmed ITC from itc_calculator."""
        data = self._default_input()
        result = build_gstr3b_json(data)

        oth_row = next(r for r in result["itc_elg"]["itc_avl"] if r["ty"] == "OTH")
        assert oth_row["camt"] == "1000.00"  # cgst_confirmed
        assert oth_row["samt"] == "1000.00"  # sgst_confirmed
        assert oth_row["iamt"] == "500.00"   # igst_confirmed
        assert oth_row["csamt"] == "0.00"

    def test_itc_rev_oth_has_rejected_values(self):
        """itc_rev OTH should have rejected ITC."""
        data = self._default_input()
        result = build_gstr3b_json(data)

        oth_row = next(r for r in result["itc_elg"]["itc_rev"] if r["ty"] == "OTH")
        assert oth_row["camt"] == "50.00"   # cgst_rejected
        assert oth_row["samt"] == "50.00"   # sgst_rejected
        assert oth_row["iamt"] == "25.00"   # igst_rejected

    def test_itc_net_equals_avl_minus_rev(self):
        """itc_net = itc_avl totals minus itc_rev totals."""
        data = self._default_input()
        result = build_gstr3b_json(data)

        net = result["itc_elg"]["itc_net"]
        # net camt = 1000 - 50 = 950
        assert net["camt"] == "950.00"
        # net samt = 1000 - 50 = 950
        assert net["samt"] == "950.00"
        # net iamt = 500 - 25 = 475
        assert net["iamt"] == "475.00"
        assert net["csamt"] == "0.00"

    def test_rcm_in_isup_rev(self):
        """RCM liability maps to sup_details.isup_rev."""
        data = self._default_input()
        result = build_gstr3b_json(data)

        isup_rev = result["sup_details"]["isup_rev"]
        assert isup_rev["txval"] == "5000.00"  # rcm_taxable
        assert isup_rev["camt"] == "450.00"    # rcm_cgst
        assert isup_rev["samt"] == "450.00"    # rcm_sgst
        assert isup_rev["iamt"] == "0.00"      # rcm_igst

    def test_zero_amounts_are_zero_dot_zero_zero(self):
        """All zero amounts must be '0.00' not '0' or '0.0'."""
        data = self._default_input(
            cgst_confirmed=ZERO,
            sgst_confirmed=ZERO,
            igst_confirmed=ZERO,
            cgst_rejected=ZERO,
            sgst_rejected=ZERO,
            igst_rejected=ZERO,
            rcm_taxable=ZERO,
            rcm_cgst=ZERO,
            rcm_sgst=ZERO,
            rcm_igst=ZERO,
        )
        result = build_gstr3b_json(data)

        # Check a few strategic spots
        oth = next(r for r in result["itc_elg"]["itc_avl"] if r["ty"] == "OTH")
        assert oth["camt"] == "0.00"
        assert oth["samt"] == "0.00"
        assert oth["iamt"] == "0.00"

        assert result["sup_details"]["isup_rev"]["txval"] == "0.00"
        assert result["itc_elg"]["itc_net"]["camt"] == "0.00"

    def test_inward_sup_details(self):
        """inward_sup should have GST and NONGST entries."""
        data = self._default_input()
        result = build_gstr3b_json(data)

        isup = result["inward_sup"]["isup_details"]
        assert len(isup) == 2
        gst_entry = next(e for e in isup if e["ty"] == "GST")
        assert gst_entry["inter"] == "500.00"   # igst_confirmed
        assert gst_entry["intra"] == "2000.00"  # cgst + sgst confirmed

        nongst_entry = next(e for e in isup if e["ty"] == "NONGST")
        assert nongst_entry["inter"] == "0.00"
        assert nongst_entry["intra"] == "0.00"

    def test_itc_avl_has_all_five_types(self):
        """itc_avl must have IMPG, IMPS, ISRC, ISD, OTH."""
        data = self._default_input()
        result = build_gstr3b_json(data)

        types = [r["ty"] for r in result["itc_elg"]["itc_avl"]]
        assert types == ["IMPG", "IMPS", "ISRC", "ISD", "OTH"]

    def test_itc_rev_has_two_types(self):
        """itc_rev must have RUL and OTH."""
        data = self._default_input()
        result = build_gstr3b_json(data)

        types = [r["ty"] for r in result["itc_elg"]["itc_rev"]]
        assert types == ["RUL", "OTH"]

    def test_intr_ltfee_present(self):
        data = self._default_input()
        result = build_gstr3b_json(data)

        assert "intr_ltfee" in result
        assert result["intr_ltfee"]["intr_details"]["camt"] == "0.00"

    def test_empty_gstin(self):
        """Should handle empty GSTIN gracefully."""
        data = self._default_input(gstin="")
        result = build_gstr3b_json(data)
        assert result["gstin"] == ""

    def test_itc_net_clamped_to_zero_when_negative(self):
        """If reversed > available, itc_net must be 0.00 not negative."""
        data = self._default_input(
            cgst_confirmed=Decimal("100.00"),
            sgst_confirmed=Decimal("100.00"),
            igst_confirmed=Decimal("50.00"),
            cgst_rejected=Decimal("200.00"),  # More than confirmed
            sgst_rejected=Decimal("300.00"),
            igst_rejected=Decimal("100.00"),
        )
        result = build_gstr3b_json(data)
        net = result["itc_elg"]["itc_net"]
        assert net["camt"] == "0.00"  # Would be -100 without clamp
        assert net["samt"] == "0.00"  # Would be -200 without clamp
        assert net["iamt"] == "0.00"  # Would be -50 without clamp

    def test_no_float_in_entire_output(self):
        """Deep check: no float type anywhere in the output dict."""
        data = self._default_input()
        result = build_gstr3b_json(data)

        def find_floats(obj, path="root"):
            if isinstance(obj, float):
                return [f"{path} = {obj}"]
            if isinstance(obj, dict):
                found = []
                for k, v in obj.items():
                    found.extend(find_floats(v, f"{path}.{k}"))
                return found
            if isinstance(obj, list):
                found = []
                for i, v in enumerate(obj):
                    found.extend(find_floats(v, f"{path}[{i}]"))
                return found
            return []

        floats = find_floats(result)
        assert floats == [], f"Found float values: {floats}"
