import re
import urllib.parse

import httpx
from bs4 import BeautifulSoup

from models.models import AnimeMetadata, ScrapedEpisodes
from scrapers.plugins.utils import (
    DEFAULT_HEADERS,
    CloudflareChallengeError,
    http_get_with_retry,
    load_plugin,
    store_player_source,
)
from utils.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://animesonline.cloud"
HEADERS = DEFAULT_HEADERS
REQUEST_TIMEOUT = 20

_PLAYER_OPTION_RE = re.compile(
    r"data-type=['\"]([^'\"]+)['\"] data-post=['\"](\d+)['\"] data-nume=['\"]([^'\"]+)['\"]"
)
_EPISODE_NUM_RE = re.compile(r"-episodio-(\d+)/?$")
_ALL_EPISODES_SUFFIX_RE = re.compile(r"\s+todos\s+os\s+epis[oó]dios\s*$", re.IGNORECASE)
_CLOUDFLARE_WARNING = "AnimesOnlineCloud indisponível: o Cloudflare exige validação no navegador."
_CLOUDFLARE_BYPASS_INFO = (
    "Cloudflare detectado em AnimesOnlineCloud, tentando bypass via navegador..."
)


def _parse_search_results(soup: BeautifulSoup, source_name: str) -> list[AnimeMetadata]:
    results = []
    for article in soup.select("article"):
        a = article.select_one(".details .title a[href*='/anime/']")
        if not a:
            continue
        title = _ALL_EPISODES_SUFFIX_RE.sub("", a.get_text(strip=True)).strip()
        link = a.get("href", "")
        if title and link:
            results.append(AnimeMetadata(title=title, url=link, source=source_name))
    return results


def _parse_episode_results(soup: BeautifulSoup, source_name: str) -> list[ScrapedEpisodes]:
    seen = set()
    titles = []
    urls = []
    for a in soup.find_all("a", href=re.compile(r"/episodio/")):
        ep_url = str(a.get("href", ""))
        num_match = _EPISODE_NUM_RE.search(ep_url)
        if not ep_url.startswith("http") or not num_match or ep_url in seen:
            continue
        seen.add(ep_url)
        title = a.get_text(strip=True) or f"Episódio {int(num_match.group(1))}"
        titles.append(title)
        urls.append(ep_url)

    if titles and urls:
        return [ScrapedEpisodes(titles=titles, urls=urls, source=source_name)]
    return []


class AnimesOnlineCloud:
    name = "animesonlinecloud"
    base_url = BASE_URL

    def search_anime(self, query: str) -> list[AnimeMetadata]:
        url = f"{BASE_URL}/?s={urllib.parse.quote(query)}"
        try:
            r = http_get_with_retry(
                url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True
            )
            soup = BeautifulSoup(r.text, "html.parser")
            return _parse_search_results(soup, self.name)
        except CloudflareChallengeError:
            logger.info(_CLOUDFLARE_BYPASS_INFO)
            try:
                return self._search_anime_via_browser(url)
            except Exception as e:
                logger.warning(f"{_CLOUDFLARE_WARNING} (bypass falhou: {e})")
                return []
        except httpx.HTTPError as e:
            logger.debug(f"AnimesOnlineCloud search request failed for '{query}': {e}")
        return []

    def _search_anime_via_browser(self, url: str) -> list[AnimeMetadata]:
        from scrapers.core.selenium_driver import SeleniumWebDriver

        with SeleniumWebDriver(headless=True, timeout=30) as driver:
            soup = driver.fetch(url, wait_selector="article")
            return _parse_search_results(soup, self.name)

    def search_episodes(self, anime: str, url: str, params: dict | None) -> list[ScrapedEpisodes]:
        _ = params
        try:
            r = http_get_with_retry(
                url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True
            )
            soup = BeautifulSoup(r.text, "html.parser")
            return _parse_episode_results(soup, self.name)
        except CloudflareChallengeError:
            logger.info(_CLOUDFLARE_BYPASS_INFO)
            try:
                return self._search_episodes_via_browser(url)
            except Exception as e:
                logger.warning(f"{_CLOUDFLARE_WARNING} (bypass falhou: {e})")
                return []
        except httpx.HTTPError as e:
            logger.debug(f"AnimesOnlineCloud episode fetch failed for '{anime}': {e}")
            return []

    def _search_episodes_via_browser(self, url: str) -> list[ScrapedEpisodes]:
        from scrapers.core.selenium_driver import SeleniumWebDriver

        with SeleniumWebDriver(headless=True, timeout=30) as driver:
            soup = driver.fetch(url, wait_selector="a[href*='/episodio/']")
            return _parse_episode_results(soup, self.name)

    def search_player_src(self, url: str, container: list, event) -> None:
        try:
            r = http_get_with_retry(
                url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True
            )
            if self._extract_player_sources(r.text, url, container, event):
                return
            raise ValueError("No playable source in AnimesOnlineCloud episode page")
        except CloudflareChallengeError as cf_err:
            logger.info(_CLOUDFLARE_BYPASS_INFO)
            try:
                if self._extract_player_sources_via_browser(url, container, event):
                    return
                raise ValueError("No playable source via browser bypass")
            except CloudflareChallengeError as e:
                raise RuntimeError(f"AnimesOnlineCloud: {e}") from e
            except ValueError as e:
                raise RuntimeError(f"AnimesOnlineCloud: {e}") from cf_err
            except Exception as e:
                raise RuntimeError(f"AnimesOnlineCloud: {e}") from e
        except Exception as e:
            raise RuntimeError(f"AnimesOnlineCloud: {e}") from e

    def _extract_player_sources(self, html: str, referer: str, container: list, event) -> bool:
        found = False
        for typ, post, nume in _PLAYER_OPTION_RE.findall(html):
            embed = self._dooplayer_embed(referer, post, typ, nume)
            if not embed:
                continue
            if embed.get("type") == "mp4":
                if source := self._decode_source(embed.get("embed_url", "")):
                    if store_player_source(container, event, source):
                        found = True
        return found

    def _extract_player_sources_via_browser(self, url: str, container: list, event) -> bool:
        from scrapers.core.selenium_driver import SeleniumWebDriver

        with SeleniumWebDriver(headless=True, timeout=30) as driver:
            soup = driver.fetch(url, wait_selector="body")
            # Use raw page_source when available to preserve original quoting
            try:
                html = driver.driver.page_source or str(soup)
            except Exception:
                html = str(soup)

            found = False
            for typ, post, nume in _PLAYER_OPTION_RE.findall(html):
                # Try browser fetch for API (reuses cf_clearance cookies)
                embed = self._dooplayer_embed_via_browser(driver, url, post, typ, nume)
                if embed is None:
                    try:
                        embed = self._dooplayer_embed(url, post, typ, nume)
                    except CloudflareChallengeError:
                        # API still behind Cloudflare even after page bypass - skip
                        continue
                if not embed:
                    continue
                if embed.get("type") == "mp4":
                    if source := self._decode_source(embed.get("embed_url", "")):
                        if store_player_source(container, event, source):
                            found = True
            return found

    def _dooplayer_embed(self, referer: str, post: str, typ: str, nume: str) -> dict | None:
        api = f"{BASE_URL}/wp-json/dooplayer/v2/{post}/{typ}/{nume}"
        try:
            r = http_get_with_retry(
                api,
                headers={**HEADERS, "Referer": referer},
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
            )
            return r.json()
        except CloudflareChallengeError:
            # Let caller decide to use browser fallback
            raise
        except (httpx.HTTPError, ValueError) as e:
            logger.debug(f"AnimesOnlineCloud dooplayer API failed ({post}/{typ}/{nume}): {e}")
            return None

    def _dooplayer_embed_via_browser(
        self, driver, referer: str, post: str, typ: str, nume: str
    ) -> dict | None:
        api = f"{BASE_URL}/wp-json/dooplayer/v2/{post}/{typ}/{nume}"
        try:
            result = driver.fetch_json(api, referer=referer)
            if result is not None:
                return result
        except Exception as e:
            logger.debug(
                f"AnimesOnlineCloud dooplayer browser API failed ({post}/{typ}/{nume}): {e}"
            )
        return None

    @staticmethod
    def _decode_source(embed_url: str) -> str | None:
        """Decode the `source` param of a jwplayer embed (direct .mp4 or signed HLS)."""
        query = urllib.parse.urlparse(embed_url).query
        source = urllib.parse.parse_qs(query).get("source", [""])[0]
        return urllib.parse.unquote(source) or None


def load(register) -> None:
    load_plugin(AnimesOnlineCloud, register)
