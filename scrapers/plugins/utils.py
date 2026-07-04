import re

import httpx
from bs4 import BeautifulSoup

from scrapers.core.blogger_resolver import resolve_blogger_streams

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

_BG_MP4_IFRAME_RE = re.compile(r'<iframe[^>]+src=["\']([^"\']*bg\.mp4[^"\']*)["\']', re.I)
_TOKEN_RE = re.compile(r"blogger\.com/video\.g\?token=([^&\"'\s]+)")


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
    """Register an anime plugin."""
    register(plugin_cls())
