"""MPV playback hints for source-specific stream URLs."""

_IMAGESKILL_MARKERS = ("imagesskill.com", "cdn.imagesskill.com")
_ANIVIDEO_REFERER = "https://api.anivideo.net/"
_DEFAULT_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0"


def is_imagesskill_hls(url: str) -> bool:
    """True when URL is an imagesskill HLS playlist."""
    lower = url.lower()
    return any(marker in lower for marker in _IMAGESKILL_MARKERS) and (
        ".m3u8" in lower or "/index.m3u8" in lower
    )


def resolve_mpv_stream_options(url: str, referrer: str | None) -> tuple[str | None, str | None]:
    """Return MPV ``(referrer, demuxer_lavf_o)`` tuned for the stream URL.

    imagesskill HLS uses Referer-gated CDN access and serves segments as ``.webp``
    files. FFmpeg rejects those unless ``extension_picky=0`` and the anivideo
    Referer is forwarded to every segment request.
    """
    if not is_imagesskill_hls(url):
        return referrer, None

    effective_referrer = _ANIVIDEO_REFERER
    header_block = f"Referer: {effective_referrer}\\r\\nUser-Agent: {_DEFAULT_UA}\\r\\n"
    demuxer_lavf_o = f"extension_picky=0,headers={header_block}"
    return effective_referrer, demuxer_lavf_o
