"""
VyapaarBandhu -- Per-Field Confidence Scoring for OCR Results

Each extracted field gets a confidence score (0.0-1.0) based on:
  - OCR engine's raw confidence
  - Validation checks (checksum, format, cross-field consistency)
  - Extraction method reliability (regex > positional > fallback)

Thresholds are named constants with documented rationale.
These will be tuned against the evaluation dataset in Phase 3.12-3.15.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
import re

import structlog

logger = structlog.get_logger()


# ── Per-field confidence thresholds ───────────────────────────────────
# Basis: GSTIN has a Modulo 36 checksum so we can validate with certainty.
# Any GSTIN that passes checksum gets 1.0; partial matches get penalized.
GSTIN_CONFIDENCE_THRESHOLD = Decimal("0.95")

# Dates have multiple valid formats (DD/MM/YYYY, DD-MM-YYYY, DD MMM YYYY).
# Lower threshold because OCR often garbles separators but keeps digits.
DATE_CONFIDENCE_THRESHOLD = Decimal("0.80")

# Financial fields require high confidence -- errors here mean wrong
# GSTR-3B filing which attracts penalties under GST Act Section 122.
AMOUNT_CONFIDENCE_THRESHOLD = Decimal("0.90")

# Invoice numbers are alphanumeric, max 16 chars per GST rules.
# Medium threshold because OCR commonly confuses O/0 and I/1.
INVOICE_NUMBER_CONFIDENCE_THRESHOLD = Decimal("0.85")

# HSN/SAC codes are 4-8 digit numbers with a known valid set.
# Medium-high threshold; wrong HSN means wrong tax rate.
HSN_SAC_CONFIDENCE_THRESHOLD = Decimal("0.88")

# Place of supply is a 2-digit state code derived from GSTIN.
# If GSTIN is valid, place of supply is deterministic (confidence = 1.0).
PLACE_OF_SUPPLY_CONFIDENCE_THRESHOLD = Decimal("0.95")

# Overall threshold below which the invoice is flagged for manual review
OVERALL_CONFIDENCE_THRESHOLD = Decimal("0.85")

# Threshold below which a field is considered "low confidence"
LOW_CONFIDENCE_CUTOFF = Decimal("0.70")


@dataclass
class FieldConfidence:
    """Confidence score for a single extracted field."""
    field_name: str
    score: Decimal
    extraction_method: str  # "regex" | "positional" | "fallback" | "derived"
    is_below_threshold: bool = False
    validation_notes: str = ""


@dataclass
class ConfidenceReport:
    """Aggregate confidence report for all extracted fields."""
    field_scores: dict[str, FieldConfidence] = field(default_factory=dict)
    overall_score: Decimal = Decimal("0.00")
    low_confidence_fields: list[str] = field(default_factory=list)
    requires_manual_review: bool = False

    def to_json(self) -> dict:
        """Serialize to JSON-compatible dict for storage in ocr_confidence_json."""
        return {
            name: {
                "score": str(fc.score),
                "method": fc.extraction_method,
                "below_threshold": fc.is_below_threshold,
                "notes": fc.validation_notes,
            }
            for name, fc in self.field_scores.items()
        }


# ── Regex patterns for validation ─────────────────────────────────────
GSTIN_RE = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]$"
)
DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
INVOICE_NUMBER_RE = re.compile(r"^[A-Z0-9/\-]{1,16}$", re.IGNORECASE)
HSN_RE = re.compile(r"^\d{4,8}$")
STATE_CODE_RE = re.compile(r"^\d{2}$")


def score_extracted_fields(
    extracted: dict,
    ocr_confidence: float,
) -> ConfidenceReport:
    """
    Score each extracted field and produce an aggregate confidence report.

    Args:
        extracted: dict of field_name -> extracted_value (from field_extractor)
        ocr_confidence: raw OCR engine confidence (0.0-1.0)

    Returns:
        ConfidenceReport with per-field scores and overall assessment.
    """
    report = ConfidenceReport()
    base = Decimal(str(round(ocr_confidence, 4)))

    # Score each field
    report.field_scores["gstin_supplier"] = _score_gstin(
        extracted.get("gstin_supplier"), base, "gstin_supplier"
    )
    report.field_scores["gstin_recipient"] = _score_gstin(
        extracted.get("gstin_recipient"), base, "gstin_recipient"
    )
    report.field_scores["invoice_number"] = _score_invoice_number(
        extracted.get("invoice_number"), base
    )
    report.field_scores["invoice_date"] = _score_date(
        extracted.get("invoice_date"), base
    )
    report.field_scores["taxable_value"] = _score_amount(
        extracted.get("taxable_value"), base, "taxable_value"
    )
    report.field_scores["cgst_amount"] = _score_amount(
        extracted.get("cgst_amount"), base, "cgst_amount"
    )
    report.field_scores["sgst_amount"] = _score_amount(
        extracted.get("sgst_amount"), base, "sgst_amount"
    )
    report.field_scores["igst_amount"] = _score_amount(
        extracted.get("igst_amount"), base, "igst_amount"
    )
    report.field_scores["total_amount"] = _score_amount(
        extracted.get("total_amount"), base, "total_amount"
    )
    report.field_scores["hsn_sac_codes"] = _score_hsn_codes(
        extracted.get("hsn_sac_codes"), base
    )
    report.field_scores["place_of_supply"] = _score_place_of_supply(
        extracted.get("place_of_supply"), base
    )

    # Cross-field validation: amounts should add up
    amount_validation = _validate_amount_consistency(extracted)
    if amount_validation:
        for field_name in ["taxable_value", "cgst_amount", "sgst_amount",
                           "igst_amount", "total_amount"]:
            if field_name in report.field_scores:
                fc = report.field_scores[field_name]
                fc.score = (fc.score * Decimal("0.80")).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
                fc.validation_notes += f" Amount mismatch: {amount_validation}"

    # Cross-field validation: IGST vs CGST+SGST mutual exclusivity
    tax_type_issue = _validate_tax_type_consistency(extracted)
    if tax_type_issue:
        for field_name in ["cgst_amount", "sgst_amount", "igst_amount"]:
            if field_name in report.field_scores:
                fc = report.field_scores[field_name]
                fc.validation_notes += f" {tax_type_issue}"

    # Calculate overall score and identify low-confidence fields
    scores = [fc.score for fc in report.field_scores.values()]
    if scores:
        report.overall_score = (sum(scores) / len(scores)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )

    for name, fc in report.field_scores.items():
        if fc.score < LOW_CONFIDENCE_CUTOFF:
            report.low_confidence_fields.append(name)
            fc.is_below_threshold = True

    report.requires_manual_review = (
        report.overall_score < OVERALL_CONFIDENCE_THRESHOLD
        or len(report.low_confidence_fields) > 0
    )

    logger.info(
        "confidence.scored",
        overall=str(report.overall_score),
        low_fields=report.low_confidence_fields,
        manual_review=report.requires_manual_review,
    )

    return report


def _score_gstin(value: str | None, base: Decimal, field_name: str) -> FieldConfidence:
    """Score GSTIN field. Checksum-validated GSTINs get 1.0."""
    if value is None:
        return FieldConfidence(
            field_name=field_name, score=Decimal("0.00"),
            extraction_method="none", validation_notes="Field not extracted",
        )

    # Check format
    if not GSTIN_RE.match(value):
        return FieldConfidence(
            field_name=field_name, score=Decimal("0.30"),
            extraction_method="regex", validation_notes="Invalid GSTIN format",
        )

    # Verify checksum
    from app.services.ocr.gstin_validator import _verify_checksum
    if _verify_checksum(value):
        return FieldConfidence(
            field_name=field_name, score=Decimal("1.00"),
            extraction_method="regex", validation_notes="Checksum verified",
        )

    # Format OK but checksum fails -- OCR may have garbled one character
    return FieldConfidence(
        field_name=field_name, score=Decimal("0.50"),
        extraction_method="regex",
        validation_notes="Format valid but checksum failed",
    )


def _score_invoice_number(value: str | None, base: Decimal) -> FieldConfidence:
    if value is None:
        return FieldConfidence(
            field_name="invoice_number", score=Decimal("0.00"),
            extraction_method="none", validation_notes="Field not extracted",
        )

    score = base
    method = "regex"

    if len(value) > 16:
        score = (score * Decimal("0.70")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        method = "fallback"

    if INVOICE_NUMBER_RE.match(value):
        score = min(score + Decimal("0.10"), Decimal("1.00"))

    return FieldConfidence(
        field_name="invoice_number", score=score,
        extraction_method=method,
    )


def _score_date(value: str | None, base: Decimal) -> FieldConfidence:
    if value is None:
        return FieldConfidence(
            field_name="invoice_date", score=Decimal("0.00"),
            extraction_method="none", validation_notes="Field not extracted",
        )

    score = base
    if DATE_RE.match(value):
        # Validate actual date values
        try:
            parts = value.split("-")
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
            if 1 <= day <= 31 and 1 <= month <= 12 and 2000 <= year <= 2100:
                score = min(score + Decimal("0.15"), Decimal("1.00"))
            else:
                score = (score * Decimal("0.50")).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
        except (ValueError, IndexError):
            score = (score * Decimal("0.60")).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
    else:
        score = (score * Decimal("0.70")).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )

    return FieldConfidence(
        field_name="invoice_date", score=score,
        extraction_method="regex",
    )


def _score_amount(value, base: Decimal, field_name: str) -> FieldConfidence:
    if value is None:
        return FieldConfidence(
            field_name=field_name, score=Decimal("0.00"),
            extraction_method="none", validation_notes="Field not extracted",
        )

    score = base
    try:
        dec_val = Decimal(str(value))
        if dec_val < Decimal("0"):
            score = Decimal("0.20")
        elif dec_val == Decimal("0"):
            # Zero amounts are valid (e.g., IGST=0 for intrastate)
            score = min(base + Decimal("0.05"), Decimal("1.00"))
        else:
            score = min(base + Decimal("0.10"), Decimal("1.00"))
    except Exception:
        score = Decimal("0.20")

    return FieldConfidence(
        field_name=field_name, score=score,
        extraction_method="regex",
    )


def _score_hsn_codes(value: list | None, base: Decimal) -> FieldConfidence:
    if not value:
        return FieldConfidence(
            field_name="hsn_sac_codes", score=Decimal("0.00"),
            extraction_method="none", validation_notes="No HSN/SAC codes found",
        )

    valid_count = sum(1 for code in value if HSN_RE.match(str(code)))
    total = len(value)
    ratio = Decimal(str(valid_count)) / Decimal(str(total)) if total > 0 else Decimal("0")
    score = (base * ratio).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    return FieldConfidence(
        field_name="hsn_sac_codes", score=score,
        extraction_method="regex",
        validation_notes=f"{valid_count}/{total} codes match HSN pattern",
    )


def _score_place_of_supply(value: str | None, base: Decimal) -> FieldConfidence:
    if value is None:
        return FieldConfidence(
            field_name="place_of_supply", score=Decimal("0.00"),
            extraction_method="none", validation_notes="Not determined",
        )

    from app.services.compliance.gstin_state_mapper import STATE_CODES
    if value in STATE_CODES:
        return FieldConfidence(
            field_name="place_of_supply", score=Decimal("1.00"),
            extraction_method="derived",
            validation_notes=f"Valid state: {STATE_CODES[value]}",
        )

    return FieldConfidence(
        field_name="place_of_supply", score=Decimal("0.30"),
        extraction_method="derived",
        validation_notes="Invalid state code",
    )


def _validate_amount_consistency(extracted: dict) -> str | None:
    """
    Check that taxable_value + cgst + sgst + igst = total_amount.
    Tolerance: +/-1 rupee (to account for rounding in invoices).
    Returns error message if mismatch, None if OK.
    """
    try:
        taxable = Decimal(str(extracted.get("taxable_value") or 0))
        cgst = Decimal(str(extracted.get("cgst_amount") or 0))
        sgst = Decimal(str(extracted.get("sgst_amount") or 0))
        igst = Decimal(str(extracted.get("igst_amount") or 0))
        total = Decimal(str(extracted.get("total_amount") or 0))
    except Exception:
        return "Could not parse amounts for validation"

    if total == Decimal("0"):
        return None  # No total to validate against

    computed = taxable + cgst + sgst + igst
    diff = abs(computed - total)

    if diff > Decimal("1.00"):
        return f"computed={computed} vs total={total}, diff={diff}"

    return None


def _validate_tax_type_consistency(extracted: dict) -> str | None:
    """
    IGST and CGST+SGST are mutually exclusive:
      - Interstate: IGST > 0, CGST = SGST = 0
      - Intrastate: CGST + SGST > 0, IGST = 0
    Flag if both are non-zero (OCR may have extracted wrong fields).
    """
    try:
        cgst = Decimal(str(extracted.get("cgst_amount") or 0))
        sgst = Decimal(str(extracted.get("sgst_amount") or 0))
        igst = Decimal(str(extracted.get("igst_amount") or 0))
    except Exception:
        return None

    has_cgst_sgst = (cgst > 0 or sgst > 0)
    has_igst = igst > 0

    if has_cgst_sgst and has_igst:
        return "Both IGST and CGST/SGST are non-zero -- likely OCR error"

    return None
