from utils.logging import get_logger
import re
import urllib.parse

import httpx
from bs4 import BeautifulSoup

from scrapers.core.blogger_resolver import resolve_blogger_token
from scrapers.plugins.utils import (
    DEFAULT_HEADERS,
    http_get_with_retry,
    load_plugin,
    store_player_source,
)
from models.models import AnimeMetadata, ScrapedEpisodes

logger = get_logger(__name__)

BASE_URL = "https://animesonlinecc.to"
HEADERS = DEFAULT_HEADERS
REQUEST_TIMEOUT = 15

_EPISODE_PARTS_RE = re.compile(r"/episodio/(?P<slug>.+?)-episodio-(?P<num>\d+)/?$")
_ANIME_SLUG_RE = re.compile(r"/anime/([^/]+)")
_TOKEN_RE = re.compile(r"token=([^&\s\"']+)")


def _season_from_slug(episode_slug: str, anime_slug: str) -> int:
    """Infer the season of an episode from its URL slug.

    AnimesOnlineCC lists every season of a series on the same anime page.
    Season 1 episodes reuse the anime slug ("mato-seihei-no-slave"), while later
    seasons append the season number ("mato-seihei-no-slave-2"). Anchoring on the
    known anime slug keeps series whose title ends in a number from being
    misread as a season.
    """
    if not anime_slug or episode_slug == anime_slug:
        return 1
    if episode_slug.startswith(f"{anime_slug}-"):
        suffix = episode_slug[len(anime_slug) + 1 :]
        if suffix.isdigit():
            return int(suffix)
    return 1


class AnimesOnlineCC:
    name = "animesonlinecc"
    base_url = BASE_URL

    def search_anime(self, query: str) -> list[AnimeMetadata]:
        results = []
        try:
            url = f"{BASE_URL}/search/{urllib.parse.quote(query)}"
            r = http_get_with_retry(
                url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True
            )
            soup = BeautifulSoup(r.text, "html.parser")
            for article in soup.select("article"):
                a = article.find("a", href=re.compile(r"/anime/"))
                if not a:
                    continue
                title_el = article.find(["h2", "h3"])
                title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)
                link = a.get("href", "")
                if title and link:
                    results.append(AnimeMetadata(title=title, url=link, source=self.name))
        except httpx.HTTPError as e:
            logger.debug(f"AnimesOnlineCC search request failed for '{query}': {e}")
        return results

    def search_episodes(self, anime: str, url: str, params: dict | None) -> list[ScrapedEpisodes]:
        target_season = 1
        if isinstance(params, dict) and params.get("season"):
            target_season = int(params["season"])

        anime_slug_match = _ANIME_SLUG_RE.search(url)
        anime_slug = anime_slug_match.group(1) if anime_slug_match else ""

        try:
            r = http_get_with_retry(
                url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True
            )
            soup = BeautifulSoup(r.text, "html.parser")

            # The anime page mixes every season together; group by season so a
            # single source never merges S1 + S2 into one continuous list.
            seen = set()
            episodes: list[tuple[int, str]] = []  # (episode number, url)
            for a in soup.find_all("a", href=re.compile(r"/episodio/")):
                ep_url = str(a.get("href", ""))
                if ep_url.startswith("//"):
                    ep_url = "https:" + ep_url
                parts = _EPISODE_PARTS_RE.search(ep_url)
                # Skip nav links (no episode number) and relative URLs
                if not ep_url.startswith("http") or not parts or ep_url in seen:
                    continue
                if _season_from_slug(parts.group("slug"), anime_slug) != target_season:
                    continue
                seen.add(ep_url)
                episodes.append((int(parts.group("num")), ep_url))

            episodes.sort(key=lambda item: item[0])
            titles = [f"Episódio {num}" for num, _ in episodes]
            urls = [ep_url for _, ep_url in episodes]

            if titles and urls:
                return [
                    ScrapedEpisodes(
                        titles=titles, urls=urls, source=self.name, season=target_season
                    )
                ]
            return []
        except httpx.HTTPError as e:
            logger.debug(f"AnimesOnlineCC episode fetch failed for '{anime}': {e}")
            return []

    def search_player_src(self, url: str, container: list, event) -> None:
        try:
            r = http_get_with_retry(
                url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True
            )
            soup = BeautifulSoup(r.text, "html.parser")

            iframes = soup.find_all("iframe", src=re.compile(r"blogger\.com/video\.g"))
            if not iframes:
                raise ValueError("No blogger iframe found in AnimesOnlineCC episode page")

            for iframe in iframes:
                src = iframe.get("src", "")
                m = _TOKEN_RE.search(src)
                if not m:
                    continue
                token = m.group(1)
                try:
                    video_url = resolve_blogger_token(token)
                except Exception as e:
                    logger.debug(f"AnimesOnlineCC blogger token resolve failed, trying next: {e}")
                    continue
                if store_player_source(container, event, video_url):
                    return

            raise ValueError("No playable blogger source in AnimesOnlineCC episode page")
        except Exception as e:
            raise type(e)(f"AnimesOnlineCC: {e}") from e


def load(register) -> None:
    load_plugin(AnimesOnlineCC, register)
