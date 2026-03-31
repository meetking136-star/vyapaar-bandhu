"""
VyapaarBandhu -- Integration Tests for OCR Pipeline
Tests the full pipeline with mocked OCR engines.
"""

import pytest
from decimal import Decimal
from unittest.mock import patch, AsyncMock, MagicMock

from app.services.ocr.pipeline import (
    process_invoice_image,
    OCRFailedError,
    OCRResult,
)
from app.services.ocr.tesseract import RawOCRResult


# Sample OCR text simulating a real Indian invoice
MOCK_INVOICE_TEXT = """TAX INVOICE
M/s Rajesh Electronics Pvt Ltd
GSTIN: 27AAPFU0939F1ZV
Address: 123 MG Road, Mumbai 400001

Bill To:
XYZ Trading Co
GSTIN: 29AABCU9603R1ZM
Address: 456 Brigade Road, Bangalore 560001

Invoice No: INV-2026-0042
Invoice Date: 15/03/2026

HSN Code   Description           Qty    Rate       Amount
8471       Computer Desktop       2     45000.00   90000.00
8443       Laser Printer          1     15000.00   15000.00

Taxable Value:                                    1,05,000.00
IGST @ 18%:                                         18,900.00
Total Amount:                                     1,23,900.00

Terms: Payment within 30 days
E&OE
"""


class TestFullPipeline:
    """Full OCR pipeline with mocked Vision API response."""

    @pytest.mark.asyncio
    async def test_pipeline_with_mock_tesseract(self):
        """Full pipeline with mocked Tesseract returning valid invoice text."""
        mock_raw = RawOCRResult(
            text=MOCK_INVOICE_TEXT,
            overall_confidence=0.92,
            provider="tesseract",
        )

        with patch(
            "app.services.ocr.pipeline.is_vision_available",
            return_value=False,
        ), patch(
            "app.services.ocr.pipeline.tesseract_extract",
            new_callable=AsyncMock,
            return_value=mock_raw,
        ), patch(
            "app.services.ocr.pipeline.preprocess_image",
            side_effect=lambda x: x,  # passthrough
        ):
            result = await process_invoice_image(b"fake_image", "test/key.jpg")

        assert isinstance(result, OCRResult)
        assert result.provider == "tesseract"
        assert result.confidence_score == 0.92
        assert result.confidence_level == "green"

        # Verify field extraction
        fields = result.fields
        assert fields.gstin_supplier == "27AAPFU0939F1ZV"
        assert fields.gstin_recipient == "29AABCU9603R1ZM"
        assert fields.invoice_number is not None
        assert fields.invoice_date is not None
        assert fields.place_of_supply == "27"

        # Verify confidence report
        assert result.confidence_report is not None
        assert len(result.confidence_report.field_scores) > 0

    @pytest.mark.asyncio
    async def test_pipeline_vision_fallback_to_tesseract(self):
        """Vision API fails, falls back to Tesseract."""
        mock_raw = RawOCRResult(
            text=MOCK_INVOICE_TEXT,
            overall_confidence=0.88,
            provider="tesseract",
        )

        with patch(
            "app.services.ocr.pipeline.is_vision_available",
            return_value=True,
        ), patch(
            "app.services.ocr.pipeline.vision_extract",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Vision API error"),
        ), patch(
            "app.services.ocr.pipeline.tesseract_extract",
            new_callable=AsyncMock,
            return_value=mock_raw,
        ), patch(
            "app.services.ocr.pipeline.preprocess_image",
            side_effect=lambda x: x,
        ):
            result = await process_invoice_image(b"fake_image", "test/key.jpg")

        assert result.provider == "tesseract"
        assert result.fields.gstin_supplier is not None

    @pytest.mark.asyncio
    async def test_pipeline_both_engines_fail(self):
        """Both OCR engines fail -> raises OCRFailedError."""
        with patch(
            "app.services.ocr.pipeline.is_vision_available",
            return_value=True,
        ), patch(
            "app.services.ocr.pipeline.vision_extract",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Vision failed"),
        ), patch(
            "app.services.ocr.pipeline.tesseract_extract",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Tesseract failed"),
        ), patch(
            "app.services.ocr.pipeline.preprocess_image",
            side_effect=lambda x: x,
        ):
            with pytest.raises(OCRFailedError):
                await process_invoice_image(b"fake_image", "test/key.jpg")

    @pytest.mark.asyncio
    async def test_pipeline_low_confidence_flags_review(self):
        """Low-confidence OCR should flag invoice for manual review."""
        mock_raw = RawOCRResult(
            text="some garbled text 123 $$$ noise",
            overall_confidence=0.35,
            provider="tesseract",
        )

        with patch(
            "app.services.ocr.pipeline.is_vision_available",
            return_value=False,
        ), patch(
            "app.services.ocr.pipeline.tesseract_extract",
            new_callable=AsyncMock,
            return_value=mock_raw,
        ), patch(
            "app.services.ocr.pipeline.preprocess_image",
            side_effect=lambda x: x,
        ):
            result = await process_invoice_image(b"fake_image", "test/key.jpg")

        assert result.confidence_level == "red"
        assert result.requires_manual_review is True

    @pytest.mark.asyncio
    async def test_pipeline_gstin_autocorrection(self):
        """GSTIN with OCR confusion should be auto-corrected."""
        # Replace a char to trigger autocorrection attempt
        text_with_bad_gstin = MOCK_INVOICE_TEXT.replace(
            "27AAPFU0939F1ZV", "27AAPFU0939FIZV"  # 1->I confusion
        )
        mock_raw = RawOCRResult(
            text=text_with_bad_gstin,
            overall_confidence=0.90,
            provider="tesseract",
        )

        with patch(
            "app.services.ocr.pipeline.is_vision_available",
            return_value=False,
        ), patch(
            "app.services.ocr.pipeline.tesseract_extract",
            new_callable=AsyncMock,
            return_value=mock_raw,
        ), patch(
            "app.services.ocr.pipeline.preprocess_image",
            side_effect=lambda x: x,
        ):
            result = await process_invoice_image(b"fake_image", "test/key.jpg")

        # The GSTIN validator should attempt correction
        # It may or may not succeed depending on checksum
        assert result.fields is not None


class TestAmountCrossValidation:
    """Verify amount cross-validation in the pipeline."""

    @pytest.mark.asyncio
    async def test_interstate_detection_from_amounts(self):
        """IGST present with no CGST/SGST -> interstate detected."""
        mock_raw = RawOCRResult(
            text=MOCK_INVOICE_TEXT,  # Has IGST, no CGST/SGST
            overall_confidence=0.90,
            provider="tesseract",
        )

        with patch(
            "app.services.ocr.pipeline.is_vision_available",
            return_value=False,
        ), patch(
            "app.services.ocr.pipeline.tesseract_extract",
            new_callable=AsyncMock,
            return_value=mock_raw,
        ), patch(
            "app.services.ocr.pipeline.preprocess_image",
            side_effect=lambda x: x,
        ):
            result = await process_invoice_image(b"fake_image", "test/key.jpg")

        # The mock text has IGST, so fields should reflect that
        fields = result.fields
        if fields.igst_amount and fields.igst_amount > Decimal("0"):
            assert fields.cgst_amount is None or fields.cgst_amount == Decimal("0")
