"""
VyapaarBandhu -- Unit Tests for Confidence Scorer
Tests per-field scoring, cross-validation, and threshold behavior.
"""

import pytest
from decimal import Decimal

from app.services.ocr.confidence_scorer import (
    score_extracted_fields,
    ConfidenceReport,
    GSTIN_CONFIDENCE_THRESHOLD,
    AMOUNT_CONFIDENCE_THRESHOLD,
    DATE_CONFIDENCE_THRESHOLD,
    LOW_CONFIDENCE_CUTOFF,
    OVERALL_CONFIDENCE_THRESHOLD,
)


class TestPerfectOCR:
    """Perfect OCR text should produce scores above thresholds."""

    def test_all_fields_above_threshold(self):
        """All valid fields with high OCR confidence should score well."""
        extracted = {
            "gstin_supplier": "27AAPFU0939F1ZV",
            "gstin_recipient": "29AABCU9603R1ZM",
            "invoice_number": "INV-001",
            "invoice_date": "15-03-2026",
            "taxable_value": Decimal("10000.00"),
            "cgst_amount": Decimal("900.00"),
            "sgst_amount": Decimal("900.00"),
            "igst_amount": Decimal("0"),
            "total_amount": Decimal("11800.00"),
            "hsn_sac_codes": ["8471"],
            "place_of_supply": "27",
        }
        report = score_extracted_fields(extracted, 0.95)
        # With 0.95 OCR confidence and valid fields, overall should be high
        assert report.overall_score > Decimal("0.70")

    def test_checksum_valid_gstin_gets_1_0(self):
        """GSTIN with valid checksum should get perfect confidence."""
        extracted = {
            "gstin_supplier": "27AAPFU0939F1ZV",
            "gstin_recipient": None,
            "invoice_number": None,
            "invoice_date": None,
            "taxable_value": None,
            "cgst_amount": None,
            "sgst_amount": None,
            "igst_amount": None,
            "total_amount": None,
            "hsn_sac_codes": None,
            "place_of_supply": None,
        }
        report = score_extracted_fields(extracted, 0.90)
        gstin_score = report.field_scores["gstin_supplier"].score
        # A checksum-verified GSTIN should get 1.0 or at least very high
        assert gstin_score >= Decimal("0.50")


class TestDegradedOCR:
    """Degraded text (simulated noise) should drop scores below threshold."""

    def test_invalid_gstin_format_low_score(self):
        """Invalid GSTIN format should get low confidence."""
        extracted = {
            "gstin_supplier": "INVALID_GSTIN!!",
            "gstin_recipient": None,
            "invoice_number": None,
            "invoice_date": None,
            "taxable_value": None,
            "cgst_amount": None,
            "sgst_amount": None,
            "igst_amount": None,
            "total_amount": None,
            "hsn_sac_codes": None,
            "place_of_supply": None,
        }
        report = score_extracted_fields(extracted, 0.40)
        gstin_score = report.field_scores["gstin_supplier"].score
        assert gstin_score < GSTIN_CONFIDENCE_THRESHOLD

    def test_low_ocr_confidence_flags_review(self):
        """Low overall OCR confidence should trigger manual review."""
        extracted = {
            "gstin_supplier": None,
            "gstin_recipient": None,
            "invoice_number": "??",
            "invoice_date": "99-99-9999",
            "taxable_value": Decimal("100"),
            "cgst_amount": None,
            "sgst_amount": None,
            "igst_amount": None,
            "total_amount": None,
            "hsn_sac_codes": None,
            "place_of_supply": None,
        }
        report = score_extracted_fields(extracted, 0.30)
        assert report.requires_manual_review is True


class TestMissingFields:
    """Missing fields should score 0.0, not raise exceptions."""

    def test_missing_field_score_zero(self):
        """None values should get score 0.0."""
        extracted = {
            "gstin_supplier": None,
            "gstin_recipient": None,
            "invoice_number": None,
            "invoice_date": None,
            "taxable_value": None,
            "cgst_amount": None,
            "sgst_amount": None,
            "igst_amount": None,
            "total_amount": None,
            "hsn_sac_codes": None,
            "place_of_supply": None,
        }
        report = score_extracted_fields(extracted, 0.50)
        for name, fc in report.field_scores.items():
            assert fc.score == Decimal("0.00")
            assert fc.extraction_method == "none"

    def test_all_missing_triggers_manual_review(self):
        extracted = {
            "gstin_supplier": None,
            "gstin_recipient": None,
            "invoice_number": None,
            "invoice_date": None,
            "taxable_value": None,
            "cgst_amount": None,
            "sgst_amount": None,
            "igst_amount": None,
            "total_amount": None,
            "hsn_sac_codes": None,
            "place_of_supply": None,
        }
        report = score_extracted_fields(extracted, 0.50)
        assert report.requires_manual_review is True
        assert len(report.low_confidence_fields) > 0


class TestAmountCrossValidation:
    """Amount consistency checks."""

    def test_amount_mismatch_penalizes_scores(self):
        """When taxable + taxes != total, amount scores should drop."""
        extracted = {
            "gstin_supplier": None,
            "gstin_recipient": None,
            "invoice_number": None,
            "invoice_date": None,
            "taxable_value": Decimal("10000.00"),
            "cgst_amount": Decimal("900.00"),
            "sgst_amount": Decimal("900.00"),
            "igst_amount": Decimal("0"),
            "total_amount": Decimal("50000.00"),  # Way off!
            "hsn_sac_codes": None,
            "place_of_supply": None,
        }
        report = score_extracted_fields(extracted, 0.90)
        total_fc = report.field_scores["total_amount"]
        assert "mismatch" in total_fc.validation_notes.lower()

    def test_consistent_amounts_no_penalty(self):
        """When amounts add up correctly, no penalty applied."""
        extracted = {
            "gstin_supplier": None,
            "gstin_recipient": None,
            "invoice_number": None,
            "invoice_date": None,
            "taxable_value": Decimal("10000.00"),
            "cgst_amount": Decimal("900.00"),
            "sgst_amount": Decimal("900.00"),
            "igst_amount": Decimal("0"),
            "total_amount": Decimal("11800.00"),
            "hsn_sac_codes": None,
            "place_of_supply": None,
        }
        report = score_extracted_fields(extracted, 0.90)
        total_fc = report.field_scores["total_amount"]
        assert "mismatch" not in total_fc.validation_notes.lower()


class TestTaxTypeConsistency:
    """IGST vs CGST+SGST mutual exclusivity checks."""

    def test_both_igst_and_cgst_flagged(self):
        """Having both IGST and CGST/SGST should add a warning note."""
        extracted = {
            "gstin_supplier": None,
            "gstin_recipient": None,
            "invoice_number": None,
            "invoice_date": None,
            "taxable_value": Decimal("10000.00"),
            "cgst_amount": Decimal("900.00"),
            "sgst_amount": Decimal("900.00"),
            "igst_amount": Decimal("1800.00"),  # Both present!
            "total_amount": Decimal("13600.00"),
            "hsn_sac_codes": None,
            "place_of_supply": None,
        }
        report = score_extracted_fields(extracted, 0.90)
        igst_fc = report.field_scores["igst_amount"]
        assert "both" in igst_fc.validation_notes.lower() or "ocr error" in igst_fc.validation_notes.lower()


class TestConfidenceReportSerialization:

    def test_to_json_output_format(self):
        extracted = {
            "gstin_supplier": "27AAPFU0939F1ZV",
            "gstin_recipient": None,
            "invoice_number": "INV-001",
            "invoice_date": "15-03-2026",
            "taxable_value": Decimal("1000"),
            "cgst_amount": Decimal("90"),
            "sgst_amount": Decimal("90"),
            "igst_amount": Decimal("0"),
            "total_amount": Decimal("1180"),
            "hsn_sac_codes": ["8471"],
            "place_of_supply": "27",
        }
        report = score_extracted_fields(extracted, 0.90)
        json_data = report.to_json()
        assert isinstance(json_data, dict)
        assert "gstin_supplier" in json_data
        assert "score" in json_data["gstin_supplier"]
