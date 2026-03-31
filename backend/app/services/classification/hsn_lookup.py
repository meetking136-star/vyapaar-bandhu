"""
VyapaarBandhu -- HSN/SAC Code to Tax Rate Mapping (Static Table)

HSN (Harmonized System of Nomenclature) codes for goods.
SAC (Services Accounting Code) codes for services.

Rates effective 2026-03-31. Source: CBIC notifications.
This is a subset covering the most common SME invoice categories.
Full HSN table has 20,000+ entries -- loaded from config in Phase 8.

RULE 1: No AI/LLM. Static lookup only.
RULE 3: All rates are Decimal.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class HSNEntry:
    code: str
    description: str
    gst_rate: Decimal  # percentage (e.g., 18.00 = 18%)
    category: str      # broad category for classification


# ── Common HSN codes for SME invoices ─────────────────────────────────
HSN_TABLE: dict[str, HSNEntry] = {
    # Electronics & IT
    "8471": HSNEntry("8471", "Computers and peripherals", Decimal("18.00"), "electronics"),
    "8473": HSNEntry("8473", "Computer parts and accessories", Decimal("18.00"), "electronics"),
    "8443": HSNEntry("8443", "Printers, copiers", Decimal("18.00"), "electronics"),
    "8528": HSNEntry("8528", "Monitors, projectors", Decimal("18.00"), "electronics"),

    # Office supplies
    "4820": HSNEntry("4820", "Registers, notebooks, stationery", Decimal("12.00"), "office_supplies"),
    "4802": HSNEntry("4802", "Paper for printing", Decimal("12.00"), "office_supplies"),
    "9403": HSNEntry("9403", "Office furniture", Decimal("18.00"), "office_supplies"),
    "9401": HSNEntry("9401", "Seats and chairs", Decimal("18.00"), "office_supplies"),

    # Raw materials
    "7204": HSNEntry("7204", "Ferrous waste and scrap", Decimal("18.00"), "raw_materials"),
    "7208": HSNEntry("7208", "Hot-rolled steel", Decimal("18.00"), "raw_materials"),
    "3901": HSNEntry("3901", "Polymers of ethylene", Decimal("18.00"), "raw_materials"),
    "5208": HSNEntry("5208", "Woven cotton fabrics", Decimal("5.00"), "raw_materials"),

    # Capital goods
    "8422": HSNEntry("8422", "Industrial machinery (packaging)", Decimal("18.00"), "capital_goods"),
    "8479": HSNEntry("8479", "Mechanical appliances", Decimal("18.00"), "capital_goods"),
    "8414": HSNEntry("8414", "Air pumps, compressors", Decimal("18.00"), "capital_goods"),

    # Food & beverages
    "2106": HSNEntry("2106", "Food preparations", Decimal("18.00"), "food"),
    "1905": HSNEntry("1905", "Bread, biscuits, cakes", Decimal("18.00"), "food"),
    "0902": HSNEntry("0902", "Tea", Decimal("5.00"), "food"),
    "0901": HSNEntry("0901", "Coffee", Decimal("5.00"), "food"),
    "2201": HSNEntry("2201", "Mineral water", Decimal("18.00"), "food"),

    # Clothing / textiles
    "6109": HSNEntry("6109", "T-shirts, knitted", Decimal("5.00"), "clothing"),
    "6203": HSNEntry("6203", "Men's suits, trousers", Decimal("12.00"), "clothing"),
    "6204": HSNEntry("6204", "Women's suits, dresses", Decimal("12.00"), "clothing"),

    # Health / pharma
    "3004": HSNEntry("3004", "Medicaments", Decimal("12.00"), "health"),
    "3005": HSNEntry("3005", "Bandages, first-aid", Decimal("18.00"), "health"),
    "9018": HSNEntry("9018", "Medical instruments", Decimal("12.00"), "health"),
}

# ── Common SAC codes for services ─────────────────────────────────────
SAC_TABLE: dict[str, HSNEntry] = {
    "9965": HSNEntry("9965", "GTA (Goods Transport Agency)", Decimal("5.00"), "transport"),
    "9967": HSNEntry("9967", "Supporting transport services", Decimal("18.00"), "transport"),
    "9971": HSNEntry("9971", "Financial services", Decimal("18.00"), "finance"),
    "9972": HSNEntry("9972", "Real estate services", Decimal("18.00"), "real_estate"),
    "9973": HSNEntry("9973", "Leasing/rental services", Decimal("18.00"), "rental"),
    "9982": HSNEntry("9982", "Legal services", Decimal("18.00"), "legal"),
    "9983": HSNEntry("9983", "Professional services", Decimal("18.00"), "professional"),
    "9985": HSNEntry("9985", "Security services", Decimal("18.00"), "security"),
    "9986": HSNEntry("9986", "IT and telecom services", Decimal("18.00"), "it_services"),
    "9988": HSNEntry("9988", "Manufacturing services", Decimal("18.00"), "manufacturing"),
    "9991": HSNEntry("9991", "Government services", Decimal("18.00"), "government"),
    "9992": HSNEntry("9992", "Education services", Decimal("18.00"), "education"),
    "9993": HSNEntry("9993", "Health services", Decimal("18.00"), "health"),
    "9995": HSNEntry("9995", "Recreational services", Decimal("18.00"), "recreation"),
    "9996": HSNEntry("9996", "Hotel and accommodation", Decimal("12.00"), "hospitality"),
    "9997": HSNEntry("9997", "Restaurant and catering", Decimal("5.00"), "food_service"),
}


def lookup_hsn(code: str) -> HSNEntry | None:
    """
    Look up an HSN code and return the entry with GST rate.
    Tries exact match first, then 4-digit prefix match.
    """
    if not code:
        return None

    # Exact match
    if code in HSN_TABLE:
        return HSN_TABLE[code]

    # 4-digit prefix match (HSN codes can be 4, 6, or 8 digits)
    prefix = code[:4]
    if prefix in HSN_TABLE:
        return HSN_TABLE[prefix]

    return None


def lookup_sac(code: str) -> HSNEntry | None:
    """Look up a SAC code and return the entry with GST rate."""
    if not code:
        return None

    if code in SAC_TABLE:
        return SAC_TABLE[code]

    prefix = code[:4]
    if prefix in SAC_TABLE:
        return SAC_TABLE[prefix]

    return None


def lookup_code(code: str) -> HSNEntry | None:
    """
    Look up either HSN or SAC code. Tries HSN first, then SAC.
    Returns None if not found in either table.
    """
    result = lookup_hsn(code)
    if result:
        return result
    return lookup_sac(code)
