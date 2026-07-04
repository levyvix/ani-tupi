"""Resolve blogger.com video tokens to direct googlevideo.com streaming URLs.

Blogger video embeds serve MP4 content via Google's CDN. The actual URL
is fetched through the BloggerVideoPlayerUi batchexecute API.
"""

import json
import re

import httpx

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Accept-Language": "pt-BR,pt;q=0.9",
}
_TIMEOUT = 15

# Known Blogger/googlevideo itags (higher = better for the formats we see).
_ITAG_PRIORITY = {22: 720, 18: 360}


def _itag_from_stream(stream: object) -> int:
    """Extract itag number from a batchexecute stream entry."""
    if not isinstance(stream, list) or len(stream) < 2:
        return 0
    itags = stream[1]
    if isinstance(itags, list) and itags:
        return int(itags[0])
    url = stream[0] if isinstance(stream[0], str) else ""
    match = re.search(r"[?&]itag=(\d+)", url)
    return int(match.group(1)) if match else 0


def _parse_batchexecute_streams(inner: object) -> list[str]:
    """Return googlevideo URLs sorted best-quality first."""
    if not isinstance(inner, list) or len(inner) < 3:
        raise ValueError(f"Unexpected batchexecute inner shape: {inner!r}")

    streams = inner[2]
    if not isinstance(streams, list) or not streams:
        raise ValueError("No streams in batchexecute response")

    ranked: list[tuple[int, str]] = []
    for stream in streams:
        if not isinstance(stream, list) or not stream:
            continue
        url = stream[0]
        if not isinstance(url, str) or "googlevideo.com" not in url:
            continue
        itag = _itag_from_stream(stream)
        priority = _ITAG_PRIORITY.get(itag, itag)
        ranked.append((priority, url))

    if not ranked:
        raise ValueError("No googlevideo URLs in batchexecute streams")

    ranked.sort(key=lambda item: item[0], reverse=True)
    seen: set[str] = set()
    ordered: list[str] = []
    for _, url in ranked:
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def _fetch_batchexecute_inner(token: str) -> object:
    r = httpx.get(
        f"https://www.blogger.com/video.g?token={token}",
        headers=_HEADERS,
        timeout=_TIMEOUT,
        follow_redirects=True,
    )
    r.raise_for_status()

    fsid_m = re.search(r'"FdrFJe"\s*:\s*"(-?\d+)"', r.text)
    bl_m = re.search(r'"cfb2h"\s*:\s*"([^"]+)"', r.text)
    if not fsid_m or not bl_m:
        raise ValueError("Could not extract session parameters from blogger page")

    f_req = json.dumps([[["WcwnYd", json.dumps([token, None, 0]), None, "generic"]]])
    r2 = httpx.post(
        "https://www.blogger.com/_/BloggerVideoPlayerUi/data/batchexecute",
        params={
            "rpcids": "WcwnYd",
            "source-path": "/video.g",
            "f.sid": fsid_m.group(1),
            "bl": bl_m.group(1),
            "hl": "pt-BR",
            "_reqid": "1",
            "rt": "c",
        },
        data={"f.req": f_req},
        headers={
            **_HEADERS,
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "X-Same-Domain": "1",
            "Referer": f"https://www.blogger.com/video.g?token={token}",
        },
        timeout=_TIMEOUT,
    )
    r2.raise_for_status()

    json_line = next(
        (line.strip() for line in r2.text.split("\n") if line.strip().startswith("[[")),
        None,
    )
    if not json_line:
        raise ValueError("No JSON data in batchexecute response")

    outer = json.loads(json_line)
    if not (
        isinstance(outer, list) and outer and isinstance(outer[0], list) and len(outer[0]) >= 3
    ):
        raise ValueError(f"Unexpected batchexecute outer response: {outer!r}")
    if not isinstance(outer[0][2], str) or not outer[0][2]:
        raise ValueError(f"batchexecute outer[0][2] is not a non-empty string: {outer[0][2]!r}")

    return json.loads(outer[0][2])


def resolve_blogger_streams(token: str) -> list[str]:
    """Resolve a blogger token to googlevideo URLs, best quality first."""
    inner = _fetch_batchexecute_inner(token)
    return _parse_batchexecute_streams(inner)


def resolve_blogger_token(token: str) -> str:
    """Resolve a blogger.com video token to the best googlevideo.com MP4 URL."""
    streams = resolve_blogger_streams(token)
    return streams[0]
