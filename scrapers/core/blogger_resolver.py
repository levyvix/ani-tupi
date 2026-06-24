"""Resolve blogger.com video tokens to direct googlevideo.com streaming URLs.

Blogger video embeds serve MP4 content via Google's CDN. The actual URL
is fetched through the BloggerVideoPlayerUi batchexecute API.
"""

import json
import re

import requests

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Accept-Language": "pt-BR,pt;q=0.9",
}
_TIMEOUT = 15


def resolve_blogger_token(token: str) -> str:
    """Resolve a blogger.com video token to a direct googlevideo.com MP4 URL.

    Args:
        token: Blogger video token (from blogger.com/video.g?token=TOKEN)

    Returns:
        Direct googlevideo.com URL playable by MPV with browser User-Agent

    Raises:
        ValueError: If the token cannot be resolved
    """
    # Step 1: GET the player page to extract session parameters
    r = requests.get(
        f"https://www.blogger.com/video.g?token={token}",
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()

    fsid_m = re.search(r'"FdrFJe"\s*:\s*"(-?\d+)"', r.text)
    bl_m = re.search(r'"cfb2h"\s*:\s*"([^"]+)"', r.text)
    if not fsid_m or not bl_m:
        raise ValueError("Could not extract session parameters from blogger page")

    fsid = fsid_m.group(1)
    bl = bl_m.group(1)

    # Step 2: POST to batchexecute API to get the video URL
    f_req = json.dumps([[["WcwnYd", json.dumps([token, None, 0]), None, "generic"]]])
    r2 = requests.post(
        "https://www.blogger.com/_/BloggerVideoPlayerUi/data/batchexecute",
        params={
            "rpcids": "WcwnYd",
            "source-path": "/video.g",
            "f.sid": fsid,
            "bl": bl,
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

    # Parse the doubly-encoded JSON response
    json_line = next(
        (line.strip() for line in r2.text.split("\n") if line.strip().startswith("[[")),
        None,
    )
    if not json_line:
        raise ValueError("No JSON data in batchexecute response")

    outer = json.loads(json_line)
    inner = json.loads(outer[0][2])
    url = inner[2][0][0]
    if not url or "googlevideo.com" not in url:
        raise ValueError(f"Unexpected video URL: {url!r}")
    return url
