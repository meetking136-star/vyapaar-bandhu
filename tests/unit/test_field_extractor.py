"""
VyapaarBandhu -- Unit Tests for OCR Field Extractor
Covers GSTIN extraction, date parsing, amount extraction, cross-validation.
"""

import pytest
from decimal import Decimal

from app.services.ocr.field_extractor import (
    extract_fields_from_raw,
    ExtractedFields,
)


# ── GSTIN Extraction ──────────────────────────────────────────────────

class TestGSTINExtraction:
    """Valid GSTIN extraction from 5 different invoice layouts."""

    def test_gstin_standard_layout(self):
        """Standard invoice with GSTIN on its own line."""
        text = """TAX INVOICE
GSTIN: 27AAPFU0939F1ZV
M/s ABC Trading Co
"""
        fields = extract_fields_from_raw(text)
        assert fields.gstin_supplier == "27AAPFU0939F1ZV"

    def test_gstin_inline_with_label(self):
        """GSTIN appearing inline after a label."""
        text = """Invoice No: INV-001
Supplier GSTIN : 07AAACH7409R1Z7
Buyer GSTIN : 29AABCU9603R1ZM
Date: 15/03/2026
"""
        fields = extract_fields_from_raw(text)
        assert fields.gstin_supplier == "07AAACH7409R1Z7"
        assert fields.gstin_recipient == "29AABCU9603R1ZM"

    def test_gstin_no_label(self):
        """GSTIN appearing without explicit label."""
        text = """XYZ Enterprises
06AABCT1332L1ZN
123 Main Street
"""
        fields = extract_fields_from_raw(text)
        assert fields.gstin_supplier == "06AABCT1332L1ZN"

    def test_gstin_mixed_case(self):
        """GSTIN with mixed case (OCR sometimes lowercases)."""
        text = """Seller: 27aapfu0939f1zv
Total: 1000.00
"""
        fields = extract_fields_from_raw(text)
        assert fields.gstin_supplier == "27AAPFU0939F1ZV"

    def test_gstin_two_gstins_both_extracted(self):
        """Two distinct GSTINs should be extracted as supplier + recipient."""
        text = """Seller GSTIN: 27AAPFU0939F1ZV
Buyer GSTIN: 33AADCS0472N1Z5
Invoice No: INV-2024-001
"""
        fields = extract_fields_from_raw(text)
        assert fields.gstin_supplier == "27AAPFU0939F1ZV"
        assert fields.gstin_recipient == "33AADCS0472N1Z5"

    def test_place_of_supply_from_recipient_gstin(self):
        """Place of supply is derived from recipient GSTIN first 2 digits."""
        text = """Seller GSTIN: 27AAPFU0939F1ZV
Buyer GSTIN: 29AABCU9603R1ZM"""
        fields = extract_fields_from_raw(text)
        assert fields.place_of_supply == "29"

    def test_place_of_supply_b2c_fallback(self):
        """B2C invoice (no recipient GSTIN): place of supply from text."""
        text = """GSTIN: 27AAPFU0939F1ZV
Place of Supply: 33
Total: 1000.00"""
        fields = extract_fields_from_raw(text)
        assert fields.place_of_supply == "33"

    def test_place_of_supply_b2c_no_text(self):
        """B2C invoice with no place of supply in text returns None."""
        text = "GSTIN: 29AABCU9603R1ZM"
        fields = extract_fields_from_raw(text)
        assert fields.place_of_supply is None

    def test_no_gstin_returns_none(self):
        """No GSTIN in text returns None."""
        text = "Just a random text without any GSTIN"
        fields = extract_fields_from_raw(text)
        assert fields.gstin_supplier is None


# ── Date Parsing ──────────────────────────────────────────────────────

class TestDateParsing:
    """Date parsing for DD/MM/YYYY, DD-MM-YYYY, DD MMM YYYY formats."""

    def test_date_dd_mm_yyyy_slash(self):
        text = "Invoice Date: 15/03/2026\nTotal: 1000"
        fields = extract_fields_from_raw(text)
        assert fields.invoice_date == "15-03-2026"

    def test_date_dd_mm_yyyy_dash(self):
        text = "Date: 22-11-2025\nAmount: 500"
        fields = extract_fields_from_raw(text)
        assert fields.invoice_date == "22-11-2025"

    def test_date_dd_mmm_yyyy(self):
        text = "Invoice Date: 5 Jan 2026\nTotal: 200"
        fields = extract_fields_from_raw(text)
        assert fields.invoice_date == "05-01-2026"

    def test_date_yyyy_mm_dd(self):
        text = "Date: 2026-03-15\nGST"
        fields = extract_fields_from_raw(text)
        assert fields.invoice_date == "15-03-2026"

    def test_date_dd_mm_yyyy_dot(self):
        text = "Bill Date: 01.12.2025"
        fields = extract_fields_from_raw(text)
        assert fields.invoice_date == "01-12-2025"

    def test_no_date_returns_none(self):
        text = "No date information here"
        fields = extract_fields_from_raw(text)
        assert fields.invoice_date is None


# ── Amount Extraction ─────────────────────────────────────────────────

class TestAmountExtraction:
    """Amounts are extracted as Decimal (RULE 3: no float)."""

    def test_taxable_amount_extracted(self):
        text = "Taxable Value: 10,000.50\nTotal: 11,800.59"
        fields = extract_fields_from_raw(text)
        assert fields.taxable_value == Decimal("10000.50")
        assert isinstance(fields.taxable_value, Decimal)

    def test_cgst_sgst_extracted(self):
        text = """Sub Total: 5000.00
CGST @ 9%: 450.00
SGST @ 9%: 450.00
Total: 5900.00"""
        fields = extract_fields_from_raw(text)
        assert fields.cgst_amount == Decimal("450.00")
        assert fields.sgst_amount == Decimal("450.00")
        assert isinstance(fields.cgst_amount, Decimal)
        assert isinstance(fields.sgst_amount, Decimal)

    def test_igst_extracted(self):
        text = """Taxable: 10000.00
IGST @ 18%: 1800.00
Total: 11800.00"""
        fields = extract_fields_from_raw(text)
        assert fields.igst_amount == Decimal("1800.00")
        assert isinstance(fields.igst_amount, Decimal)

    def test_total_amount_extracted(self):
        text = "Grand Total: 25,000.00\nPay within 30 days"
        fields = extract_fields_from_raw(text)
        assert fields.total_amount == Decimal("25000.00")

    def test_amounts_with_commas(self):
        text = "Total Amount: 1,25,000.75"
        fields = extract_fields_from_raw(text)
        assert fields.total_amount == Decimal("125000.75")

    def test_no_amounts_returns_none(self):
        text = "This invoice has no amounts listed"
        fields = extract_fields_from_raw(text)
        assert fields.taxable_value is None
        assert fields.total_amount is None


# ── Invoice Number ────────────────────────────────────────────────────

class TestInvoiceNumber:

    def test_invoice_number_standard(self):
        text = "Invoice No: INV-2024-001\nDate: 15/03/2026"
        fields = extract_fields_from_raw(text)
        assert fields.invoice_number == "INV-2024-001"

    def test_invoice_number_hash_prefix(self):
        text = "Bill # AB/123/456\nTotal: 100"
        fields = extract_fields_from_raw(text)
        assert fields.invoice_number is not None

    def test_invoice_number_max_16_chars(self):
        """GST rule: invoice numbers max 16 chars."""
        text = "Invoice Number: ABCDEFGHIJKLMNOPQRSTUVWXYZ\nTotal: 100"
        fields = extract_fields_from_raw(text)
        if fields.invoice_number:
            assert len(fields.invoice_number) <= 16


# ── HSN/SAC Code Extraction ──────────────────────────────────────────

class TestHSNCodes:

    def test_hsn_codes_extracted(self):
        text = """HSN Code: 8471
Description: Computer
HSN: 4820
Description: Notebooks"""
        fields = extract_fields_from_raw(text)
        assert "8471" in fields.hsn_sac_codes
        assert "4820" in fields.hsn_sac_codes

    def test_hsn_codes_not_confused_with_years(self):
        """Year-like numbers (2024, 2025) should not be HSN codes."""
        text = "HSN: 8471\nDate: 2025"
        fields = extract_fields_from_raw(text)
        assert "2025" not in fields.hsn_sac_codes

    def test_no_hsn_returns_empty_list(self):
        text = "Simple invoice with no HSN codes"
        fields = extract_fields_from_raw(text)
        assert fields.hsn_sac_codes == []


# ── Fields Extracted Count ────────────────────────────────────────────

class TestFieldCount:

    def test_full_invoice_count(self):
        text = """TAX INVOICE
27AAPFU0939F1ZV
29AABCU9603R1ZM
ABC Trading Co
Invoice No: INV-001
Invoice Date: 15/03/2026
Taxable Value: 10000.00
CGST @ 9%: 900.00
SGST @ 9%: 900.00
IGST: 0
Total: 11800.00
HSN: 8471
Computer Equipment"""
        fields = extract_fields_from_raw(text)
        # Should have most fields extracted
        assert fields.fields_extracted_count >= 6

    def test_empty_text_zero_count(self):
        fields = extract_fields_from_raw("")
        assert fields.fields_extracted_count == 0


# ── Serialization ─────────────────────────────────────────────────────

class TestSerialization:

    def test_to_dict_decimal_serialized_as_string(self):
        text = "Taxable: 1000.00\nTotal: 1180.00\nCGST: 90.00\nSGST: 90.00"
        fields = extract_fields_from_raw(text)
        d = fields.to_dict()
        if d["taxable_value"] is not None:
            assert isinstance(d["taxable_value"], str)

    def test_to_scorer_dict_has_all_keys(self):
        fields = ExtractedFields()
        d = fields.to_scorer_dict()
        expected_keys = {
            "gstin_supplier", "gstin_recipient", "invoice_number",
            "invoice_date", "taxable_value", "cgst_amount", "sgst_amount",
            "igst_amount", "total_amount", "hsn_sac_codes", "place_of_supply",
        }
        assert set(d.keys()) == expected_keys
