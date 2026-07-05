#!/usr/bin/env python3
"""Extrai a URL de vídeo Full HD de episódios do dattebayo-br.com.

Uso:
    uv run scripts/extract_dattebayo.py <url_episodio> [<url_episodio> ...]
    uv run scripts/extract_dattebayo.py --play <url_episodio>   # abre no mpv
    uv run scripts/extract_dattebayo.py --quality hd <url>      # SD | hd | fullhd

Fluxo:
    /videos/{id} -> R2 unsigned (fful/{id}.mp4)
    -> ads.animeyabu.net assina a URL -> mp4 direto no Cloudflare R2.
    A assinatura expira em ~1h (X-Amz-Expires=3600).
"""

import subprocess
import sys

import httpx

from scrapers.plugins.dattebayo import (
    resolve_signed_video_url,
    sign_video_url,
    unsigned_video_url,
    extract_video_id,
)

TIMEOUT = 20


def extract_video(
    client: httpx.Client,
    episode_url: str,
    *,
    quality: str = "fullhd",
) -> str:
    """Devolve a URL assinada do episódio na qualidade pedida."""
    if quality == "fullhd":
        return resolve_signed_video_url(client, episode_url, qualities=("fullhd",))

    video_id = extract_video_id(episode_url)
    unsigned = unsigned_video_url(video_id, quality=quality)
    return sign_video_url(client, unsigned, referer=episode_url)


def play_mpv(url: str, *, referer: str) -> None:
    subprocess.run(
        ["mpv", f"--referrer={referer}", url],
        check=False,
    )


def main(argv: list[str]) -> int:
    play = "--play" in argv
    quality = "fullhd"
    args = [a for a in argv if not a.startswith("--")]

    if "--quality" in argv:
        idx = argv.index("--quality")
        try:
            quality = argv[idx + 1].lower()
        except IndexError:
            print("[erro] --quality requer sd, hd ou fullhd", file=sys.stderr)
            return 1
        args = [a for i, a in enumerate(argv) if not a.startswith("--") and i not in {idx, idx + 1}]

    if not args:
        print(__doc__)
        return 1

    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        for episode_url in args:
            try:
                video = extract_video(client, episode_url, quality=quality)
            except (httpx.HTTPError, ValueError) as exc:
                print(f"[erro] {episode_url}: {exc}", file=sys.stderr)
                continue

            label = quality.upper()
            if quality == "fullhd":
                label = "FULLHD"
            print(f"[{label}] {episode_url}\n       {video}")
            if play:
                play_mpv(video, referer=episode_url)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
