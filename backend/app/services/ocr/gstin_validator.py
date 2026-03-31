"""
VyapaarBandhu -- GSTIN Validator with Modulo 36 Checksum
Refactored from the original gstin_validator.py to use dataclass output.

Handles OCR confusion pairs (I/1, O/0, S/5, B/8, Z/2, G/6, A/4)
and attempts single-character auto-correction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import product

from app.services.compliance.gstin_state_mapper import STATE_CODES

GSTIN_CHAR_MAP = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")

OCR_CONFUSIONS: dict[str, list[str]] = {
    "1": ["I", "L"], "I": ["1", "L"],
    "0": ["O", "D"], "O": ["0", "D"],
    "5": ["S"], "S": ["5"],
    "8": ["B"], "B": ["8"],
    "2": ["Z"], "Z": ["2"],
    "6": ["G"], "G": ["6"],
    "4": ["A"], "A": ["4"],
    "D": ["0", "O"],
    "L": ["1", "I"],
}


@dataclass
class GSTINValidationResult:
    corrected: str
    is_valid: bool
    was_corrected: bool
    original: str
    state: str | None = None
    state_code: str | None = None
    pan: str | None = None
    ambiguous_candidates: list[str] = field(default_factory=list)
    needs_ca_review: bool = False
    corrections: list[str] = field(default_factory=list)


def calculate_gstin_checksum(gstin_14: str) -> str:
    """
    Calculate Modulo 36 checksum for first 14 chars of GSTIN.

    Per GST specification: character set is 0-9 then A-Z (36 chars).
    Odd positions (1-indexed) multiplied by 1, even by 2.
    If product >= 36, reduce by (product // 36) + (product % 36).
    Checksum = CHARSET[36 - (total % 36)], or CHARSET[0] if total % 36 == 0.
    """
    total = 0
    for i, char in enumerate(gstin_14.upper()):
        if char not in GSTIN_CHAR_MAP:
            return "?"
        val = GSTIN_CHAR_MAP.index(char)
        factor = 2 if (i + 1) % 2 == 0 else 1
        p = val * factor
        if p >= 36:
            p = (p // 36) + (p % 36)
        total += p
    remainder = total % 36
    return GSTIN_CHAR_MAP[0] if remainder == 0 else GSTIN_CHAR_MAP[36 - remainder]


def _verify_checksum(gstin: str) -> bool:
    if len(gstin) != 15:
        return False
    try:
        return gstin[14] == calculate_gstin_checksum(gstin[:14])
    except Exception:
        return False


def validate_and_correct_gstin(raw: str) -> GSTINValidationResult:
    """
    Validate GSTIN with Modulo 36 checksum. Attempt auto-correction
    for common OCR confusion pairs (single-character substitutions).

    Returns GSTINValidationResult with corrected value and metadata.
    """
    if not raw:
        return GSTINValidationResult(
            corrected="", is_valid=False, was_corrected=False, original=""
        )

    gstin = raw.upper().strip().replace(" ", "")

    if len(gstin) != 15:
        return GSTINValidationResult(
            corrected=gstin, is_valid=False, was_corrected=False, original=raw
        )

    # Check if already valid
    state_code = gstin[:2]
    if _verify_checksum(gstin) and state_code in STATE_CODES:
        return GSTINValidationResult(
            corrected=gstin,
            is_valid=True,
            was_corrected=False,
            original=raw,
            state=STATE_CODES.get(state_code),
            state_code=state_code,
            pan=gstin[2:12],
        )

    # Try single-character substitutions from OCR confusion pairs
    confused_positions = []
    for i, char in enumerate(gstin):
        if char in OCR_CONFUSIONS:
            confused_positions.append((i, [char] + OCR_CONFUSIONS[char]))

    if not confused_positions:
        return GSTINValidationResult(
            corrected=gstin, is_valid=False, was_corrected=False, original=raw
        )

    # Limit search space to prevent combinatorial explosion
    confused_positions = confused_positions[:8]
    positions = [p[0] for p in confused_positions]
    options = [p[1] for p in confused_positions]
    originals = [gstin[p] for p in positions]

    candidates = []
    for combo in product(*options):
        candidate = list(gstin)
        for pos, char in zip(positions, combo):
            candidate[pos] = char
        c = "".join(candidate)
        if len(c) != 15:
            continue
        sc = c[:2]
        if sc not in STATE_CODES:
            continue
        if not GSTIN_PATTERN.match(c):
            continue
        if _verify_checksum(c):
            corrections = [
                f"pos {p + 1}: '{o}'->'{n}'"
                for p, o, n in zip(positions, originals, combo)
                if o != n
            ]
            if corrections:  # Only add if actually changed
                candidates.append((c, corrections))

    if len(candidates) == 1:
        corrected, corrections = candidates[0]
        sc = corrected[:2]
        return GSTINValidationResult(
            corrected=corrected,
            is_valid=True,
            was_corrected=True,
            original=raw,
            state=STATE_CODES.get(sc),
            state_code=sc,
            pan=corrected[2:12],
            corrections=corrections,
        )
    elif len(candidates) > 1:
        # Ambiguous — multiple valid corrections possible
        return GSTINValidationResult(
            corrected=gstin,
            is_valid=False,
            was_corrected=False,
            original=raw,
            ambiguous_candidates=[c[0] for c in candidates],
            needs_ca_review=True,
        )

    return GSTINValidationResult(
        corrected=gstin, is_valid=False, was_corrected=False, original=raw
    )
