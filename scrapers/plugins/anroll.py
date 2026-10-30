from utils.logging import get_logger
import base64
import json
import re
import time
import urllib.parse
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from scrapers.core.selenium_driver import SeleniumWebDriver
from scrapers.core.blogger_resolver import resolve_blogger_token
from scrapers.plugins.utils import (
    DEFAULT_HEADERS,
    http_get_with_retry,
    load_plugin,
    log_scraper_http_failure,
    store_player_source,
)
from models.models import AnimeMetadata, ScrapedEpisodes

logger = get_logger(__name__)

OPTIONAL_DEPENDENCIES = {"selenium": "browser-scrapers"}

BASE_URL = "https://anroll.cc"
HEADERS = DEFAULT_HEADERS
REQUEST_TIMEOUT = 15

_TITLE_DUB_HD_RE = re.compile(r"^(DUB|LEG)HD")
_TITLE_YEAR_RE = re.compile(r"\s*\d{4}$")
_TITLE_LEG_RE = re.compile(r"\s*\(?Legendado\)?\s*$", re.IGNORECASE)
_EPISODE_NUMBER_RE = re.compile(r"(?:epis[oó]dio|ep\.?)[\s-]*(\d+)", re.IGNORECASE)


class AnRoll:
    name = "anroll"
    base_url = BASE_URL

    def search_anime(self, query: str) -> list[AnimeMetadata]:
        results = []
        try:
            url = f"{BASE_URL}/?s={urllib.parse.quote(query)}"
            response = http_get_with_retry(
                url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True
            )
            soup = BeautifulSoup(response.text, "html.parser")
            cards = soup.select("article.anime-card")
            if cards:
                links = [card.find("a", href=True) for card in cards]
            else:
                # The current AnRoll site uses Dooplay's /animes/ routes and
                # puts the title link inside a div.title rather than an article
                # with the old anime-card class.
                links = soup.select("div.title a[href*='/animes/']")

            seen: set[str] = set()
            for a in links:
                if not a:
                    continue
                href = urljoin(BASE_URL, str(a.get("href", "")))
                if not any(path in href for path in ("/anime/", "/animes/")):
                    continue
                if href in seen:
                    continue
                seen.add(href)
                img = a.find("img")
                title = img.get("alt", "").strip() if img else a.get_text(" ", strip=True)
                title = _TITLE_DUB_HD_RE.sub("", title).strip()
                title = _TITLE_YEAR_RE.sub("", title).strip()
                title = _TITLE_LEG_RE.sub("", title).strip()
                if title and href:
                    results.append(AnimeMetadata(title=title, url=href, source=self.name))
        except httpx.HTTPError as e:
            log_scraper_http_failure(logger, "AnRoll", "search_anime", e)
        return results

    def search_episodes(self, anime: str, url: str, params: dict | None) -> list[ScrapedEpisodes]:
        _ = params
        try:
            response = http_get_with_retry(
                url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True
            )
            soup = BeautifulSoup(response.text, "html.parser")
            titles = []
            urls = []
            for a in soup.select("a.ep-text-item"):
                href = str(a.get("href", ""))
                ep_num = a.get("data-ep", "")
                if not href or not ep_num:
                    continue
                if not href.startswith("http"):
                    href = BASE_URL + href
                label = f"Ep.{int(ep_num):03d}"
                titles.append(label)
                urls.append(href)
            if not titles:
                seen: set[str] = set()
                for anchor in soup.select(".episodes a[href*='/episodios/']"):
                    href = urljoin(BASE_URL, str(anchor.get("href", "")))
                    if href in seen:
                        continue
                    match = _EPISODE_NUMBER_RE.search(anchor.get_text(" ", strip=True))
                    if not match:
                        match = re.search(r"-episodio-(\d+)/?$", urlparse(href).path, re.I)
                    if not match:
                        continue
                    seen.add(href)
                    titles.append(f"Episódio {int(match.group(1))}")
                    urls.append(href)
            if not titles:
                first_ep_url = self._find_first_episode_url(soup)
                if first_ep_url:
                    titles, urls = self._episodes_from_sidebar(first_ep_url)
            if titles and urls:
                return [ScrapedEpisodes(titles=titles, urls=urls, source=self.name)]
            return []
        except httpx.HTTPError as e:
            log_scraper_http_failure(logger, "AnRoll", "search_episodes", e)
            return []

    def _find_first_episode_url(self, soup: BeautifulSoup) -> str | None:
        """Return the 'Primeiro Episódio' link from the anime page."""
        for anchor in soup.find_all("a", href=True):
            if "Primeiro" not in anchor.get_text(strip=True):
                continue
            href = str(anchor["href"])
            if re.search(r"/\d+/?$", href):
                return href if href.startswith("http") else f"{BASE_URL}{href}"
        return None

    def _episodes_from_sidebar(self, first_ep_url: str) -> tuple[list[str], list[str]]:
        """Fallback: scrape the episode sidebar from the first episode page.

        Anroll post IDs are global (not sequential per anime). The old range()
        fallback treated last_id - first_id as episode count, inflating lists to
        thousands. The sidebar on any episode page lists all episodes in order.
        """
        response = http_get_with_retry(
            first_ep_url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        soup = BeautifulSoup(response.text, "html.parser")

        sidebar = soup.select_one(".ep-list-box")
        if sidebar is None:
            return [], []

        titles: list[str] = []
        urls: list[str] = []
        seen: set[str] = set()
        for anchor in sidebar.find_all("a", href=True):
            href = str(anchor["href"])
            if not re.match(r"https://(?:anroll\.io|anroll\.cc)/\d+/?$", href):
                continue
            if href in seen:
                continue
            seen.add(href)
            ep_num = anchor.get("data-ep") or len(urls) + 1
            try:
                label = f"Ep.{int(ep_num):03d}"
            except ValueError:
                label = f"Ep.{len(urls) + 1:03d}"
            titles.append(label)
            urls.append(href)

        return titles, urls

    def search_player_src(self, url: str, container: list, event) -> None:
        if urlparse(url).hostname == urlparse(BASE_URL).hostname:
            self._search_dooplay_player_src(url, container, event)
            if container:
                return
            raise ValueError("AnRoll: no playable Blogger source found")

        # The anidrive player serves a "Bot Detected" placeholder (pro.mp4) unless
        # the page is loaded inside the trusted anroll parent (passing the Cloudflare
        # challenge sets the cookies that unlock the real googlevideo sources).
        # The real URL is also bound to the requesting User-Agent, so Selenium must
        # use the SAME UA the video player (mpv) will replay it with.
        from selenium.webdriver.common.by import By

        try:
            with SeleniumWebDriver(user_agent=HEADERS["User-Agent"]) as driver:
                driver.driver.get(url)
                time.sleep(5)  # allow Cloudflare challenge + iframe to load

                iframe = None
                for f in driver.driver.find_elements(By.TAG_NAME, "iframe"):
                    if "anidrive" in (f.get_attribute("src") or ""):
                        iframe = f
                        break
                if iframe is None:
                    raise ValueError("Anroll: anidrive iframe not found on episode page")
                driver.driver.switch_to.frame(iframe)

                video_url = None
                for _ in range(40):
                    if event.is_set():
                        return
                    sources = driver.driver.execute_script("""
                        try {
                            var pl = jwplayer().getPlaylist();
                            if (pl && pl[0] && pl[0].sources)
                                return pl[0].sources.map(function(s){ return s.file; });
                        } catch(e) { return null; }
                        return null;
                    """)
                    if sources:
                        real = [s for s in sources if s and "pro.mp4" not in s]
                        if real:
                            video_url = real[0]
                            break
                    time.sleep(0.5)

            if not video_url:
                raise ValueError("Anroll: real video source not resolved (bot detected)")

            if store_player_source(container, event, video_url):
                return

            raise ValueError("Anroll: failed to store video source")
        except Exception as e:
            raise type(e)(f"Anroll: {e}") from e

    def _search_dooplay_player_src(self, url: str, container: list, event) -> None:
        """Resolve current AnRoll Dooplay player options without launching a browser."""
        response = http_get_with_retry(
            url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True
        )
        soup = BeautifulSoup(response.text, "html.parser")
        options = soup.select("#playeroptionsul li.dooplay_player_option")
        for option in options:
            if event.is_set():
                return
            post_id = option.get("data-post", "")
            player_type = option.get("data-type", "")
            source_number = option.get("data-nume", "")
            if not (post_id.isdigit() and player_type and source_number.isdigit()):
                continue

            api_url = urljoin(
                BASE_URL,
                f"/wp-json/dooplayer/v2/{post_id}/{player_type}/{source_number}",
            )
            try:
                api_response = http_get_with_retry(
                    api_url,
                    headers={**HEADERS, "Referer": url},
                    timeout=REQUEST_TIMEOUT,
                    follow_redirects=True,
                )
                player_data = api_response.json()
                embed_url = player_data.get("embed_url", "")
                if urlparse(embed_url).hostname != urlparse(BASE_URL).hostname:
                    continue

                embed_response = http_get_with_retry(
                    embed_url,
                    headers={**HEADERS, "Referer": url},
                    timeout=REQUEST_TIMEOUT,
                    follow_redirects=True,
                )
                player_soup = BeautifulSoup(embed_response.text, "html.parser")
                player_script = next(
                    (
                        script.string or script.get_text()
                        for script in player_soup.find_all("script")
                        if "var jw" in (script.string or script.get_text())
                    ),
                    "",
                )
                config_match = re.search(r"var\s+jw\s*=\s*", player_script)
                if not config_match:
                    continue
                config, _ = json.JSONDecoder().raw_decode(player_script[config_match.end() :])
                encoded_token = config.get("file", "")
                if not encoded_token:
                    continue
                decoded_token = base64.b64decode(encoded_token).decode("utf-8")[::-1]
                video_url = resolve_blogger_token(decoded_token)
            except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
                logger.debug(f"AnRoll Dooplay player option could not be resolved: {e}")
                continue
            except Exception as e:
                logger.debug(f"AnRoll Blogger source could not be resolved: {e}")
                continue

            store_player_source(container, event, video_url)


def load(register) -> None:
    load_plugin(AnRoll, register)
