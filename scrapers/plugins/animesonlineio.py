import base64
import json
import re
import urllib.parse

import httpx
from bs4 import BeautifulSoup

from models.models import AnimeMetadata, ScrapedEpisodes
from scrapers.plugins.utils import DEFAULT_HEADERS, load_plugin, store_player_source
from utils.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://animesonline.io"
HEADERS = DEFAULT_HEADERS
REQUEST_TIMEOUT = 20

_IFRAME_SRC_RE = re.compile(r'<iframe[^>]+src=["\']((?:https?:)?//[^"\']+)["\']', re.I)
_URL_RE = re.compile(r"^(?:https?:)?//", re.I)
# juicycodes-style loader call: _fn([<b64 pieces>], [<indices>], "<b64 xor key>")
_JUICY_CALL_RE = re.compile(r'\}\w+\((\[.*?\]),(\[[\d,\s]*\]),"([^"]+)"\)', re.S)
_JW_SOURCES_RE = re.compile(r"sources:\s*(\[.*?\])\s*,?\n")


class AnimesOnlineIO:
    name = "animesonlineio"
    base_url = BASE_URL

    def search_anime(self, query: str) -> list[AnimeMetadata]:
        results = []
        try:
            url = f"{BASE_URL}/search/{urllib.parse.quote(query)}"
            r = httpx.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for article in soup.select("article.bs"):
                a = article.select_one("a[href*='/anime/']")
                if not a:
                    continue
                title = str(a.get("title", "")) or a.get_text(strip=True)
                link = str(a.get("href", ""))
                if title and link:
                    results.append(AnimeMetadata(title=title, url=link, source=self.name))
        except httpx.HTTPError as e:
            logger.debug(f"AnimesOnlineIO search request failed for '{query}': {e}")
        return results

    def search_episodes(self, anime: str, url: str, params: dict | None) -> list[ScrapedEpisodes]:
        _ = params
        try:
            r = httpx.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            episodes = []
            seen = set()
            for li in soup.select(".eplister ul li"):
                a = li.find("a")
                if not a:
                    continue
                ep_url = str(a.get("href", ""))
                if not ep_url.startswith("http") or ep_url in seen:
                    continue
                seen.add(ep_url)
                num_el = li.select_one(".epl-num")
                title_el = li.select_one(".epl-title")
                num_text = num_el.get_text(strip=True) if num_el else ""
                try:
                    num = float(num_text)
                except ValueError:
                    num = 0.0
                title = (
                    title_el.get_text(strip=True) if title_el else f"Episódio {num_text}".strip()
                )
                episodes.append((num, title, ep_url))

            # The site lists episodes newest-first; playback expects ascending order
            episodes.sort(key=lambda ep: ep[0])
            if episodes:
                titles = [ep[1] for ep in episodes]
                urls = [ep[2] for ep in episodes]
                return [ScrapedEpisodes(titles=titles, urls=urls, source=self.name)]
            return []
        except httpx.HTTPError as e:
            logger.debug(f"AnimesOnlineIO episode fetch failed for '{anime}': {e}")
            return []

    def search_player_src(self, url: str, container: list, event) -> None:
        try:
            r = httpx.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            found = False
            for embed_url in self._extract_embed_urls(soup):
                for video_url in self._resolve_embed_streams(embed_url):
                    if store_player_source(container, event, video_url):
                        found = True

            if not found:
                raise ValueError("No playable source in AnimesOnlineIO episode page")
        except Exception as e:
            raise type(e)(f"AnimesOnlineIO: {e}") from e

    def _extract_embed_urls(self, soup: BeautifulSoup) -> list[str]:
        urls = []

        # Player tabs carry the embed as base64 (iframe HTML or bare URL)
        for li in soup.select(".tabs_videos li"):
            raw = ""
            for attr in ("value", "data-value", "data-embed", "data-src"):
                raw = str(li.get(attr, "") or "")
                if raw:
                    break
            if not raw:
                continue
            if embed_url := self._decode_embed(raw):
                urls.append(embed_url)

        # Fallback: lazy-loaded iframe in the player area
        for iframe in soup.select("iframe[data-src]"):
            src = self._normalize_url(str(iframe.get("data-src", "")))
            if src and "a-ads.com" not in src:
                urls.append(src)

        # Preserve order, drop duplicates
        return list(dict.fromkeys(urls))

    def _decode_embed(self, raw: str) -> str | None:
        value = raw
        try:
            decoded = base64.b64decode(raw).decode("utf-8")
            if "<" in decoded or _URL_RE.match(decoded):
                value = decoded
        except (ValueError, UnicodeDecodeError):
            pass

        if m := _IFRAME_SRC_RE.search(value):
            return self._normalize_url(m.group(1))
        if _URL_RE.match(value):
            return self._normalize_url(value)
        return None

    def _resolve_embed_streams(self, embed_url: str) -> list[str]:
        """Resolve an anidrive-style embed to direct googlevideo MP4 URLs (720p first)."""
        try:
            r = httpx.get(
                embed_url,
                headers={**HEADERS, "Referer": f"{BASE_URL}/"},
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
            )
            r.raise_for_status()
            payload = self._decode_juicy_payload(r.text)
            sources_m = _JW_SOURCES_RE.search(payload)
            if not sources_m:
                raise ValueError("No jwplayer sources in embed payload")

            streams = []
            for source in json.loads(sources_m.group(1)):
                file_url = source.get("file", "")
                if file_url.startswith("http"):
                    streams.append(self._follow_redirector(file_url))
            return streams
        except Exception as e:
            logger.debug(f"AnimesOnlineIO embed resolve failed for '{embed_url}': {e}")
            return []

    @staticmethod
    def _decode_juicy_payload(html: str) -> str:
        """Decode the XOR+base64 obfuscated jwplayer setup script."""
        m = _JUICY_CALL_RE.search(html)
        if not m:
            raise ValueError("No obfuscated payload in embed page")
        pieces = json.loads(m.group(1))
        indices = json.loads(m.group(2))
        data = base64.b64decode("".join(pieces[i] for i in indices))
        key = base64.b64decode(m.group(3))
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(data)).decode("utf-8")

    @staticmethod
    def _follow_redirector(url: str) -> str:
        """Resolve redirector.googlevideo.com hops; mpv/ffmpeg fail on the redirect."""
        if "redirector.googlevideo.com" not in url:
            return url
        try:
            r = httpx.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=False)
            location = r.headers.get("location", "")
            return location if location.startswith("http") else url
        except httpx.HTTPError:
            return url

    @staticmethod
    def _normalize_url(url: str) -> str:
        return f"https:{url}" if url.startswith("//") else url


def load(register) -> None:
    load_plugin(AnimesOnlineIO, register)
