"""
VyapaarBandhu -- Invoice Deduplication
SHA-256 hash of (seller_gstin + invoice_number + client_id) prevents duplicate invoices.
"""
from __future__ import annotations

import hashlib
import uuid


def compute_dedup_hash(
    seller_gstin: str | None,
    invoice_number: str | None,
    client_id: uuid.UUID,
    fallback_key: str | None = None,
) -> str:
    """
    Compute deterministic deduplication hash for an invoice.
    Uses SHA-256 of normalised (seller_gstin || invoice_number || client_id).

    If both seller_gstin and invoice_number are None/UNKNOWN and a
    fallback_key is provided (e.g., S3 key), it is included to ensure
    uniqueness for newly uploaded invoices before OCR extraction.

    Normalisation:
    - GSTIN uppercased, whitespace stripped
    - Invoice number uppercased, whitespace stripped
    - Client ID as lowercase hex string

    Returns 64-char hex string.
    """
    gstin = (seller_gstin or "UNKNOWN").upper().strip()
    inv_no = (invoice_number or "UNKNOWN").upper().strip()
    cid = str(client_id).lower()

    payload = f"{gstin}|{inv_no}|{cid}"
    if fallback_key and gstin == "UNKNOWN" and inv_no == "UNKNOWN":
        payload = f"{payload}|{fallback_key}"

    return hashlib.sha256(payload.encode()).hexdigest()
