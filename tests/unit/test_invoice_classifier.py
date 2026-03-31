"""
VyapaarBandhu -- Unit Tests for Invoice Classifier
Covers B2B/B2C, interstate/intrastate, and all 5 RCM categories.
RULE 1: No AI/LLM in classification. Deterministic rules only.
"""

import pytest
from decimal import Decimal

from app.services.classification.invoice_classifier import (
    classify_invoice,
    ClassificationResult,
)

ZERO = Decimal("0.00")


# ── B2B vs B2C Classification ─────────────────────────────────────────

class TestB2BClassification:

    def test_both_gstins_valid_is_b2b(self):
        """Both supplier and recipient GSTINs valid -> B2B."""
        result = classify_invoice(
            gstin_supplier="27AAPFU0939F1ZV",
            gstin_recipient="29AABCU9603R1ZM",
            hsn_sac_codes=None,
            description="Office supplies",
            igst_amount=ZERO,
            cgst_amount=Decimal("900"),
            sgst_amount=Decimal("900"),
            place_of_supply="27",
        )
        assert result.is_b2b is True
        assert result.transaction_type == "B2B"

    def test_missing_recipient_gstin_is_b2c(self):
        """Recipient GSTIN missing -> B2C."""
        result = classify_invoice(
            gstin_supplier="27AAPFU0939F1ZV",
            gstin_recipient=None,
            hsn_sac_codes=None,
            description="Retail purchase",
            igst_amount=ZERO,
            cgst_amount=Decimal("90"),
            sgst_amount=Decimal("90"),
            place_of_supply="27",
        )
        assert result.is_b2c is True
        assert result.transaction_type == "B2C"

    def test_invalid_recipient_gstin_is_b2c(self):
        """Invalid recipient GSTIN format -> B2C."""
        result = classify_invoice(
            gstin_supplier="27AAPFU0939F1ZV",
            gstin_recipient="INVALID",
            hsn_sac_codes=None,
            description="Purchase",
            igst_amount=ZERO,
            cgst_amount=ZERO,
            sgst_amount=ZERO,
            place_of_supply=None,
        )
        assert result.is_b2c is True

    def test_missing_supplier_flags_review(self):
        """Missing supplier GSTIN should flag for CA review."""
        result = classify_invoice(
            gstin_supplier=None,
            gstin_recipient="29AABCU9603R1ZM",
            hsn_sac_codes=None,
            description="Service",
            igst_amount=ZERO,
            cgst_amount=ZERO,
            sgst_amount=ZERO,
            place_of_supply=None,
        )
        assert result.requires_ca_review is True
        assert any("Supplier GSTIN" in r for r in result.review_reasons)


# ── Interstate vs Intrastate ──────────────────────────────────────────

class TestSupplyType:

    def test_different_states_is_interstate(self):
        """Supplier in state 27, recipient in state 29 -> interstate."""
        result = classify_invoice(
            gstin_supplier="27AAPFU0939F1ZV",
            gstin_recipient="29AABCU9603R1ZM",
            hsn_sac_codes=None,
            description="Purchase",
            igst_amount=Decimal("1800"),
            cgst_amount=ZERO,
            sgst_amount=ZERO,
            place_of_supply="27",
        )
        assert result.is_interstate is True
        assert result.supply_type == "interstate"
        assert result.igst_applicable is True

    def test_same_state_is_intrastate(self):
        """Both in state 27 -> intrastate."""
        result = classify_invoice(
            gstin_supplier="27AAPFU0939F1ZV",
            gstin_recipient="27BBDCS1234A1Z5",
            hsn_sac_codes=None,
            description="Purchase",
            igst_amount=ZERO,
            cgst_amount=Decimal("900"),
            sgst_amount=Decimal("900"),
            place_of_supply="27",
        )
        assert result.is_intrastate is True
        assert result.supply_type == "intrastate"

    def test_igst_present_implies_interstate(self):
        """IGST > 0 with CGST=SGST=0 -> interstate (from amounts)."""
        result = classify_invoice(
            gstin_supplier=None,
            gstin_recipient=None,
            hsn_sac_codes=None,
            description="Something",
            igst_amount=Decimal("500"),
            cgst_amount=ZERO,
            sgst_amount=ZERO,
            place_of_supply=None,
        )
        assert result.is_interstate is True
        assert result.igst_applicable is True

    def test_cgst_sgst_present_implies_intrastate(self):
        """CGST+SGST > 0 with IGST=0 -> intrastate (from amounts)."""
        result = classify_invoice(
            gstin_supplier=None,
            gstin_recipient=None,
            hsn_sac_codes=None,
            description="Something",
            igst_amount=ZERO,
            cgst_amount=Decimal("450"),
            sgst_amount=Decimal("450"),
            place_of_supply=None,
        )
        assert result.is_intrastate is True

    def test_no_data_flags_unknown(self):
        """Insufficient data -> unknown, flags for CA review."""
        result = classify_invoice(
            gstin_supplier=None,
            gstin_recipient=None,
            hsn_sac_codes=None,
            description=None,
            igst_amount=ZERO,
            cgst_amount=ZERO,
            sgst_amount=ZERO,
            place_of_supply=None,
        )
        assert result.supply_type == "unknown"
        assert result.requires_ca_review is True


# ── RCM Detection (RULE 6: must cover all 5 categories) ──────────────

class TestRCMDetection:

    def test_rcm_gta_sac_code(self):
        """GTA SAC code 9965 -> RCM applicable."""
        result = classify_invoice(
            gstin_supplier="27AAPFU0939F1ZV",
            gstin_recipient="29AABCU9603R1ZM",
            hsn_sac_codes=["9965"],
            description="Freight charges",
            igst_amount=Decimal("500"),
            cgst_amount=ZERO,
            sgst_amount=ZERO,
            place_of_supply="27",
        )
        assert result.rcm_applicable is True
        assert result.rcm_category == "gta"

    def test_rcm_gta_keyword(self):
        """GTA detected via keyword 'goods transport'."""
        result = classify_invoice(
            gstin_supplier="27AAPFU0939F1ZV",
            gstin_recipient="29AABCU9603R1ZM",
            hsn_sac_codes=None,
            description="Goods transport agency freight bill",
            igst_amount=Decimal("500"),
            cgst_amount=ZERO,
            sgst_amount=ZERO,
            place_of_supply="27",
        )
        assert result.rcm_applicable is True
        assert result.rcm_category == "gta"

    def test_rcm_legal_services_sac(self):
        """Legal services SAC 9982 -> RCM applicable."""
        result = classify_invoice(
            gstin_supplier="27AAPFU0939F1ZV",
            gstin_recipient="29AABCU9603R1ZM",
            hsn_sac_codes=["9982"],
            description="Legal consultation",
            igst_amount=ZERO,
            cgst_amount=Decimal("900"),
            sgst_amount=Decimal("900"),
            place_of_supply="27",
        )
        assert result.rcm_applicable is True
        assert result.rcm_category == "legal"

    def test_rcm_legal_keyword(self):
        """Legal services detected via keyword."""
        result = classify_invoice(
            gstin_supplier="27AAPFU0939F1ZV",
            gstin_recipient="29AABCU9603R1ZM",
            hsn_sac_codes=None,
            description="Legal services from advocate",
            igst_amount=ZERO,
            cgst_amount=Decimal("900"),
            sgst_amount=Decimal("900"),
            place_of_supply="27",
        )
        assert result.rcm_applicable is True
        assert result.rcm_category == "legal"

    def test_rcm_security_services_sac(self):
        """Security services SAC 9985 -> RCM applicable."""
        result = classify_invoice(
            gstin_supplier="27AAPFU0939F1ZV",
            gstin_recipient="29AABCU9603R1ZM",
            hsn_sac_codes=["9985"],
            description="Security guard services",
            igst_amount=ZERO,
            cgst_amount=Decimal("450"),
            sgst_amount=Decimal("450"),
            place_of_supply="27",
        )
        assert result.rcm_applicable is True
        assert result.rcm_category == "security"

    def test_rcm_import_of_services(self):
        """Place of supply outside India -> import RCM."""
        result = classify_invoice(
            gstin_supplier="27AAPFU0939F1ZV",
            gstin_recipient="29AABCU9603R1ZM",
            hsn_sac_codes=None,
            description="Import consulting services",
            igst_amount=Decimal("1800"),
            cgst_amount=ZERO,
            sgst_amount=ZERO,
            place_of_supply="99",  # Outside India
        )
        assert result.rcm_applicable is True
        assert result.rcm_category == "import"

    def test_rcm_unregistered_vendor(self):
        """No supplier GSTIN -> unregistered vendor RCM."""
        result = classify_invoice(
            gstin_supplier=None,
            gstin_recipient="29AABCU9603R1ZM",
            hsn_sac_codes=None,
            description="Cleaning services",
            igst_amount=ZERO,
            cgst_amount=Decimal("90"),
            sgst_amount=Decimal("90"),
            place_of_supply=None,
        )
        assert result.rcm_applicable is True
        assert result.rcm_category == "unregistered"
        assert result.requires_ca_review is True

    def test_no_rcm_for_normal_b2b(self):
        """Normal B2B purchase should NOT trigger RCM."""
        result = classify_invoice(
            gstin_supplier="27AAPFU0939F1ZV",
            gstin_recipient="29AABCU9603R1ZM",
            hsn_sac_codes=["8471"],  # Computers - not RCM
            description="Computer equipment purchase",
            igst_amount=Decimal("1800"),
            cgst_amount=ZERO,
            sgst_amount=ZERO,
            place_of_supply="27",
        )
        assert result.rcm_applicable is False


# ── Classification Result Serialization ───────────────────────────────

class TestClassificationSerialization:

    def test_to_json_complete(self):
        result = classify_invoice(
            gstin_supplier="27AAPFU0939F1ZV",
            gstin_recipient="29AABCU9603R1ZM",
            hsn_sac_codes=None,
            description="Office supplies",
            igst_amount=Decimal("1800"),
            cgst_amount=ZERO,
            sgst_amount=ZERO,
            place_of_supply="27",
        )
        json_data = result.to_json()
        assert "transaction_type" in json_data
        assert "supply_type" in json_data
        assert "rcm_applicable" in json_data
        assert "is_b2b" in json_data
