import logging
import urllib.parse

import requests
from bs4 import BeautifulSoup
from requests import RequestException

from scrapers.plugins.utils import load_plugin, store_player_source
from models.models import AnimeMetadata
from services.repository import rep

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
}


class AniTube:
    name = "anitube"
    base_url = "https://www.anitube.zip"

    def search_anime(self, query: str) -> list[AnimeMetadata]:
        collected: list[AnimeMetadata] = []

        def _do_search(q: str) -> None:
            try:
                url = f"{self.base_url}/wp-json/wp/v2/posts?search={urllib.parse.quote(q)}&per_page=20"
                response = requests.get(url, headers=HEADERS, timeout=30)
                response.raise_for_status()
                posts = response.json()
            except RequestException as e:
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

            response = requests.get(episodes_url, headers=HEADERS, timeout=30)
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
        except RequestException as e:
            logger.debug(f"AniTube episode fetch failed for '{anime}': {e}")
            return

    def search_player_src(self, url: str, container: list, event) -> None:
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            page = BeautifulSoup(response.text, "html.parser")

            # Prefer the anivideo iframe which contains a direct m3u8 URL
            for iframe in page.select("iframe.metaframe"):
                src = iframe.get("src") or ""
                if "api." in src:
                    if store_player_source(container, event, src):
                        return

            # Fallback: any iframe
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
