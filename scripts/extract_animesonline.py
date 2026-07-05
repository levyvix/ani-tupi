#!/usr/bin/env python3
"""Extrai a URL de vídeo (mp4 direto ou HLS assinado) de episódios do animesonline.cloud.

Uso:
    uv run scripts/extract_animesonline.py <url_episodio> [<url_episodio> ...]
    uv run scripts/extract_animesonline.py --play <url_episodio>   # abre no mpv

Fluxo:
    página do episódio -> opções do player (data-post/type/nume)
    -> API DooPlay v2 -> fonte type="mp4" -> parâmetro `source` decodificado.
    A fonte "mp4" do DooPlay pode ser um .mp4 direto (aniplay.online) ou um
    HLS assinado via proxy (ccdn.xyz/stream.php?...playlist.m3u8). Ambos tocam no mpv.
"""

import re
import subprocess
import sys
from urllib.parse import parse_qs, unquote, urlparse

import httpx

BASE = "https://animesonline.cloud"
API = BASE + "/wp-json/dooplayer/v2/{post}/{typ}/{nume}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Referer": BASE + "/",
}
TIMEOUT = 20

_OPT_RE = re.compile(r"data-type='([^']+)' data-post='(\d+)' data-nume='([^']+)'")


def _player_options(client: httpx.Client, episode_url: str) -> list[tuple[str, str, str]]:
    """Retorna [(type, post, nume)] das abas de player da página."""
    r = client.get(episode_url, headers={**HEADERS, "Referer": episode_url})
    r.raise_for_status()
    return _OPT_RE.findall(r.text)


def _resolve_source(embed_url: str) -> str | None:
    """Extrai a URL de vídeo do embed_url da fonte type='mp4'.

    O embed é `.../jwplayer?source=<url-encoded>&...`; devolve a URL decodificada,
    seja .mp4 direto ou HLS (playlist.m3u8) via ccdn.xyz.
    """
    source = parse_qs(urlparse(embed_url).query).get("source", [""])[0]
    return unquote(source) or None


def extract_video(client: httpx.Client, episode_url: str) -> str | None:
    """Devolve a melhor URL de vídeo (mp4/HLS) do episódio, ou None."""
    for typ, post, nume in _player_options(client, episode_url):
        api = API.format(post=post, typ=typ, nume=nume)
        try:
            data = client.get(api, headers=HEADERS).json()
        except (httpx.HTTPError, ValueError):
            continue
        if data.get("type") == "mp4":
            if url := _resolve_source(data.get("embed_url", "")):
                return url
    return None


def play_mpv(url: str) -> None:
    subprocess.run(["mpv", f"--referrer={BASE}/", url], check=False)


def main(argv: list[str]) -> int:
    play = "--play" in argv
    urls = [a for a in argv if not a.startswith("--")]
    if not urls:
        print(__doc__)
        return 1

    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        for ep in urls:
            try:
                video = extract_video(client, ep)
            except httpx.HTTPError as e:
                print(f"[erro] {ep}: {e}", file=sys.stderr)
                continue
            if not video:
                print(f"[sem fonte mp4] {ep}", file=sys.stderr)
                continue
            kind = "HLS" if ".m3u8" in video else "MP4"
            print(f"[{kind}] {ep}\n       {video}")
            if play:
                play_mpv(video)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
