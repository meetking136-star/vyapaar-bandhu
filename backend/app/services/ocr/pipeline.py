"""
VyapaarBandhu -- OCR Pipeline Orchestrator
Primary: Google Vision API | Fallback: Tesseract 5
Pre-processing: grayscale + deskew + binarize + scale (cv2)
Post-processing: field extraction + GSTIN validation + confidence scoring

RULE 7: Preprocessing runs BEFORE any OCR engine call.
RULE 8: Fallback chain: Vision API -> Tesseract -> manual_review_required.
"""
from __future__ import annotations

import structlog
from dataclasses import dataclass, field

from app.config import settings
from app.services.ocr.preprocessor import preprocess_image
from app.services.ocr.tesseract import tesseract_extract, RawOCRResult
from app.services.ocr.field_extractor import extract_fields_from_raw, ExtractedFields
from app.services.ocr.gstin_validator import validate_and_correct_gstin
from app.services.ocr.confidence_scorer import score_extracted_fields, ConfidenceReport

logger = structlog.get_logger()


class LowConfidenceError(Exception):
    pass


class OCRFailedError(Exception):
    """Both OCR engines failed -- invoice needs manual review."""
    pass


@dataclass
class OCRResult:
    fields: ExtractedFields
    confidence_report: ConfidenceReport
    confidence_score: float
    confidence_level: str  # "green" | "amber" | "red"
    provider: str          # "google_vision" | "tesseract"
    requires_manual_review: bool
    raw_text: str = ""
    raw_text_length: int = 0
    low_confidence_fields: list[str] = field(default_factory=list)


async def process_invoice_image(image_bytes: bytes, image_s3_key: str) -> OCRResult:
    """
    Process an invoice image through the full OCR pipeline.

    1. Preprocess image (grayscale, deskew, binarize, scale)
    2. Primary OCR: Google Vision API
    3. Fallback OCR: Tesseract 5 (if Vision fails or low confidence)
    4. Field extraction (regex + heuristics)
    5. GSTIN validation + auto-correction
    6. Per-field confidence scoring
    7. Confidence classification (green/amber/red)

    Raises OCRFailedError if both engines fail entirely.
    """

    # Step 1: Preprocess image
    try:
        processed_bytes = preprocess_image(image_bytes)
        logger.info("ocr.preprocessed", original_size=len(image_bytes), processed_size=len(processed_bytes))
    except Exception as e:
        logger.warning("ocr.preprocess_failed", error=str(e))
        processed_bytes = image_bytes  # fall through with original

    # Step 2-3: OCR extraction with fallback chain
    raw_result = await _run_ocr_with_fallback(processed_bytes)

    # Step 4: Field extraction
    fields = extract_fields_from_raw(raw_result.text)

    # Step 5: GSTIN validation + auto-correction (supplier)
    if fields.gstin_supplier:
        correction = validate_and_correct_gstin(fields.gstin_supplier)
        if correction.was_corrected:
            fields.gstin_original_ocr = fields.gstin_supplier
            fields.gstin_supplier = correction.corrected
            fields.gstin_was_autocorrected = True
            logger.info(
                "ocr.gstin.supplier.autocorrected",
                original=fields.gstin_original_ocr,
                corrected=fields.gstin_supplier,
            )

    # GSTIN validation + auto-correction (recipient)
    if fields.gstin_recipient:
        correction = validate_and_correct_gstin(fields.gstin_recipient)
        if correction.was_corrected:
            fields.gstin_recipient = correction.corrected

    # Step 6: Per-field confidence scoring
    confidence_report = score_extracted_fields(
        fields.to_scorer_dict(), raw_result.overall_confidence
    )

    # Step 7: Overall confidence classification
    confidence = raw_result.overall_confidence
    confidence_level = classify_confidence(confidence)

    requires_manual_review = (
        confidence_report.requires_manual_review
        or confidence_level == "red"
    )

    return OCRResult(
        fields=fields,
        confidence_report=confidence_report,
        confidence_score=confidence,
        confidence_level=confidence_level,
        provider=raw_result.provider,
        requires_manual_review=requires_manual_review,
        raw_text=raw_result.text,
        raw_text_length=len(raw_result.text),
        low_confidence_fields=confidence_report.low_confidence_fields,
    )


async def _run_ocr_with_fallback(image_bytes: bytes) -> RawOCRResult:
    """
    Run OCR with fallback chain:
      1. Google Vision API (if available)
      2. Tesseract 5 (local fallback)
      3. Raise OCRFailedError if both fail
    """
    raw_result: RawOCRResult | None = None

    # Try Google Vision API first
    try:
        from app.services.ocr.vision_client import vision_extract, is_vision_available
        if is_vision_available():
            raw_result = await vision_extract(image_bytes)
            if raw_result.overall_confidence >= settings.OCR_FALLBACK_THRESHOLD:
                return raw_result
            logger.warning(
                "ocr.vision.low_confidence",
                confidence=raw_result.overall_confidence,
            )
    except Exception as e:
        logger.warning("ocr.vision.failed", error=str(e))

    # Fallback: Tesseract
    try:
        tesseract_result = await tesseract_extract(image_bytes)
        # If Vision gave us something, pick the better result
        if raw_result and raw_result.overall_confidence > tesseract_result.overall_confidence:
            return raw_result
        return tesseract_result
    except Exception as e:
        logger.error("ocr.tesseract.failed", error=str(e))
        # If Vision gave us anything, use it even if low confidence
        if raw_result:
            return raw_result

    raise OCRFailedError("Both Google Vision and Tesseract OCR failed")


def classify_confidence(score: float) -> str:
    """
    Classify OCR confidence into traffic light levels.
    Thresholds from config (empirical evaluation in Phase 3.12-3.15).
    """
    if score >= settings.OCR_CONFIDENCE_THRESHOLD:
        return "green"   # >= 0.85
    elif score >= settings.OCR_AMBER_THRESHOLD:
        return "amber"   # 0.75 - 0.85
    else:
        return "red"     # < 0.75
