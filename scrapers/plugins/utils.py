import re
import time

import httpx
from bs4 import BeautifulSoup

from scrapers.core.blogger_resolver import resolve_blogger_streams
from utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

_BG_MP4_IFRAME_RE = re.compile(r'<iframe[^>]+src=["\']([^"\']*bg\.mp4[^"\']*)["\']', re.I)
_TOKEN_RE = re.compile(r"blogger\.com/video\.g\?token=([^&\"'\s]+)")


def http_get_with_retry(
    url: str,
    *,
    headers: dict | None = None,
    timeout: float = 30,
    follow_redirects: bool = True,
    max_retries: int = 3,
    backoff_base: float = 0.5,
    client: httpx.Client | None = None,
) -> httpx.Response:
    """Perform an HTTP GET with retry/backoff for transient failures.

    Retries on rate limiting (HTTP 429), server errors (>= 500), timeouts,
    and transport/connection errors, up to ``max_retries`` times. For a 429
    response the ``Retry-After`` header (in seconds) is honored when present;
    otherwise exponential backoff (``backoff_base * 2 ** attempt``) is used.
    Other 4xx errors (except 429) are raised immediately without retrying.

    On success the response is returned with ``raise_for_status()`` already
    verified. When all retries are exhausted the last error is re-raised.

    Args:
        url: The URL to fetch.
        headers: Optional request headers.
        timeout: Per-request timeout in seconds.
        follow_redirects: Whether to follow redirects.
        max_retries: Maximum number of retry attempts after the first request.
        backoff_base: Base seconds for exponential backoff.
        client: Optional ``httpx.Client`` to use (mainly for testability).

    Returns:
        The successful ``httpx.Response`` (status verified via raise_for_status).
    """

    def _do_get() -> httpx.Response:
        if client is not None:
            return client.get(
                url, headers=headers, timeout=timeout, follow_redirects=follow_redirects
            )
        return httpx.get(url, headers=headers, timeout=timeout, follow_redirects=follow_redirects)

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = _do_get()
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            if attempt >= max_retries:
                raise
            delay = backoff_base * 2**attempt
            logger.debug(
                f"http_get_with_retry retry {attempt + 1}/{max_retries} for {url} "
                f"(reason: {type(exc).__name__}), sleeping {delay:.2f}s"
            )
            time.sleep(delay)
            continue

        status = getattr(response, "status_code", None)
        if isinstance(status, int) and (status == 429 or status >= 500):
            last_exc = None
            if attempt >= max_retries:
                response.raise_for_status()
                return response
            if status == 429 and (retry_after := response.headers.get("Retry-After")):
                try:
                    delay = float(
                        retry_after
                    )  # integer seconds; RFC 7231 date format raises ValueError → falls through to backoff
                except ValueError:
                    delay = backoff_base * 2**attempt
            else:
                delay = backoff_base * 2**attempt
            logger.debug(
                f"http_get_with_retry retry {attempt + 1}/{max_retries} for {url} "
                f"(reason: HTTP {status}), sleeping {delay:.2f}s"
            )
            time.sleep(delay)
            continue

        # Success or a non-retryable 4xx: let raise_for_status decide.
        response.raise_for_status()
        return response

    # Should not reach here, but re-raise last error defensively.
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("http_get_with_retry exhausted retries without a response")


def append_player_source(container: list, source: str) -> bool:
    """Append a candidate playback URL, skipping duplicates."""
    if source in container:
        return False
    container.append(source)
    return True


def store_player_source(container: list, event, source: str) -> bool:
    """Append a candidate playback URL.

    ``event`` is kept for plugin API compatibility; extraction no longer
    stops after the first URL so playback can try every candidate in order.
    """
    _ = event
    return append_player_source(container, source)


def extract_anivideo_hls(html: str) -> str | None:
    """Extract the direct HLS URL from an anivideo videohls.php `d=` parameter."""
    from urllib.parse import unquote

    match = re.search(r"https://api\.anivideo\.net/videohls\.php\?d=([^\"'<>&\s]+)", html)
    if not match:
        return None
    base = unquote(match.group(1).split("&")[0])
    if base.endswith(".m3u8"):
        return base
    if base.endswith(".mp4"):
        return f"{base}/index.m3u8"
    return base


def extract_blogger_from_bg_mp4(
    html: str,
    episode_url: str,
    site_referer: str,
    headers: dict | None = None,
    timeout: float = 30,
) -> list[str]:
    """Follow bg.mp4 redirector iframes and resolve Blogger streams (HD first)."""
    request_headers = headers or DEFAULT_HEADERS
    iframe_urls = _BG_MP4_IFRAME_RE.findall(html)
    if not iframe_urls:
        soup = BeautifulSoup(html, "html.parser")
        iframe_urls = [
            src
            for iframe in soup.select("iframe.metaframe, iframe")
            if (src := iframe.get("src")) and "bg.mp4" in src
        ]

    for iframe_url in iframe_urls:
        try:
            hop = httpx.get(
                iframe_url,
                headers={**request_headers, "Referer": episode_url},
                timeout=timeout,
                follow_redirects=False,
            )
            location = hop.headers.get("location", "")
            if not location:
                continue
            if location.startswith("/"):
                from urllib.parse import urlparse

                parsed = urlparse(iframe_url)
                location = f"{parsed.scheme}://{parsed.netloc}{location}"

            provider = httpx.get(
                location,
                headers={**request_headers, "Referer": site_referer},
                timeout=timeout,
                follow_redirects=True,
            )
            provider.raise_for_status()
            token_match = _TOKEN_RE.search(provider.text)
            if not token_match:
                continue
            return resolve_blogger_streams(token_match.group(1))
        except Exception:
            continue
    return []


def load_plugin(plugin_cls, register) -> None:
    """Register an anime plugin with the caller-supplied registration callback."""
    register(plugin_cls())
