"""
VyapaarBandhu -- Supplier Resolver
Match supplier GSTIN to known vendor in the database.

Used to:
  1. Link invoices to known suppliers for recurring analysis
  2. Flag new/unknown suppliers for CA review
  3. Detect supplier name mismatches (possible fraud indicator)
"""
from __future__ import annotations

import uuid

import structlog
from dataclasses import dataclass
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


@dataclass
class SupplierMatch:
    """Result of supplier GSTIN resolution."""
    found: bool = False
    supplier_name: str | None = None
    supplier_id: uuid.UUID | None = None
    name_mismatch: bool = False
    is_new_supplier: bool = True


async def resolve_supplier(
    db: AsyncSession,
    ca_id: uuid.UUID,
    gstin: str | None,
    extracted_name: str | None,
) -> SupplierMatch:
    """
    Attempt to match a supplier GSTIN against invoices previously
    processed for this CA. Returns match info including whether the
    supplier name on the new invoice differs from the one on file.

    This is NOT a full vendor master -- that comes in Phase 8.
    For now, we just check previous invoices for the same supplier GSTIN.
    """
    if not gstin:
        return SupplierMatch(is_new_supplier=True)

    # Look up previous invoices with the same supplier GSTIN for this CA
    result = await db.execute(
        select(
            text("seller_gstin"),
            text("seller_name"),
        ).select_from(text("vyapaar.invoices")).where(
            text("ca_id = :ca_id AND seller_gstin = :gstin AND status != 'ca_rejected'")
        ).params(ca_id=str(ca_id), gstin=gstin).limit(1)
    )

    row = result.first()
    if not row:
        logger.info(
            "supplier.new",
            gstin=gstin,
            ca_id=str(ca_id),
        )
        return SupplierMatch(is_new_supplier=True)

    existing_name = row[1]  # seller_name from previous invoice

    name_mismatch = False
    if extracted_name and existing_name:
        # Simple comparison -- normalize and check
        if _normalize_name(extracted_name) != _normalize_name(existing_name):
            name_mismatch = True
            logger.warning(
                "supplier.name_mismatch",
                gstin=gstin,
                previous_name=existing_name,
                new_name=extracted_name,
            )

    return SupplierMatch(
        found=True,
        supplier_name=existing_name,
        name_mismatch=name_mismatch,
        is_new_supplier=False,
    )


def _normalize_name(name: str) -> str:
    """Normalize business name for comparison."""
    import re
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in ["pvt", "ltd", "limited", "private", "llp", "inc", "corp"]:
        name = name.replace(suffix, "")
    # Remove punctuation and extra spaces
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name
