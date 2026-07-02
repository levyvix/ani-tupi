from utils.logging import get_logger
import re
import urllib.parse
from urllib.parse import unquote

import httpx
from bs4 import BeautifulSoup

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
            html_content = response.text

            # Preferred: the anivideo embed carries the direct CDN m3u8 in its
            # `d=` parameter. The embed URL itself is an HTML player page that
            # MPV cannot play, so extract the underlying stream instead.
            hls_match = re.search(
                r"https://api\.anivideo\.net/videohls\.php\?d=([^\"'<>&\s]+)", html_content
            )
            if hls_match:
                hls_url = unquote(hls_match.group(1))
                if store_player_source(container, event, hls_url):
                    return

            # Fallback: any anivideo iframe src (still an embed page, but let the
            # downstream player attempt it before giving up).
            page = BeautifulSoup(html_content, "html.parser")
            for iframe in page.select("iframe.metaframe"):
                src = iframe.get("src") or ""
                if "api." in src:
                    if store_player_source(container, event, src):
                        return

            # Last resort: first iframe on the page.
            iframe = page.select_one("iframe")
            if iframe:
                src = iframe.get("src", "")
                if src:
                    if store_player_source(container, event, src):
                        return

            raise Exception("No video source found in AniTube episode page")
        except Exception as e:
            raise Exception(f"Could not extract video from AniTube: {e}") from e


def load() -> None:
    load_plugin(AniTube, rep.register)
