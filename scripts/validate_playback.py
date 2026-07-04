#!/usr/bin/env python3
"""End-to-end validation: extract + mpv probe for real episode URLs."""

import subprocess
import sys


from scrapers.plugins.anitube import AniTube
from scrapers.plugins.animesdigital import AnimesDigital

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0"


def extract_and_test(scraper, url: str, referrer: str) -> bool:
    container: list[str] = []
    event = __import__("threading").Event()
    try:
        scraper.search_player_src(url, container, event)
    except Exception as e:
        print(f"  extraction failed: {e}")
        return False

    print(f"  candidates ({len(container)}):")
    for idx, candidate in enumerate(container, 1):
        itag = ""
        if "itag=" in candidate:
            import re

            m = re.search(r"itag=(\d+)", candidate)
            itag = f" itag={m.group(1)}" if m else ""
        print(f"    {idx}.{itag} {candidate[:100]}...")
        rc = subprocess.run(
            [
                "mpv",
                "--no-config",
                "--no-video",
                "--frames=5",
                "--really-quiet",
                f"--referrer={referrer}",
                f"--user-agent={UA}",
                candidate,
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        ok = rc.returncode == 0
        print(f"       mpv: {'✅' if ok else '❌'} ({rc.returncode})")
        if ok:
            return True
    return False


def main():
    tests = [
        (
            "AniTube",
            AniTube(),
            "https://www.anitube.zip/video/1061265/",
            "https://www.anitube.zip/video/1061265/",
        ),
        (
            "AnimesDigital",
            AnimesDigital(),
            "https://animesdigital.org/video/a/136878/",
            "https://animesdigital.org/video/a/136878/",
        ),
    ]
    if len(sys.argv) > 1:
        tests = [("CLI", AniTube(), sys.argv[1], sys.argv[1])]

    all_ok = True
    for name, scraper, url, ref in tests:
        print(f"\n=== {name}: {url} ===")
        if not extract_and_test(scraper, url, ref):
            all_ok = False

    if all_ok:
        print("\n✅ At least one playable candidate per source")
        return 0
    print("\n❌ Some sources had no playable candidate")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
