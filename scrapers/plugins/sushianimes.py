import re
import urllib.parse
import html

import httpx
from bs4 import BeautifulSoup

from scrapers.plugins.utils import load_plugin, store_player_source
from models.models import AnimeMetadata
from services.repository import rep


BASE_URL = "https://sushianimes.com.br"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.7,en;q=0.3",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}
# Keep this lower than the generic provider timeout so a stalled source
# does not block fallback for too long.
REQUEST_TIMEOUT = 10


def _extract_embed_id(soup: BeautifulSoup) -> str | None:
    """Extract embed ID from known player controls."""
    selectors = [
        ".btn-service.selected[data-embed]",
        "[data-embed]",
        ".play-btn[data-id]",
        "[data-id]",
    ]

    for selector in selectors:
        element = soup.select_one(selector)
        if not element:
            continue

        embed_id = element.get("data-embed") or element.get("data-id")
        if embed_id:
            return str(embed_id).strip()

    return None


def _extract_player_url(embed_html: str) -> str | None:
    """Extract direct player URL from AJAX embed response."""
    patterns = [
        r'var\s+playerEmbed\s*=\s*["\']([^"\']+)["\']',
        r'"file"\s*:\s*"([^"\\]+(?:\\.[^"\\]*)*)"',
        r'https?:\\/\\/[^"\'\s]+\.(?:m3u8|mp4)(?:[^"\'\s]*)',
        r'https?://[^"\'\s]+\.(?:m3u8|mp4)(?:[^"\'\s]*)',
    ]

    for pattern in patterns:
        match = re.search(pattern, embed_html, flags=re.IGNORECASE)
        if not match:
            continue

        player_url = match.group(1) if match.lastindex else match.group(0)
        player_url = html.unescape(player_url)
        player_url = player_url.replace("\\/", "/")
        if player_url.startswith("//"):
            player_url = f"https:{player_url}"

        if player_url.startswith("http://") or player_url.startswith("https://"):
            return player_url

    return None


def _normalize_url(href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return f"{BASE_URL}{href}"


def _extract_season_number(text: str) -> int:
    match = re.search(r"(?:temporada|season)\s*(\d+)", text.lower())
    if match:
        return int(match.group(1))
    match = re.search(r"(?:^|\D)(\d+)(?:º|ª)?\s*(?:temporada|season)", text.lower())
    if match:
        return int(match.group(1))
    match = re.search(r"(?:^|\D)([1-9]\d?)(?:º|ª)?", text.lower())
    if match:
        return int(match.group(1))
    return 1


def _build_result_title(title: str, season: int) -> str:
    normalized = title.strip()
    audio_suffix = ""

    if re.search(r"\bdublado\b", normalized, re.IGNORECASE):
        audio_suffix = " - Dublado"
    elif re.search(r"\blegendado\b", normalized, re.IGNORECASE):
        audio_suffix = " - Legendado"

    base_title = re.sub(r"\s*[(-]?\s*(dublado|legendado)\s*[)]?\s*", " ", normalized, flags=re.I)
    base_title = re.sub(r"\s+", " ", base_title).strip()

    if season > 1:
        return f"{base_title} {season}{audio_suffix}"
    return f"{base_title}{audio_suffix}"


class SushiAnimes:
    name = "sushianimes"
    base_url = BASE_URL

    def _search_page(self, query: str) -> BeautifulSoup:
        url = f"{BASE_URL}/search/{urllib.parse.quote(query)}"
        response = httpx.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    def _fetch_anime_page(self, url: str) -> BeautifulSoup:
        response = httpx.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    def search_anime(self, query: str) -> list[AnimeMetadata]:
        results = []
        try:
            soup = self._search_page(query)
            anime_items = soup.select("#animes .list-movie")

            for item in anime_items:
                anchor = item.select_one("a.list-title") or item.select_one("a.list-media")
                if not anchor:
                    continue

                title = anchor.get_text(strip=True)
                href = anchor.get("href")
                if not title or not href:
                    continue

                anime_url = _normalize_url(href)
                anime_page = self._fetch_anime_page(anime_url)
                season_panes = anime_page.select(".episodes.tab-content .tab-pane[id^='season-']")

                if len(season_panes) <= 1:
                    results.append(
                        AnimeMetadata(
                            title=_build_result_title(title, 1),
                            url=anime_url,
                            source=self.name,
                            params={"season": 1},
                        )
                    )
                    continue

                for pane in season_panes:
                    season_id = pane.get("id", "season-1")
                    season = _extract_season_number(season_id)
                    results.append(
                        AnimeMetadata(
                            title=_build_result_title(title, season),
                            url=anime_url,
                            source=self.name,
                            params={"season": season},
                        )
                    )
        except httpx.HTTPError:
            pass
        return results

    def search_episodes(self, anime: str, url: str, params: dict | None) -> None:
        try:
            response = httpx.get(
                url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            season = None
            if isinstance(params, dict):
                season = params.get("season")
            if not season:
                season = _extract_season_number(anime)

            season_pane = soup.select_one(f".episodes.tab-content .tab-pane#season-{season}")
            if season_pane is None:
                season_pane = soup.select_one(".episodes.tab-content .tab-pane")
            if season_pane is None:
                return

            titles: list[str] = []
            urls: list[str] = []
            for episode in season_pane.select("a[href*='/anime/']"):
                href = episode.get("href")
                if not href:
                    continue

                episode_title = episode.get("title", "").strip()
                name_el = episode.select_one(".name")
                episode_name = name_el.get_text(" ", strip=True) if name_el else ""
                full_title = f"{episode_title} {episode_name}".strip()

                titles.append(full_title)
                urls.append(_normalize_url(href))

            if titles and urls:
                rep.add_episode_list(anime, titles, urls, self.name, season=season)
        except httpx.HTTPError:
            # Avoid leaking thread tracebacks when the site blocks direct requests.
            pass

    def search_player_src(self, url: str, container: list, event) -> None:
        try:
            response = httpx.get(
                url, headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            embed_id = _extract_embed_id(soup)
            if not embed_id:
                raise ValueError(f"No embed ID found in SushiAnimes episode page: {url}")

            ajax_headers = {
                **HEADERS,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": url,
            }

            embed_response = httpx.post(
                f"{BASE_URL}/ajax/embed",
                data={"id": embed_id},
                headers=ajax_headers,
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
            )
            embed_response.raise_for_status()

            player_url = _extract_player_url(embed_response.text)
            if not player_url:
                raise ValueError(f"No player URL found in SushiAnimes embed response for: {url}")
            store_player_source(container, event, player_url)
        except httpx.HTTPError:
            pass


def load() -> None:
    load_plugin(SushiAnimes, rep.register)
