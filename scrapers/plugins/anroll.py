from utils.logging import get_logger
import re
import time
import urllib.parse

import httpx
from bs4 import BeautifulSoup

from scrapers.core.selenium_driver import SeleniumWebDriver
from scrapers.plugins.utils import DEFAULT_HEADERS, load_plugin, store_player_source
from models.models import AnimeMetadata
from services.repository import rep

logger = get_logger(__name__)

BASE_URL = "https://anroll.io"
HEADERS = DEFAULT_HEADERS
REQUEST_TIMEOUT = 15

_TITLE_DUB_HD_RE = re.compile(r"^(DUB|LEG)HD")
_TITLE_YEAR_RE = re.compile(r"\s*\d{4}$")
_TITLE_LEG_RE = re.compile(r"\s*\(?Legendado\)?\s*$", re.IGNORECASE)


class AnRoll:
    name = "anroll"
    base_url = BASE_URL

    def search_anime(self, query: str) -> list[AnimeMetadata]:
        results = []
        try:
            url = f"{BASE_URL}/?s={urllib.parse.quote(query)}"
            response = httpx.get(
                url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            for article in soup.select("article.anime-card"):
                a = article.find("a", href=True)
                if not a:
                    continue
                href = str(a.get("href", ""))
                if "/anime/" not in href or "episodio" in href:
                    continue
                img = a.find("img")
                title = img.get("alt", "").strip() if img else a.get_text(strip=True)
                title = _TITLE_DUB_HD_RE.sub("", title).strip()
                title = _TITLE_YEAR_RE.sub("", title).strip()
                title = _TITLE_LEG_RE.sub("", title).strip()
                if title and href:
                    results.append(AnimeMetadata(title=title, url=href, source=self.name))
        except httpx.HTTPError as e:
            logger.debug("anroll search_anime falhou: %s", e)
        return results

    def search_episodes(self, anime: str, url: str, params: dict | None) -> None:
        try:
            response = httpx.get(
                url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True
            )
            response.raise_for_status()
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
                titles, urls = self._episodes_from_range(soup)
            if titles and urls:
                rep.add_episode_list(anime, titles, urls, self.name)
        except httpx.HTTPError as e:
            logger.debug("anroll search_episodes falhou: %s", e)

    def _episodes_from_range(self, soup: BeautifulSoup) -> tuple[list[str], list[str]]:
        """Fallback: episode list is JS-rendered. Derive count from the static
        "Primeiro Episódio" / "Último Episódio" links, whose URLs carry sequential
        numeric ids (e.g. /56004/ .. /56015/ → episodes 1..12)."""
        first_id = last_id = None
        for a in soup.find_all("a", href=True):
            label = a.get_text(strip=True)
            m = re.search(r"/(\d+)/?$", str(a["href"]))
            if not m:
                continue
            if "Primeiro" in label:
                first_id = int(m.group(1))
            elif "Último" in label or "Ultimo" in label:
                last_id = int(m.group(1))
        if first_id is None or last_id is None or last_id < first_id:
            return [], []
        titles, urls = [], []
        for n, ep_id in enumerate(range(first_id, last_id + 1), start=1):
            titles.append(f"Ep.{n:03d}")
            urls.append(f"{BASE_URL}/{ep_id}/")
        return titles, urls

    def search_player_src(self, url: str, container: list, event) -> None:
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


def load() -> None:
    load_plugin(AnRoll, rep.register)
