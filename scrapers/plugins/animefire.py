import json
import re
from utils.logging import get_logger
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

from scrapers.core.blogger_resolver import resolve_blogger_token
from scrapers.plugins.utils import load_plugin, store_player_source
from models.models import AnimeMetadata
from services.repository import rep

logger = get_logger(__name__)

SEARCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class AnimeFire:
    name = "animefire"

    @staticmethod
    def _strip_ip_param(url: str | None) -> str | None:
        if not url:
            return None

        parts = urlsplit(url)
        query = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key != "ip"
        ]
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )

    @staticmethod
    def _resolve_if_blogger(url: str | None) -> str | None:
        """Resolve blogger.com/video.g embeds to direct googlevideo URLs."""
        if not url:
            return url
        m = re.search(r"blogger\.com/video\.g\?token=([^&\s]+)", url)
        if not m:
            return url
        try:
            return resolve_blogger_token(m.group(1))
        except Exception as e:
            logger.debug(f"AnimeFire blogger resolve failed: {e}")
            return url

    def _parse_search_page(self, tree: BeautifulSoup) -> list[AnimeMetadata]:
        target_class = "col-6 col-sm-4 col-md-3 col-lg-2 mb-1 minWDanime divCardUltimosEps"
        titles_urls = []
        selector = f"div.{target_class.replace(' ', '.')}"

        for div in tree.select(selector):
            article = div.select_one("article a")
            if article is not None:
                href = article.get("href")
                if href:
                    titles_urls.append(href)

        titles = [str(h3.text) for h3 in tree.select("h3.animeTitle")]
        results = []
        for title, page_url in zip(titles, titles_urls, strict=False):
            if page_url:
                results.append(AnimeMetadata(title=title, url=page_url, source=self.name))
        return results

    def search_anime(self, query: str) -> list[AnimeMetadata]:
        url = "https://animefire.plus/pesquisar/" + "-".join(query.split())
        response = httpx.get(url, timeout=20, follow_redirects=True, headers=SEARCH_HEADERS)
        response.raise_for_status()
        tree = BeautifulSoup(response.text, "html.parser")
        return self._parse_search_page(tree)

    def search_episodes(self, anime: str, url: str, params: dict | None) -> None:
        _ = params
        try:
            response = httpx.get(url, timeout=20, follow_redirects=True)
            response.raise_for_status()
            tree = BeautifulSoup(response.text, "html.parser")

            ep_links = tree.select("a.lEp")
            if not ep_links:
                logger.debug(f"AnimeFire: no episodes found for '{anime}' at {url}")
                return

            episode_links = [a.get("href") for a in ep_links if a.get("href")]
            if not episode_links:
                logger.debug(f"AnimeFire: no valid hrefs for '{anime}' at {url}")
                return

            opts = []
            for href in episode_links:
                m = re.search(r"/(\d+(?:\.\d+)?)$", href)
                opts.append(m.group(1) if m else href.split("/")[-1])

            rep.add_episode_list(anime, opts, episode_links, self.name)
        except Exception as e:
            logger.debug(f"AnimeFire episode fetch failed for '{anime}': {e}")

    def search_player_src(self, url: str, container: list, event) -> None:
        try:
            # data-video-src is in static HTML — no Selenium needed
            response = httpx.get(url, timeout=20, follow_redirects=True)
            response.raise_for_status()
            page = BeautifulSoup(response.text, "html.parser")

            # AnimeFire uses Video.js player with data-video-src attribute
            # The attribute contains an API endpoint that returns JSON with video URLs
            video = page.select_one("video")
            if video:
                api_url = video.get("data-video-src")
                if api_url:
                    try:
                        response = httpx.get(api_url, timeout=20, follow_redirects=True)
                        response.raise_for_status()
                        video_data = json.loads(response.text)

                        if isinstance(video_data, dict) and "data" in video_data:
                            videos = video_data["data"]
                            if isinstance(videos, list) and len(videos) > 0:
                                # Prefer highest quality: 1080p > 720p > 480p > 360p
                                best_video = None
                                for quality in ["1080p", "720p", "480p", "360p"]:
                                    for v in videos:
                                        if v.get("label", "").lower() == quality.lower():
                                            best_video = v.get("src")
                                            break
                                    if best_video:
                                        break

                                # If no quality match, take the last one (usually highest quality)
                                if not best_video and videos:
                                    best_video = videos[-1].get("src")

                                best_video = self._strip_ip_param(best_video)
                                best_video = self._resolve_if_blogger(best_video)

                                if best_video:
                                    if store_player_source(container, event, best_video):
                                        return
                    except Exception as e:
                        logger.debug(f"AnimeFire API fetch failed for '{url}': {e}")

                # Fallback: try standard src attribute
                src = self._resolve_if_blogger(video.get("src"))
                if src:
                    if store_player_source(container, event, src):
                        return

            # Try to find source tag inside video
            source = page.select_one("video source")
            if source:
                src = self._resolve_if_blogger(source.get("src"))
                if src:
                    if store_player_source(container, event, src):
                        return

            # Try to find iframe
            iframe = page.select_one("iframe")
            if iframe:
                src = self._resolve_if_blogger(iframe.get("src"))
                if src:
                    if store_player_source(container, event, src):
                        return

            raise Exception("No video source found in AnimeFire episode page")
        except Exception as e:
            raise Exception(f"Could not extract video from AnimeFire: {e}") from e


def load() -> None:
    load_plugin(AnimeFire, rep.register)
