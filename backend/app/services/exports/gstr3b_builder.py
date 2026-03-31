"""
VyapaarBandhu — GSTR-3B JSON Builder
Builds GSTR-3B JSON in exact GST portal (GSTN) format.

CRITICAL: This file must never import any ML/AI library.
CRITICAL: All amounts are strings with exactly 2 decimal places.
CRITICAL: Never use float or round() for GSTR-3B amounts.

Uses itc_calculator.py output for confirmed/rejected ITC.
Pure deterministic mapping -- no LLM calls.

Reference: GSTN GSTR-3B JSON schema specification.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

import structlog

logger = structlog.get_logger()

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")


def _fmt(value: Decimal | str | None) -> str:
    """
    Format a value as GSTR-3B amount string: exactly 2 decimal places.
    Never returns float. Always returns string like "0.00".
    """
    if value is None:
        return "0.00"
    d = Decimal(str(value))
    return str(d.quantize(TWO_PLACES, rounding=ROUND_HALF_UP))


@dataclass
class GSTR3BInput:
    """
    Input data for GSTR-3B JSON generation.
    All monetary fields must be Decimal, never float.
    """
    gstin: str
    period: str  # MM-YYYY format

    # Confirmed ITC (from itc_calculator)
    cgst_confirmed: Decimal = ZERO
    sgst_confirmed: Decimal = ZERO
    igst_confirmed: Decimal = ZERO

    # Rejected/reversed ITC
    cgst_rejected: Decimal = ZERO
    sgst_rejected: Decimal = ZERO
    igst_rejected: Decimal = ZERO

    # RCM
    rcm_taxable: Decimal = ZERO
    rcm_cgst: Decimal = ZERO
    rcm_sgst: Decimal = ZERO
    rcm_igst: Decimal = ZERO


def build_gstr3b_json(data: GSTR3BInput) -> dict:
    """
    Build GSTR-3B JSON matching the official GSTN portal schema.

    All amounts are strings with exactly 2 decimal places.
    Uses Decimal with ROUND_HALF_UP throughout. Zero float.

    Field mapping:
        itc_avl "OTH" = confirmed ITC from itc_calculator
        itc_rev "OTH" = rejected ITC from itc_calculator
        itc_net = itc_avl totals minus itc_rev totals
        isup_rev = RCM liability (taxable + tax amounts)

    Returns a dict matching GSTN GSTR-3B JSON schema.
    """
    # Convert MM-YYYY to MMYYYY for GSTN ret_period
    parts = data.period.split("-")
    ret_period = f"{parts[0]}{parts[1]}"

    # ITC available -- confirmed amounts go in "OTH" type
    itc_avl_oth = _make_itc_row(
        "OTH",
        samt=data.sgst_confirmed,
        camt=data.cgst_confirmed,
        iamt=data.igst_confirmed,
    )

    # ITC reversed -- rejected amounts go in "OTH" type
    itc_rev_oth = _make_itc_row(
        "OTH",
        samt=data.sgst_rejected,
        camt=data.cgst_rejected,
        iamt=data.igst_rejected,
    )

    # ITC net = available minus reversed (clamped to zero -- negative ITC net is invalid)
    net_samt = max(data.sgst_confirmed - data.sgst_rejected, ZERO)
    net_camt = max(data.cgst_confirmed - data.cgst_rejected, ZERO)
    net_iamt = max(data.igst_confirmed - data.igst_rejected, ZERO)

    # Inward supply details
    intra_total = data.cgst_confirmed + data.sgst_confirmed
    inter_total = data.igst_confirmed

    gstr3b = {
        "gstin": data.gstin or "",
        "ret_period": ret_period,
        "inward_sup": {
            "isup_details": [
                {
                    "ty": "GST",
                    "inter": _fmt(inter_total),
                    "intra": _fmt(intra_total),
                },
                {
                    "ty": "NONGST",
                    "inter": "0.00",
                    "intra": "0.00",
                },
            ]
        },
        "itc_elg": {
            "itc_avl": [
                _make_itc_row("IMPG"),
                _make_itc_row("IMPS"),
                _make_itc_row("ISRC"),
                _make_itc_row("ISD"),
                itc_avl_oth,
            ],
            "itc_rev": [
                _make_itc_row("RUL"),
                itc_rev_oth,
            ],
            "itc_net": {
                "samt": _fmt(net_samt),
                "camt": _fmt(net_camt),
                "iamt": _fmt(net_iamt),
                "csamt": "0.00",
            },
            "itc_inelg": [
                _make_itc_row("RUL"),
                _make_itc_row("OTH"),
            ],
        },
        "sup_details": {
            "osup_det": {
                "txval": "0.00",
                "iamt": "0.00",
                "camt": "0.00",
                "samt": "0.00",
                "csamt": "0.00",
            },
            "osup_zero": {
                "txval": "0.00",
                "iamt": "0.00",
                "csamt": "0.00",
            },
            "osup_nil_exmp": {"txval": "0.00"},
            "isup_rev": {
                "txval": _fmt(data.rcm_taxable),
                "iamt": _fmt(data.rcm_igst),
                "camt": _fmt(data.rcm_cgst),
                "samt": _fmt(data.rcm_sgst),
                "csamt": "0.00",
            },
            "osup_nongst": {"txval": "0.00"},
        },
        "intr_ltfee": {
            "intr_details": {
                "camt": "0.00",
                "iamt": "0.00",
                "samt": "0.00",
            }
        },
    }

    logger.info(
        "export.gstr3b.built",
        gstin=data.gstin[:5] + "XXXXX" if len(data.gstin) >= 5 else "N/A",
        period=ret_period,
    )

    return gstr3b


def _make_itc_row(
    ty: str,
    samt: Decimal = ZERO,
    camt: Decimal = ZERO,
    iamt: Decimal = ZERO,
    csamt: Decimal = ZERO,
) -> dict:
    """Create an ITC row dict. All amounts formatted as GSTR-3B strings."""
    return {
        "ty": ty,
        "samt": _fmt(samt),
        "camt": _fmt(camt),
        "iamt": _fmt(iamt),
        "csamt": _fmt(csamt),
    }
