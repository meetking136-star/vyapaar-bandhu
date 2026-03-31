"""
VyapaarBandhu -- Post-OCR Field Extraction
Regex + heuristics to parse invoice fields from raw OCR text.

RULE 3: All amounts use Python Decimal with ROUND_HALF_UP. No float anywhere.
RULE 1: No AI/LLM calls. Deterministic extraction only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

import structlog

logger = structlog.get_logger()

ZERO = Decimal("0.00")


@dataclass
class ExtractedFields:
    gstin_supplier: str | None = None       # seller GSTIN (15 chars)
    gstin_recipient: str | None = None      # buyer GSTIN (15 chars)
    seller_name: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None         # DD-MM-YYYY string
    taxable_value: Decimal | None = None    # was taxable_amount
    cgst_amount: Decimal | None = None
    sgst_amount: Decimal | None = None
    igst_amount: Decimal | None = None
    total_amount: Decimal | None = None
    product_description: str | None = None
    hsn_sac_codes: list[str] = field(default_factory=list)
    place_of_supply: str | None = None      # 2-digit state code
    gstin_was_autocorrected: bool = False
    gstin_original_ocr: str | None = None
    fields_extracted_count: int = 0

    # Legacy alias for backward compat with existing OCR task
    @property
    def seller_gstin(self) -> str | None:
        return self.gstin_supplier

    @seller_gstin.setter
    def seller_gstin(self, value: str | None) -> None:
        self.gstin_supplier = value

    # Legacy alias
    @property
    def taxable_amount(self) -> Decimal | None:
        return self.taxable_value

    @taxable_amount.setter
    def taxable_amount(self, value: Decimal | None) -> None:
        self.taxable_value = value

    def to_dict(self) -> dict:
        """Serialize for JSON storage in extracted_fields_json."""
        return {
            "gstin_supplier": self.gstin_supplier,
            "gstin_recipient": self.gstin_recipient,
            "seller_name": self.seller_name,
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date,
            "taxable_value": str(self.taxable_value) if self.taxable_value is not None else None,
            "cgst_amount": str(self.cgst_amount) if self.cgst_amount is not None else None,
            "sgst_amount": str(self.sgst_amount) if self.sgst_amount is not None else None,
            "igst_amount": str(self.igst_amount) if self.igst_amount is not None else None,
            "total_amount": str(self.total_amount) if self.total_amount is not None else None,
            "product_description": self.product_description,
            "hsn_sac_codes": self.hsn_sac_codes,
            "place_of_supply": self.place_of_supply,
        }

    def to_scorer_dict(self) -> dict:
        """Dict formatted for confidence_scorer input."""
        return {
            "gstin_supplier": self.gstin_supplier,
            "gstin_recipient": self.gstin_recipient,
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date,
            "taxable_value": self.taxable_value,
            "cgst_amount": self.cgst_amount,
            "sgst_amount": self.sgst_amount,
            "igst_amount": self.igst_amount,
            "total_amount": self.total_amount,
            "hsn_sac_codes": self.hsn_sac_codes,
            "place_of_supply": self.place_of_supply,
        }


# ── GSTIN pattern ─────────────────────────────────────────────────────
GSTIN_RE = re.compile(
    r"\b(\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9])\b", re.IGNORECASE
)

# ── Invoice number patterns ───────────────────────────────────────────
INVOICE_NO_PATTERNS = [
    re.compile(
        r"(?:invoice|inv|bill)\s*(?:no|number|#|num)[\s.:]*([A-Z0-9/\-]{3,16})",
        re.IGNORECASE,
    ),
    re.compile(r"(?:invoice|inv)\s*[.:]\s*([A-Z0-9/\-]{3,16})", re.IGNORECASE),
    re.compile(
        r"(?:bill|receipt)\s*(?:no|#)[\s.:]*([A-Z0-9/\-]{3,16})", re.IGNORECASE
    ),
]

# ── Date patterns ─────────────────────────────────────────────────────
DATE_PATTERNS = [
    # DD-MM-YYYY, DD/MM/YYYY, DD.MM.YYYY
    re.compile(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})"),
    # DD MMM YYYY (e.g., 15 Jan 2024)
    re.compile(
        r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{4})",
        re.IGNORECASE,
    ),
    # YYYY-MM-DD
    re.compile(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})"),
]

MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

# ── Amount patterns ───────────────────────────────────────────────────
AMOUNT_RE = re.compile(r"[\d,]+\.?\d*")

TAXABLE_KEYWORDS = [
    "taxable", "assessable", "base amount", "sub total", "subtotal",
    "taxable value", "taxable amt",
]
CGST_KEYWORDS = ["cgst", "c.g.s.t", "central gst", "central tax"]
SGST_KEYWORDS = ["sgst", "s.g.s.t", "state gst", "state tax", "utgst"]
IGST_KEYWORDS = ["igst", "i.g.s.t", "integrated gst", "integrated tax"]
TOTAL_KEYWORDS = [
    "total", "grand total", "net amount", "amount payable",
    "invoice total", "total amount", "total value",
]

# ── HSN/SAC patterns ──────────────────────────────────────────────────
HSN_SAC_RE = re.compile(r"\b(\d{4,8})\b")
HSN_KEYWORDS = ["hsn", "sac", "hsn/sac", "hsn code", "sac code"]


def extract_fields_from_raw(text: str) -> ExtractedFields:
    """
    Extract invoice fields from raw OCR text using regex + heuristics.
    This is deterministic -- no AI involved.

    Returns ExtractedFields with all amounts as Decimal (RULE 3).
    """
    fields = ExtractedFields()
    lines = text.split("\n")

    # 1. GSTINs -- extract up to 2 (supplier + recipient)
    gstins = _extract_all_gstins(text)
    if len(gstins) >= 1:
        fields.gstin_supplier = gstins[0]
    if len(gstins) >= 2:
        fields.gstin_recipient = gstins[1]

    # Derive place of supply from recipient GSTIN (buyer's state).
    # For B2C invoices (no recipient GSTIN), fall back to explicit
    # "Place of Supply" text in the invoice, then leave None.
    if fields.gstin_recipient and len(fields.gstin_recipient) >= 2:
        fields.place_of_supply = fields.gstin_recipient[:2]
    else:
        fields.place_of_supply = _extract_place_of_supply(text)

    # 2. Invoice number
    for pattern in INVOICE_NO_PATTERNS:
        match = pattern.search(text)
        if match:
            inv_num = match.group(1).strip()
            # GST rule: max 16 chars
            fields.invoice_number = inv_num[:16]
            break

    # 3. Date
    fields.invoice_date = _extract_date(text)

    # 4. Seller name
    fields.seller_name = _extract_seller_name(lines, fields.gstin_supplier)

    # 5-8. Tax amounts (Decimal only)
    fields.taxable_value = _extract_amount(lines, TAXABLE_KEYWORDS)
    fields.cgst_amount = _extract_amount(lines, CGST_KEYWORDS)
    fields.sgst_amount = _extract_amount(lines, SGST_KEYWORDS)
    fields.igst_amount = _extract_amount(lines, IGST_KEYWORDS)

    # 9. Total amount
    fields.total_amount = _extract_amount(lines, TOTAL_KEYWORDS)

    # 10. Product description
    fields.product_description = _extract_description(lines)

    # 11. HSN/SAC codes
    fields.hsn_sac_codes = _extract_hsn_codes(lines)

    # Count extracted fields
    count = sum(
        1
        for v in [
            fields.gstin_supplier,
            fields.gstin_recipient,
            fields.seller_name,
            fields.invoice_number,
            fields.invoice_date,
            fields.taxable_value,
            fields.cgst_amount,
            fields.sgst_amount,
            fields.igst_amount,
            fields.total_amount,
        ]
        if v is not None
    )
    if fields.hsn_sac_codes:
        count += 1
    if fields.place_of_supply:
        count += 1
    fields.fields_extracted_count = count

    logger.info("ocr.fields.extracted", count=count)
    return fields


def _extract_all_gstins(text: str) -> list[str]:
    """
    Extract all unique GSTINs from text.
    First match is assumed to be the supplier, second is the recipient.
    """
    matches = GSTIN_RE.findall(text)
    seen = set()
    result = []
    for m in matches:
        upper = m.upper()
        if upper not in seen:
            seen.add(upper)
            result.append(upper)
    return result


def _extract_date(text: str) -> str | None:
    """Extract date from OCR text. Returns DD-MM-YYYY format."""
    date_keywords = ["date", "dated", "invoice date", "bill date"]
    lines = text.split("\n")

    # Look for date near keywords first
    for line in lines:
        line_lower = line.lower()
        if any(kw in line_lower for kw in date_keywords):
            result = _try_parse_date(line)
            if result:
                return result

    # Fallback: find any date in text
    return _try_parse_date(text)


def _try_parse_date(text: str) -> str | None:
    """Try all date patterns and return DD-MM-YYYY or None."""
    # Pattern 1: DD/MM/YYYY etc.
    match = DATE_PATTERNS[0].search(text)
    if match:
        return _normalize_numeric_date(match)

    # Pattern 2: DD MMM YYYY
    match = DATE_PATTERNS[1].search(text)
    if match:
        day = match.group(1).zfill(2)
        month_str = match.group(2).lower()[:3]
        month = MONTH_MAP.get(month_str, "01")
        year = match.group(3)
        return f"{day}-{month}-{year}"

    # Pattern 3: YYYY-MM-DD
    match = DATE_PATTERNS[2].search(text)
    if match:
        year = match.group(1)
        month = match.group(2).zfill(2)
        day = match.group(3).zfill(2)
        return f"{day}-{month}-{year}"

    return None


def _normalize_numeric_date(match: re.Match) -> str:
    """Normalize matched date to DD-MM-YYYY."""
    groups = match.groups()
    if len(groups[0]) == 4:
        # YYYY-MM-DD format
        return f"{groups[2].zfill(2)}-{groups[1].zfill(2)}-{groups[0]}"
    else:
        # DD-MM-YYYY format
        return f"{groups[0].zfill(2)}-{groups[1].zfill(2)}-{groups[2]}"


def _extract_amount(lines: list[str], keywords: list[str]) -> Decimal | None:
    """
    Extract an amount from lines matching keywords.
    Returns Decimal (RULE 3: no float arithmetic).
    """
    for line in lines:
        line_lower = line.lower()
        if any(kw in line_lower for kw in keywords):
            amounts = AMOUNT_RE.findall(line)
            if amounts:
                # Take the last amount on the line (usually the value)
                try:
                    raw = amounts[-1].replace(",", "")
                    val = Decimal(raw).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    if val > ZERO:
                        return val
                except (InvalidOperation, ValueError):
                    continue
    return None


def _extract_seller_name(lines: list[str], gstin: str | None) -> str | None:
    """Extract seller name -- usually near the top or near GSTIN."""
    skip_words = {
        "tax invoice", "invoice", "bill", "receipt", "gstin",
        "date", "original", "duplicate", "copy",
    }

    for line in lines[:10]:
        clean = line.strip()
        if len(clean) < 3 or len(clean) > 100:
            continue
        if clean.lower() in skip_words:
            continue
        if GSTIN_RE.search(clean):
            continue
        if re.match(r"^[\d/\-.:]+$", clean):
            continue
        if any(c.isalpha() for c in clean):
            return clean[:100]

    return None


def _extract_description(lines: list[str]) -> str | None:
    """Extract product/service description from invoice lines."""
    skip_words = {
        "invoice", "bill", "gstin", "date", "total", "cgst", "sgst",
        "igst", "tax", "amount", "subtotal", "grand", "receipt",
        "hsn", "sac", "qty", "rate", "quantity",
    }

    candidates = []
    for line in lines:
        clean = line.strip()
        if len(clean) < 5 or len(clean) > 200:
            continue
        lower = clean.lower()
        if any(sw in lower for sw in skip_words):
            continue
        if GSTIN_RE.search(clean):
            continue
        if re.match(r"^[\d\s,.\-/]+$", clean):
            continue
        candidates.append(clean)

    if not candidates:
        return None

    # Return the longest candidate (most descriptive)
    return max(candidates, key=len)[:200]


PLACE_OF_SUPPLY_RE = re.compile(
    r"place\s+of\s+supply[\s.:]+(\d{2})", re.IGNORECASE
)


def _extract_place_of_supply(text: str) -> str | None:
    """Extract place of supply state code from invoice text (B2C fallback)."""
    match = PLACE_OF_SUPPLY_RE.search(text)
    if match:
        return match.group(1)
    return None


def _extract_hsn_codes(lines: list[str]) -> list[str]:
    """
    Extract HSN/SAC codes from invoice text.
    HSN codes are 4-8 digit numbers that appear near HSN/SAC keywords.
    """
    codes: list[str] = []
    seen = set()

    for line in lines:
        line_lower = line.lower()
        if any(kw in line_lower for kw in HSN_KEYWORDS):
            matches = HSN_SAC_RE.findall(line)
            for m in matches:
                # Filter out likely non-HSN numbers (years, amounts, etc.)
                if len(m) >= 4 and m not in seen:
                    # Exclude common false positives
                    num = int(m)
                    if 1000 <= num <= 99999999 and not (2000 <= num <= 2100):
                        codes.append(m)
                        seen.add(m)

    return codes
