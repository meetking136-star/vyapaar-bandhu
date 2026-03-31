"""
VyapaarBandhu -- Invoice Classifier (Deterministic Rules Only)

RULE 1: NEVER USE AI/LLM FOR GST LOGIC.
Classification (B2B/B2C, interstate/intrastate, RCM) uses deterministic
rules only. No GPT, no Claude, no ML model for tax decisions. Ever.

RULE 6: RCM detection must cover all 5 categories:
  - GTA (SAC 9965, 9967)
  - Legal services (SAC 9982)
  - Security services (SAC 9985)
  - Import of services (place of supply outside India)
  - Unregistered vendor (supplier GSTIN missing/invalid)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

import structlog

logger = structlog.get_logger()

ZERO = Decimal("0.00")


@dataclass
class ClassificationResult:
    """Result of deterministic invoice classification."""
    # Transaction type
    is_b2b: bool = False
    is_b2c: bool = False
    transaction_type: str = ""  # "B2B" | "B2C"

    # Interstate/intrastate
    is_interstate: bool = False
    is_intrastate: bool = False
    supply_type: str = ""  # "interstate" | "intrastate" | "unknown"
    igst_applicable: bool = False

    # RCM
    rcm_applicable: bool = False
    rcm_category: str | None = None
    rcm_reference: str = ""
    rcm_note: str = ""

    # Confidence and review
    requires_ca_review: bool = False
    review_reasons: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        """Serialize for storage in classification_json."""
        return {
            "transaction_type": self.transaction_type,
            "is_b2b": self.is_b2b,
            "is_b2c": self.is_b2c,
            "supply_type": self.supply_type,
            "is_interstate": self.is_interstate,
            "is_intrastate": self.is_intrastate,
            "igst_applicable": self.igst_applicable,
            "rcm_applicable": self.rcm_applicable,
            "rcm_category": self.rcm_category,
            "rcm_reference": self.rcm_reference,
            "rcm_note": self.rcm_note,
            "requires_ca_review": self.requires_ca_review,
            "review_reasons": self.review_reasons,
        }


# ── RCM SAC Codes ─────────────────────────────────────────────────────
# SAC codes that trigger Reverse Charge Mechanism
RCM_SAC_CODES: dict[str, dict] = {
    "9965": {
        "category": "gta",
        "reference": "Notification 13/2017-CT(R) Entry 1",
        "note": "GTA (Goods Transport Agency) services -- buyer pays GST",
    },
    "9967": {
        "category": "gta",
        "reference": "Notification 13/2017-CT(R) Entry 1",
        "note": "GTA support services -- buyer pays GST",
    },
    "9982": {
        "category": "legal",
        "reference": "Notification 13/2017-CT(R) Entry 2",
        "note": "Legal services from individual advocate -- RCM applies",
    },
    "9985": {
        "category": "security",
        "reference": "Notification 29/2018-CT(R)",
        "note": "Security services from non-body corporate -- RCM applies",
    },
}

# Keywords for RCM detection when SAC codes are not available
RCM_KEYWORDS: dict[str, dict] = {
    "gta": {
        "keywords": [
            "goods transport", "gta", "freight", "transport agency",
            "lorry", "truck", "cargo", "logistics",
        ],
        "category": "gta",
        "reference": "Notification 13/2017-CT(R) Entry 1",
        "note": "GTA services detected via description keywords",
    },
    "legal": {
        "keywords": [
            "legal", "advocate", "lawyer", "attorney", "legal service",
            "litigation", "arbitration", "legal counsel",
        ],
        "category": "legal",
        "reference": "Notification 13/2017-CT(R) Entry 2",
        "note": "Legal services detected via description keywords",
    },
    "security": {
        "keywords": [
            "security", "guard", "security service", "security agency",
            "watchman", "security guard",
        ],
        "category": "security",
        "reference": "Notification 29/2018-CT(R)",
        "note": "Security services detected via description keywords",
    },
    "import": {
        "keywords": [
            "import", "imported", "foreign", "overseas",
            "international service", "cross-border",
        ],
        "category": "import",
        "reference": "IGST Act Section 5(3)",
        "note": "Import of services -- recipient pays IGST under RCM",
    },
    "sponsorship": {
        "keywords": [
            "sponsorship", "sponsor", "event sponsorship",
        ],
        "category": "sponsorship",
        "reference": "Notification 13/2017-CT(R) Entry 5",
        "note": "Sponsorship services under RCM",
    },
}

# Indian state codes -- GSTIN first 2 digits
# Used to determine interstate vs intrastate
INDIAN_STATE_CODES = {
    f"{i:02d}" for i in range(1, 38)
} | {"97", "96"}  # 97 = Other Territory, 96 = Overseas


def classify_invoice(
    gstin_supplier: str | None,
    gstin_recipient: str | None,
    hsn_sac_codes: list[str] | None,
    description: str | None,
    igst_amount: Decimal | None,
    cgst_amount: Decimal | None,
    sgst_amount: Decimal | None,
    place_of_supply: str | None,
) -> ClassificationResult:
    """
    Classify an invoice using deterministic rules only (RULE 1).

    Returns ClassificationResult with B2B/B2C, interstate/intrastate,
    and RCM classification.
    """
    result = ClassificationResult()

    # ── B2B vs B2C classification ─────────────────────────────────
    result = _classify_b2b_b2c(result, gstin_supplier, gstin_recipient)

    # ── Interstate vs Intrastate ──────────────────────────────────
    result = _classify_supply_type(
        result, gstin_supplier, gstin_recipient,
        igst_amount, cgst_amount, sgst_amount, place_of_supply,
    )

    # ── RCM detection ─────────────────────────────────────────────
    result = _detect_rcm(
        result, gstin_supplier, hsn_sac_codes, description, place_of_supply,
    )

    logger.info(
        "classifier.result",
        type=result.transaction_type,
        supply=result.supply_type,
        rcm=result.rcm_applicable,
        rcm_category=result.rcm_category,
        review=result.requires_ca_review,
    )

    return result


def _classify_b2b_b2c(
    result: ClassificationResult,
    gstin_supplier: str | None,
    gstin_recipient: str | None,
) -> ClassificationResult:
    """
    B2B: Both supplier and recipient have valid GSTINs.
    B2C: Recipient GSTIN is missing or invalid.
    """
    supplier_valid = _is_valid_gstin_format(gstin_supplier)
    recipient_valid = _is_valid_gstin_format(gstin_recipient)

    if supplier_valid and recipient_valid:
        result.is_b2b = True
        result.transaction_type = "B2B"
    else:
        result.is_b2c = True
        result.transaction_type = "B2C"
        if not supplier_valid:
            result.review_reasons.append("Supplier GSTIN missing or invalid")
            result.requires_ca_review = True

    return result


def _classify_supply_type(
    result: ClassificationResult,
    gstin_supplier: str | None,
    gstin_recipient: str | None,
    igst_amount: Decimal | None,
    cgst_amount: Decimal | None,
    sgst_amount: Decimal | None,
    place_of_supply: str | None,
) -> ClassificationResult:
    """
    Interstate: supplier state != recipient state, or IGST is charged.
    Intrastate: supplier state == recipient state, or CGST+SGST is charged.

    Priority: state codes from GSTIN > tax amounts > place_of_supply.
    """
    supplier_state = _extract_state_code(gstin_supplier)
    recipient_state = _extract_state_code(gstin_recipient)

    # Method 1: Compare state codes from GSTINs
    if supplier_state and recipient_state:
        if supplier_state != recipient_state:
            result.is_interstate = True
            result.supply_type = "interstate"
            result.igst_applicable = True
        else:
            result.is_intrastate = True
            result.supply_type = "intrastate"
            result.igst_applicable = False
        return result

    # Method 2: Infer from tax amounts
    igst = igst_amount or ZERO
    cgst = cgst_amount or ZERO
    sgst = sgst_amount or ZERO

    if igst > ZERO and cgst == ZERO and sgst == ZERO:
        result.is_interstate = True
        result.supply_type = "interstate"
        result.igst_applicable = True
        return result
    elif (cgst > ZERO or sgst > ZERO) and igst == ZERO:
        result.is_intrastate = True
        result.supply_type = "intrastate"
        result.igst_applicable = False
        return result

    # Method 3: Use place_of_supply if available
    if place_of_supply and supplier_state:
        if place_of_supply != supplier_state:
            result.is_interstate = True
            result.supply_type = "interstate"
            result.igst_applicable = True
        else:
            result.is_intrastate = True
            result.supply_type = "intrastate"
        return result

    # Cannot determine -- flag for CA review
    result.supply_type = "unknown"
    result.requires_ca_review = True
    result.review_reasons.append(
        "Cannot determine interstate/intrastate -- insufficient data"
    )
    return result


def _detect_rcm(
    result: ClassificationResult,
    gstin_supplier: str | None,
    hsn_sac_codes: list[str] | None,
    description: str | None,
    place_of_supply: str | None,
) -> ClassificationResult:
    """
    Detect Reverse Charge Mechanism applicability.

    RULE 6: Must cover all 5 categories:
      1. GTA (SAC 9965, 9967)
      2. Legal services (SAC 9982)
      3. Security services (SAC 9985)
      4. Import of services (place of supply outside India)
      5. Unregistered vendor (no GSTIN)
    """

    # Check 1-3: SAC code based RCM detection
    if hsn_sac_codes:
        for code in hsn_sac_codes:
            # Check first 4 digits against RCM SAC codes
            code_prefix = code[:4]
            if code_prefix in RCM_SAC_CODES:
                rcm_info = RCM_SAC_CODES[code_prefix]
                result.rcm_applicable = True
                result.rcm_category = rcm_info["category"]
                result.rcm_reference = rcm_info["reference"]
                result.rcm_note = rcm_info["note"]
                result.requires_ca_review = True
                result.review_reasons.append(
                    f"RCM applicable: {rcm_info['category']} (SAC {code_prefix})"
                )
                return result

    # Check 1-3 fallback: keyword-based RCM detection
    desc_lower = (description or "").lower()
    if desc_lower:
        for _key, rcm_info in RCM_KEYWORDS.items():
            for keyword in rcm_info["keywords"]:
                if keyword in desc_lower:
                    result.rcm_applicable = True
                    result.rcm_category = rcm_info["category"]
                    result.rcm_reference = rcm_info["reference"]
                    result.rcm_note = rcm_info["note"]
                    result.requires_ca_review = True
                    result.review_reasons.append(
                        f"RCM applicable: {rcm_info['category']} "
                        f"(keyword: '{keyword}')"
                    )
                    return result

    # Check 4: Import of services
    if place_of_supply and place_of_supply not in INDIAN_STATE_CODES:
        result.rcm_applicable = True
        result.rcm_category = "import"
        result.rcm_reference = "IGST Act Section 5(3)"
        result.rcm_note = (
            "Place of supply is outside India -- import of services under RCM"
        )
        result.requires_ca_review = True
        result.review_reasons.append("RCM applicable: import of services")
        return result

    # Check 5: Unregistered vendor
    if not _is_valid_gstin_format(gstin_supplier):
        result.rcm_applicable = True
        result.rcm_category = "unregistered"
        result.rcm_reference = "CGST Act Section 9(4)"
        result.rcm_note = (
            "Supplier GSTIN missing/invalid -- possible unregistered vendor. "
            "RCM under Section 9(4) may apply for specified categories. "
            "CA must confirm applicability."
        )
        result.requires_ca_review = True
        result.review_reasons.append(
            "RCM applicable: unregistered vendor (no valid GSTIN)"
        )
        return result

    return result


def _is_valid_gstin_format(gstin: str | None) -> bool:
    """
    Quick format check for GSTIN (15-char alphanumeric).
    Does NOT verify checksum -- use gstin_validator for full validation.
    """
    if not gstin:
        return False
    import re
    pattern = re.compile(
        r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]$"
    )
    return bool(pattern.match(gstin.upper()))


def _extract_state_code(gstin: str | None) -> str | None:
    """Extract 2-digit state code from GSTIN."""
    if gstin and len(gstin) >= 2 and gstin[:2].isdigit():
        return gstin[:2]
    return None
