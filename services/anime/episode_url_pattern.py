"""Episode URL pattern detection and derivation.

Optimizes episode navigation by detecting predictable CDN URL patterns
and deriving next/previous episode URLs without a full scraping round-trip.

Supported pattern: `/<ep>.mp4/` (1–3 digit episode number)
Example: https://cdn-s01.example.net/stream/y/<slug>/11.mp4/index.m3u8
"""

from utils.logging import get_logger
import re

from scrapers.plugins.utils import http_head_with_fallback

logger = get_logger(__name__)

_EPISODE_PATTERN = re.compile(r"/(\d{1,3})\.mp4/")


def detect_episode_pattern(url: str) -> dict | None:
    """Detect if URL contains a substitutable episode number.

    Args:
        url: Video URL to inspect.

    Returns:
        Dict with ``episode`` (int), ``padded`` (bool), ``width`` (int),
        ``match_start`` and ``match_end`` (indices of the digit group), or
        ``None`` if the pattern is not found.
    """
    match = _EPISODE_PATTERN.search(url)
    if not match:
        return None
    raw = match.group(1)
    padded = raw.startswith("0") and len(raw) > 1
    return {
        "episode": int(raw),
        "padded": padded,
        "width": len(raw) if padded else 0,
        "match_start": match.start(1),
        "match_end": match.end(1),
    }


def derive_episode_url(url: str, target_episode: int) -> str | None:
    """Derive URL for *target_episode* by substituting the episode number.

    Zero-padding is preserved: if the original number was ``08`` the derived
    number will be ``09``; if it was ``11`` (no padding) it becomes ``12``.

    Args:
        url: Current video URL containing the episode number.
        target_episode: Episode number to derive the URL for.

    Returns:
        New URL with the episode number replaced, or ``None`` if the pattern
        is not found in *url*.
    """
    info = detect_episode_pattern(url)
    if info is None:
        return None
    if info["padded"]:
        new_ep = str(target_episode).zfill(info["width"])
    else:
        new_ep = str(target_episode)
    return url[: info["match_start"]] + new_ep + url[info["match_end"] :]


def validate_episode_url(url: str, timeout: float = 5.0) -> bool:
    """Check whether *url* resolves to a valid episode via a HEAD request.

    Args:
        url: URL to validate.
        timeout: Request timeout in seconds.

    Returns:
        ``True`` if the server returns a 2xx status code, ``False`` otherwise.
    """
    logger.info(f"[URL-PATTERN] HEAD {url[:80]}{'...' if len(url) > 80 else ''}")
    try:
        response = http_head_with_fallback(
            url,
            timeout=timeout,
            follow_redirects=True,
        )
        logger.info(
            f"[URL-PATTERN] → {response.status_code} {'✅ HIT' if response.is_success else '❌ MISS'}"
        )
        return response.is_success
    except Exception as exc:
        logger.info(f"[URL-PATTERN] → ERROR: {exc}")
        logger.debug("validate_episode_url failed for %s: %s", url, exc)
        return False
