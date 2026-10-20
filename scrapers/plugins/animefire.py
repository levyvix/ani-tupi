import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from models.models import AnimeMetadata, ScrapedEpisodes
from scrapers.core.blogger_resolver import resolve_blogger_token
from scrapers.plugins.utils import http_get_with_retry, load_plugin, store_player_source
from utils.logging import get_logger

logger = get_logger(__name__)

REQUEST_TIMEOUT = 20
API_BASE_URL = "https://api.animefire.one"
SITE_BASE_URL = "https://animefire.one"

SEARCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

API_HEADERS = {
    **SEARCH_HEADERS,
    "Accept": "application/json, text/plain, */*",
    "Referer": f"{SITE_BASE_URL}/",
}


class AnimeFire:
    name = "animefire"

    @staticmethod
    def _season_numbers(anime_id: str) -> list[int]:
        """Fetch the season numbers attached to one AnimeFire catalog card."""
        try:
            response = http_get_with_retry(
                f"{API_BASE_URL}/anime/{anime_id}",
                headers=API_HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            data = AnimeFire._api_data(response)
        except Exception as e:
            logger.debug("AnimeFire seasons lookup failed for %s: %s", anime_id, e)
            return [1]

        seasons = data.get("seasons", [])
        numbers = set()
        if isinstance(seasons, list):
            for season in seasons:
                if isinstance(season, dict):
                    try:
                        numbers.add(max(1, int(season.get("number") or 1)))
                    except (TypeError, ValueError):
                        continue

        if not numbers:
            episodes = data.get("episodes", [])
            if isinstance(episodes, list):
                for episode in episodes:
                    if not isinstance(episode, dict):
                        continue
                    try:
                        numbers.add(max(1, int(episode.get("season") or 1)))
                    except (TypeError, ValueError):
                        continue

        return sorted(numbers) or [1]

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

    @staticmethod
    def _anime_id(url: str, params: dict | None = None) -> str | None:
        """Get the app's opaque anime ID from plugin params or a URL."""
        if params and (anime_id := params.get("anime_id")):
            return str(anime_id)

        parts = [part for part in urlsplit(url).path.split("/") if part]
        try:
            anime_index = parts.index("anime")
        except ValueError:
            return None
        return parts[anime_index + 1] if anime_index + 1 < len(parts) else None

    @staticmethod
    def _episode_id(url: str) -> str | None:
        """Get an episode ID from the API URL or the app's episode URL."""
        parts = [part for part in urlsplit(url).path.split("/") if part]
        try:
            episode_index = parts.index("episode")
        except ValueError:
            return None
        return parts[episode_index + 1] if episode_index + 1 < len(parts) else None

    @staticmethod
    def _api_data(response) -> dict:
        payload = response.json()
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _matching_title(titles: dict, query: str) -> str | None:
        """Prefer the localized alias that matches the user's search text."""
        language_priority = ("BR", "US", "JP")
        candidates = [
            (language, str(title))
            for language in language_priority
            if (title := titles.get(language))
        ]
        candidates.extend(
            (language, str(title))
            for language, title in titles.items()
            if language not in language_priority and title
        )
        if not candidates:
            return None

        query_words = set(re.findall(r"\w+", query.casefold()))
        if not query_words:
            return candidates[0][1]

        return max(
            enumerate(candidates),
            key=lambda item: (
                len(query_words.intersection(re.findall(r"\w+", item[1][1].casefold()))),
                -item[0],
            ),
        )[1][1]

    def search_anime(self, query: str) -> list[AnimeMetadata]:
        response = http_get_with_retry(
            f"{API_BASE_URL}/animes/pesquisar?{urlencode({'q': query})}",
            headers=API_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        payload = response.json()
        results = payload.get("data", []) if isinstance(payload, dict) else []
        if not isinstance(results, list):
            return []

        valid_results = []
        for result in results:
            if not isinstance(result, dict) or not result.get("id"):
                continue
            titles = result.get("titles")
            if isinstance(titles, dict):
                title = self._matching_title(titles, query)
            else:
                title = titles
            if not title:
                continue
            anime_id = str(result["id"])
            valid_results.append((str(title), anime_id))

        if not valid_results:
            return []

        worker_count = min(8, len(valid_results))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            seasons_by_anime = list(
                executor.map(
                    self._season_numbers,
                    (anime_id for _, anime_id in valid_results),
                )
            )

        anime_results = []
        for (title, anime_id), seasons in zip(valid_results, seasons_by_anime, strict=True):
            for season in seasons:
                season_title = title if season == 1 else f"{title} {season}"
                anime_results.append(
                    AnimeMetadata(
                        title=season_title,
                        url=f"{SITE_BASE_URL}/anime/{anime_id}",
                        source=self.name,
                        params={"anime_id": anime_id, "season": season},
                    )
                )
        return anime_results

    def search_episodes(self, anime: str, url: str, params: dict | None) -> list[ScrapedEpisodes]:
        try:
            anime_id = self._anime_id(url, params)
            if anime_id:
                response = http_get_with_retry(
                    f"{API_BASE_URL}/anime/{anime_id}",
                    headers=API_HEADERS,
                    timeout=REQUEST_TIMEOUT,
                )
                anime_data = self._api_data(response)
                episodes = anime_data.get("episodes", [])
                if not isinstance(episodes, list):
                    return []

                by_season: dict[int, list[dict]] = {}
                for episode in episodes:
                    if not isinstance(episode, dict) or not episode.get("id"):
                        continue
                    try:
                        season = max(1, int(episode.get("season") or 1))
                        number = int(episode["number"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    by_season.setdefault(season, []).append({**episode, "number": number})

                batches = []
                for season, season_episodes in sorted(by_season.items()):
                    requested_season = params.get("season") if params else None
                    if requested_season is not None and season != int(requested_season):
                        continue
                    ordered_episodes = sorted(
                        season_episodes, key=lambda episode: episode["number"]
                    )
                    batches.append(
                        ScrapedEpisodes(
                            titles=[
                                f"Episódio {episode['number']}"
                                + (f" - {episode['title']}" if episode.get("title") else "")
                                for episode in ordered_episodes
                            ],
                            urls=[
                                f"{API_BASE_URL}/episode/{episode['id']}"
                                for episode in ordered_episodes
                            ],
                            source=self.name,
                            season=season,
                        )
                    )
                return batches

            # Legacy AnimeFire links still use the old HTML episode list.
            response = http_get_with_retry(url, timeout=REQUEST_TIMEOUT)
            tree = BeautifulSoup(response.text, "html.parser")
            ep_links = tree.select("a.lEp")
            if not ep_links:
                logger.debug(f"AnimeFire: no episodes found for '{anime}' at {url}")
                return []

            episode_links = [a.get("href") for a in ep_links if a.get("href")]
            if not episode_links:
                logger.debug(f"AnimeFire: no valid hrefs for '{anime}' at {url}")
                return []

            opts = []
            for href in episode_links:
                m = re.search(r"/(\d+(?:\.\d+)?)$", href)
                opts.append(m.group(1) if m else href.split("/")[-1])

            return [ScrapedEpisodes(titles=opts, urls=episode_links, source=self.name)]
        except Exception as e:
            logger.debug(f"AnimeFire episode fetch failed for '{anime}': {e}")
            return []

    def search_player_src(self, url: str, container: list, event) -> None:
        try:
            episode_id = self._episode_id(url)
            if episode_id and "animefire.one" in urlsplit(url).netloc.lower():
                response = http_get_with_retry(
                    f"{API_BASE_URL}/episode/{episode_id}",
                    headers=API_HEADERS,
                    timeout=REQUEST_TIMEOUT,
                )
                episode_data = self._api_data(response)
                streams = episode_data.get("streams", [])
                if not isinstance(streams, list):
                    streams = []
                for stream in streams:
                    if not isinstance(stream, dict) or stream.get("is_offline"):
                        continue
                    source_url = stream.get("url")
                    if isinstance(source_url, str) and source_url.startswith(
                        ("http://", "https://")
                    ):
                        store_player_source(container, event, source_url)
                if container:
                    return
                raise Exception("No playable streams found in AnimeFire API response")

            # data-video-src is in static HTML — no Selenium needed
            response = http_get_with_retry(url, timeout=REQUEST_TIMEOUT, follow_redirects=True)
            page = BeautifulSoup(response.text, "html.parser")

            # AnimeFire uses Video.js player with data-video-src attribute
            # The attribute contains an API endpoint that returns JSON with video URLs
            video = page.select_one("video")
            if video:
                api_url = video.get("data-video-src")
                if api_url:
                    try:
                        response = http_get_with_retry(
                            api_url, timeout=REQUEST_TIMEOUT, follow_redirects=True
                        )
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


def load(register) -> None:
    load_plugin(AnimeFire, register)
