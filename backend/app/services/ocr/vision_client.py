"""
VyapaarBandhu -- Google Vision API Async Wrapper (Primary OCR)
Uses asyncio.to_thread to avoid blocking the event loop.

Falls back to Tesseract if:
  - Vision API credentials are not configured
  - Vision API returns an error
  - Vision API confidence is below threshold
"""
from __future__ import annotations

import asyncio
import io

import structlog

from app.config import settings
from app.services.ocr.tesseract import RawOCRResult

logger = structlog.get_logger()


async def vision_extract(image_bytes: bytes) -> RawOCRResult:
    """
    Extract text from an invoice image using Google Cloud Vision API.

    Uses document_text_detection (optimized for dense text like invoices)
    rather than text_detection (optimized for sparse text like signs).

    Returns RawOCRResult with raw text and overall confidence score.
    Raises Exception if Vision API is not configured or returns an error.
    """
    result = await asyncio.to_thread(_sync_vision_extract, image_bytes)
    return result


def _sync_vision_extract(image_bytes: bytes) -> RawOCRResult:
    """
    Synchronous Vision API call -- wrapped by vision_extract via to_thread.
    """
    from google.cloud import vision

    client = vision.ImageAnnotatorClient()

    image = vision.Image(content=image_bytes)

    # document_text_detection is better for structured documents (invoices)
    response = client.document_text_detection(image=image)

    if response.error.message:
        raise RuntimeError(
            f"Google Vision API error: {response.error.message}"
        )

    full_text = ""
    overall_confidence = 0.0

    if response.full_text_annotation:
        full_text = response.full_text_annotation.text

        # Calculate average confidence across all pages/blocks/paragraphs/words
        confidences = []
        for page in response.full_text_annotation.pages:
            for block in page.blocks:
                confidences.append(block.confidence)

        if confidences:
            overall_confidence = sum(confidences) / len(confidences)

    if not full_text:
        raise RuntimeError("Google Vision API returned empty text")

    logger.info(
        "ocr.vision.complete",
        text_length=len(full_text),
        confidence=round(overall_confidence, 4),
    )

    return RawOCRResult(
        text=full_text,
        overall_confidence=round(overall_confidence, 4),
        provider="google_vision",
    )


def is_vision_available() -> bool:
    """
    Check if Google Vision API credentials are configured.
    Returns False if GOOGLE_APPLICATION_CREDENTIALS env var is not set
    or the google-cloud-vision package is not installed.
    """
    import os

    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return False

    try:
        from google.cloud import vision  # noqa: F401
        return True
    except ImportError:
        return False
