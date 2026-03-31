"""
VyapaarBandhu -- GSTIN to State Mapper
Determines inter-state vs intra-state transactions from GSTIN first 2 digits.

CRITICAL: This file must never import any ML/AI library.
Reference: IGST Act Section 5 -- Inter-state supply.
"""
from __future__ import annotations

STATE_CODES: dict[str, str] = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana",
    "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
    "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra & Nagar Haveli and Daman & Diu", "27": "Maharashtra",
    "28": "Andhra Pradesh", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu",
    "34": "Puducherry", "35": "Andaman & Nicobar Islands",
    "36": "Telangana", "37": "Andhra Pradesh (new)",
    "38": "Ladakh", "97": "Other Territory",
}


def get_state_from_gstin(gstin: str | None) -> str | None:
    """Extract 2-digit state code from GSTIN. Returns None if invalid."""
    if not gstin or len(gstin) < 2:
        return None
    code = gstin[:2]
    return code if code in STATE_CODES else None


def get_state_name(state_code: str | None) -> str | None:
    """Get state name from 2-digit code."""
    if not state_code:
        return None
    return STATE_CODES.get(state_code)


def is_interstate_transaction(
    seller_gstin: str | None,
    buyer_gstin: str | None,
) -> bool:
    """
    Determine if a transaction is inter-state based on GSTIN state codes.

    Inter-state: seller state code != buyer state code -> IGST applies
    Intra-state: seller state code == buyer state code -> CGST + SGST applies

    If either GSTIN is missing, defaults to intra-state (conservative).
    Reference: IGST Act Section 7(1) — Inter-state supply definition.
    """
    seller_state = get_state_from_gstin(seller_gstin)
    buyer_state = get_state_from_gstin(buyer_gstin)

    if seller_state is None or buyer_state is None:
        # Cannot determine — default to intra-state (conservative)
        return False

    return seller_state != buyer_state
