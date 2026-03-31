"""
VyapaarBandhu -- Image Preprocessor for OCR
Runs BEFORE any OCR engine call. WhatsApp-forwarded images are typically
compressed, rotated, and low-contrast -- this pipeline normalizes them.

Steps:
  1. Convert to grayscale
  2. Deskew (correct rotation up to +/-15 degrees)
  3. Binarize (Otsu threshold)
  4. Scale to minimum 300 DPI equivalent

Uses OpenCV (cv2) -- no ML models involved.
"""
from __future__ import annotations

import io

import cv2
import numpy as np
import structlog
from PIL import Image

logger = structlog.get_logger()

# Target DPI equivalent -- 300 DPI is the OCR sweet spot for printed text.
# Below this, Tesseract accuracy drops sharply; above it, diminishing returns.
MIN_TARGET_WIDTH = 2480  # ~300 DPI for A4 width (210mm)
MIN_TARGET_HEIGHT = 3508  # ~300 DPI for A4 height (297mm)


def preprocess_image(image_bytes: bytes) -> bytes:
    """
    Full preprocessing pipeline for invoice images.
    Returns processed image as PNG bytes (lossless for OCR).

    Steps run in order:
      1. Decode -> grayscale
      2. Deskew
      3. Binarize (Otsu)
      4. Scale to 300 DPI equivalent if undersized
    """
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    if img is None:
        logger.warning("preprocessor.decode_failed", size=len(image_bytes))
        return image_bytes  # return original if decode fails

    original_h, original_w = img.shape[:2]

    # Step 1: Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Step 2: Deskew
    gray = _deskew(gray)

    # Step 3: Binarize (Otsu)
    gray = _binarize(gray)

    # Step 4: Scale up if image is too small
    gray = _scale_to_min_dpi(gray)

    final_h, final_w = gray.shape[:2]
    logger.info(
        "preprocessor.complete",
        original_size=f"{original_w}x{original_h}",
        final_size=f"{final_w}x{final_h}",
    )

    # Encode as PNG (lossless) for maximum OCR accuracy
    success, encoded = cv2.imencode(".png", gray)
    if not success:
        logger.warning("preprocessor.encode_failed")
        return image_bytes

    return encoded.tobytes()


def _deskew(gray: np.ndarray) -> np.ndarray:
    """
    Correct rotation up to +/-15 degrees using Hough line detection.
    Small rotations from phone cameras are the primary cause of OCR errors
    on structured documents like invoices.
    """
    # Detect edges
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)

    # Detect lines
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=100, minLineLength=100, maxLineGap=10
    )

    if lines is None or len(lines) == 0:
        return gray

    # Calculate median angle from detected lines
    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        dx = x2 - x1
        dy = y2 - y1
        if abs(dx) < 1:
            continue
        angle = np.degrees(np.arctan2(dy, dx))
        # Only consider nearly-horizontal lines (within 15 degrees)
        if abs(angle) <= 15:
            angles.append(angle)

    if not angles:
        return gray

    median_angle = float(np.median(angles))

    # Skip if angle is negligible (less than 0.3 degrees)
    if abs(median_angle) < 0.3:
        return gray

    h, w = gray.shape[:2]
    center = (w // 2, h // 2)
    rotation_matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    rotated = cv2.warpAffine(
        gray, rotation_matrix, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )

    logger.info("preprocessor.deskew", angle=round(median_angle, 2))
    return rotated


def _binarize(gray: np.ndarray) -> np.ndarray:
    """
    Otsu binarization -- automatically finds the optimal threshold
    for separating text from background. Works well on printed invoices
    even with uneven lighting from phone cameras.
    """
    # Apply slight Gaussian blur to reduce noise before binarization
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def _scale_to_min_dpi(gray: np.ndarray) -> np.ndarray:
    """
    Scale image up to 300 DPI equivalent if it is too small.
    WhatsApp compresses images heavily -- a typical forwarded invoice
    might be 800x1200 which is ~100 DPI on A4. Scaling up to 300 DPI
    improves Tesseract word-level accuracy by 15-25% (empirical).
    """
    h, w = gray.shape[:2]

    # Calculate scale factor based on the smaller dimension ratio
    scale_w = MIN_TARGET_WIDTH / w if w < MIN_TARGET_WIDTH else 1.0
    scale_h = MIN_TARGET_HEIGHT / h if h < MIN_TARGET_HEIGHT else 1.0
    scale = min(scale_w, scale_h)

    # Cap upscaling at 3x to avoid excessive memory usage
    scale = min(scale, 3.0)

    if scale <= 1.0:
        return gray

    new_w = int(w * scale)
    new_h = int(h * scale)

    # INTER_CUBIC gives better results than INTER_LINEAR for upscaling text
    scaled = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    logger.info("preprocessor.scaled", factor=round(scale, 2))
    return scaled
