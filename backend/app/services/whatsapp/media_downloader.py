"""
VyapaarBandhu -- WhatsApp Media Downloader
Downloads invoice images from WhatsApp with strict 30-second timeout.

RULE 5: On timeout, caller should reset state to AWAITING_INVOICE_IMAGE
and ask the user to resend.
"""
from __future__ import annotations

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()

MEDIA_DOWNLOAD_TIMEOUT = 30  # seconds -- RULE 5
BASE_URL = f"https://graph.facebook.com/{settings.WA_API_VERSION}"


class MediaDownloadError(Exception):
    """Raised when media download fails or times out."""
    pass


class MediaDownloadTimeout(MediaDownloadError):
    """Raised specifically on timeout -- triggers resend prompt."""
    pass


async def download_whatsapp_media(media_id: str) -> bytes:
    """
    Download media from WhatsApp Cloud API.
    Two-step process: resolve media URL, then download bytes.

    Raises:
        MediaDownloadTimeout: if download exceeds 30 seconds
        MediaDownloadError: on any other failure

    Returns:
        Raw image bytes.
    """
    headers = {"Authorization": f"Bearer {settings.WA_ACCESS_TOKEN}"}

    try:
        async with httpx.AsyncClient(timeout=MEDIA_DOWNLOAD_TIMEOUT) as client:
            # Step 1: Resolve media URL from ID
            url_resp = await client.get(
                f"{BASE_URL}/{media_id}", headers=headers
            )
            if url_resp.status_code != 200:
                logger.error(
                    "media.url_resolve_failed",
                    media_id=media_id,
                    status=url_resp.status_code,
                )
                raise MediaDownloadError(
                    f"Failed to resolve media URL: HTTP {url_resp.status_code}"
                )

            media_url = url_resp.json().get("url")
            if not media_url:
                raise MediaDownloadError("No URL in media response")

            # Step 2: Download actual bytes
            dl_resp = await client.get(media_url, headers=headers)
            if dl_resp.status_code != 200:
                raise MediaDownloadError(
                    f"Media download failed: HTTP {dl_resp.status_code}"
                )

            logger.info(
                "media.downloaded",
                media_id=media_id,
                size=len(dl_resp.content),
            )
            return dl_resp.content

    except httpx.TimeoutException:
        logger.warning("media.download_timeout", media_id=media_id)
        raise MediaDownloadTimeout(
            f"Media download timed out after {MEDIA_DOWNLOAD_TIMEOUT}s"
        )
    except (MediaDownloadError, MediaDownloadTimeout):
        raise
    except Exception as exc:
        logger.error("media.download_error", media_id=media_id, error=str(exc))
        raise MediaDownloadError(f"Unexpected error: {exc}")
