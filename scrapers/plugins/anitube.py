from utils.logging import get_logger
import re
import urllib.parse
from urllib.parse import unquote

import httpx
from bs4 import BeautifulSoup

from scrapers.core.blogger_resolver import resolve_blogger_token
from scrapers.plugins.utils import DEFAULT_HEADERS, load_plugin, store_player_source
from models.models import AnimeMetadata
from services.repository import rep

logger = get_logger(__name__)

HEADERS = DEFAULT_HEADERS


class AniTube:
    name = "anitube"
    base_url = "https://www.anitube.zip"

    def search_anime(self, query: str) -> list[AnimeMetadata]:
        collected: list[AnimeMetadata] = []

        def _do_search(q: str) -> None:
            try:
                url = f"{self.base_url}/wp-json/wp/v2/posts?search={urllib.parse.quote(q)}&per_page=20"
                response = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
                response.raise_for_status()
                posts = response.json()
            except httpx.HTTPError as e:
                logger.debug(f"AniTube search request failed for '{q}': {e}")
                return
            for post in posts:
                title = post.get("title", {}).get("rendered", "")
                link = post.get("link", "")
                if title and link:
                    lower_title = title.lower()
                    if "episódio" in lower_title and "todos" not in lower_title:
                        if " – ep" in lower_title or "episódio " in lower_title:
                            continue
                    title = (
                        title.replace(" – Todos os Episódios", "")
                        .replace(" – Todos Episódios", "")
                        .replace(" todos os episodios", "")
                        .replace(" todos episodios", "")
                        .replace("&#8211;", "–")
                    )
                    collected.append(AnimeMetadata(title=title.strip(), url=link, source=self.name))

        _do_search(query)
        _do_search(f"{query} todos os episodios")
        return collected

    def search_episodes(self, anime: str, url: str, params: dict | None) -> None:
        try:
            separator = "&" if "?" in url else "?"
            episodes_url = f"{url}{separator}ord=1"

            response = httpx.get(episodes_url, headers=HEADERS, timeout=30, follow_redirects=True)
            response.raise_for_status()
            page = BeautifulSoup(response.text, "html.parser")

            episode_links = page.select("a[title*='Episódio']")
            titles = []
            urls = []
            for a in episode_links:
                href = a.get("href")
                title = a.get("title")
                if href and title and href.startswith("http"):
                    titles.append(title.strip())
                    urls.append(href)

            rep.add_episode_list(anime, titles, urls, self.name)
        except httpx.HTTPError as e:
            logger.debug(f"AniTube episode fetch failed for '{anime}': {e}")
            return

    def search_player_src(self, url: str, container: list, event) -> None:
        try:
            response = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
            response.raise_for_status()
            page = BeautifulSoup(response.text, "html.parser")

            # anivideo HLS backend: the direct CDN stream lives in the
            # videohls.php `d=` parameter, usually right on the episode page.
            if hls_url := self._extract_hls(response.text):
                if store_player_source(container, event, hls_url):
                    return

            # Otherwise the episode embeds a Referer-gated redirector (bg.mp4)
            # that is not the real stream. Follow it to the provider page and
            # re-check for the videohls source there.
            meta = page.select_one("iframe.metaframe")
            redirector = meta.get("src") if meta else None
            if redirector:
                hop = httpx.get(
                    redirector,
                    headers={**HEADERS, "Referer": url},
                    timeout=30,
                    follow_redirects=False,
                )
                location = hop.headers.get("location", "")
                if location.startswith("http"):
                    provider = httpx.get(
                        location,
                        headers={**HEADERS, "Referer": f"{self.base_url}/"},
                        timeout=30,
                        follow_redirects=True,
                    )
                    provider.raise_for_status()
                    if hls_url := self._extract_hls(provider.text):
                        if store_player_source(container, event, hls_url):
                            return

                    # Blogger backend: resolve the token to a direct
                    # googlevideo.com URL (playable by MPV with a browser UA).
                    for token in re.findall(
                        r"blogger\.com/video\.g\?token=([A-Za-z0-9_-]+)", provider.text
                    ):
                        try:
                            video_url = resolve_blogger_token(token)
                        except Exception as e:
                            logger.debug(f"AniTube blogger token resolve failed, trying next: {e}")
                            continue
                        if store_player_source(container, event, video_url):
                            return

            raise Exception("No playable video source found in AniTube episode page")
        except httpx.HTTPError as e:
            raise Exception(f"Could not extract video from AniTube: {e}") from e

    @staticmethod
    def _extract_hls(html: str) -> str | None:
        """Extract the direct HLS URL from an anivideo videohls.php `d=` param.

        The `d=` value points at the CDN base (an .mp4 path); the actual
        playlist is served at `<base>/index.m3u8`.
        """
        match = re.search(r"https://api\.anivideo\.net/videohls\.php\?d=([^\"'<>&\s]+)", html)
        if not match:
            return None
        base = unquote(match.group(1))
        return base if base.endswith(".m3u8") else f"{base}/index.m3u8"


def load() -> None:
    load_plugin(AniTube, rep.register)
