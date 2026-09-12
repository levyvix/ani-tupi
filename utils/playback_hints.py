"""MPV playback hints for source-specific stream URLs."""

import re

_ANIDRIVE_TOKEN_RE = re.compile(r"https://anidrive\.click/token/[A-Za-z0-9_-]+(?:\?prime)?")

_IMAGESKILL_MARKERS = ("imagesskill.com", "cdn.imagesskill.com")
_ANIVIDEO_REFERER = "https://api.anivideo.net/"
_DEFAULT_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0"

# Cache episode-page -> token referrer so retries don't refetch.
_anidrive_referrer_cache: dict[str, str] = {}


def is_imagesskill_hls(url: str) -> bool:
    """True when URL is an imagesskill HLS playlist."""
    lower = url.lower()
    return any(marker in lower for marker in _IMAGESKILL_MARKERS) and (
        ".m3u8" in lower or "/index.m3u8" in lower
    )


def is_anidrive_hls(url: str) -> bool:
    """True when URL is an AniDrive HLS playlist (static.anidrive.click)."""
    lower = url.lower()
    return "static.anidrive.click" in lower and ".m3u8" in lower


def extract_anidrive_token(html: str) -> str | None:
    """Return the first anidrive token embed URL found in *html*, if any."""
    match = _ANIDRIVE_TOKEN_RE.search(html)
    return match.group(0) if match else None


def resolve_anidrive_referrer(video_url: str, episode_referrer: str | None) -> str | None:
    """Resolve the Referer AniDrive HLS requires.

    ``static.anidrive.click`` answers 403 unless the request carries the token
    embed URL (``https://anidrive.click/token/...``) as Referer — the episode
    page (``anroll.io/NNN``, ``animesonline.io/NNN``) is rejected. When the
    supplied referrer is already a token URL it is returned as-is; when it is
    an episode page, the page is fetched once (cached) to extract the token.

    Fails open: any fetch/parse problem returns *episode_referrer* unchanged.
    """
    if not is_anidrive_hls(video_url):
        return episode_referrer
    if not episode_referrer:
        return episode_referrer
    if "anidrive.click/token/" in episode_referrer:
        return episode_referrer
    cached = _anidrive_referrer_cache.get(episode_referrer)
    if cached:
        return cached
    try:
        import httpx

        response = httpx.get(
            episode_referrer,
            headers={"User-Agent": _DEFAULT_UA, "Accept-Language": "pt-BR,pt;q=0.9"},
            timeout=8,
            follow_redirects=True,
        )
        response.raise_for_status()
        token = extract_anidrive_token(response.text)
        if token:
            _anidrive_referrer_cache[episode_referrer] = token
            return token
    except Exception:
        pass
    return episode_referrer


def _lavf_headers(referrer: str) -> str:
    header_block = f"Referer: {referrer}\\r\\nUser-Agent: {_DEFAULT_UA}\\r\\n"
    return f"headers={header_block}"


def resolve_mpv_stream_options(url: str, referrer: str | None) -> tuple[str | None, str | None]:
    """Return MPV ``(referrer, demuxer_lavf_o)`` tuned for the stream URL.

    imagesskill HLS uses Referer-gated CDN access and serves segments as ``.webp``
    files. FFmpeg rejects those unless ``extension_picky=0`` and the anivideo
    Referer is forwarded to every segment request.

    AniDrive HLS (``static.anidrive.click``) is Referer-gated on the token embed
    URL. The episode page alone gets HTTP 403, so the token is resolved here and
    forwarded to every segment request as well.
    """
    if is_imagesskill_hls(url):
        effective_referrer = _ANIVIDEO_REFERER
        header_block = f"Referer: {effective_referrer}\\r\\nUser-Agent: {_DEFAULT_UA}\\r\\n"
        demuxer_lavf_o = f"extension_picky=0,headers={header_block}"
        return effective_referrer, demuxer_lavf_o

    if is_anidrive_hls(url):
        effective_referrer = resolve_anidrive_referrer(url, referrer)
        if effective_referrer and "anidrive.click/token/" in effective_referrer:
            demuxer_lavf_o = _lavf_headers(effective_referrer)
            return effective_referrer, demuxer_lavf_o
        return referrer, None

    return referrer, None
