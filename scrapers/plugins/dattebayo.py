import re

import requests
from bs4 import BeautifulSoup

from scrapers.core.selenium_driver import SeleniumWebDriver
from services.repository import rep

BASE_URL = "https://www.dattebayo-br.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
}
REQUEST_TIMEOUT = 30


def _extract_episode_number(text: str) -> int:
    match = re.search(r"epis[oó]dio\s*(\d+)", text.lower())
    if match:
        return int(match.group(1))
    match = re.search(r"\bep\s*(\d+)\b", text.lower())
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)", text)
    if match:
        return int(match.group(1))
    return 0


class DattebayoBR:
    languages = ["pt-br"]
    name = "dattebayo"
    base_url = BASE_URL

    def search_anime(self, query: str) -> None:
        url = f"{BASE_URL}/busca?busca={requests.utils.quote(query)}"
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        for item in soup.select(".ultimosAnimesHomeItem"):
            anchor = item.select_one("a")
            if not anchor:
                continue
            href = str(anchor.get("href", ""))
            if not href.startswith("http"):
                href = BASE_URL + href
            title_el = item.select_one(".ultimosAnimesHomeItemInfosNome")
            title = title_el.text.strip() if title_el else ""
            if title and href:
                rep.add_anime(title, href, self.name)

    def search_episodes(self, anime: str, url: str, params: dict | None) -> None:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        items = soup.select(".ultimosEpisodiosHomeItem")
        titles = []
        urls = []
        for item in items:
            anchor = item.select_one("a")
            if not anchor:
                continue
            href = str(anchor.get("href", ""))
            if not href.startswith("http"):
                href = BASE_URL + href
            name_el = item.select_one(".ultimosEpisodiosHomeItemInfosNome")
            title = name_el.text.strip() if name_el else anchor.get("title", "")
            if title and href:
                titles.append(title)
                urls.append(href)

        # Dedup by episode number (keep first occurrence), skip episode 0, sort ascending
        seen = set()
        deduped = []
        for t, u in zip(titles, urls):
            n = _extract_episode_number(t)
            if n > 0 and n not in seen:
                seen.add(n)
                deduped.append((t, u))
        paired = sorted(deduped, key=lambda x: _extract_episode_number(x[0]))
        if paired:
            titles, urls = zip(*paired)
            rep.add_episode_list(anime, list(titles), list(urls), self.name)

    def search_player_src(self, url: str, container: list, event) -> None:
        # JWPlayer builds the signed video URL via JS at runtime.
        # The rendered <video> src (inside #jwContainer_2) contains the final signed URL.
        try:
            with SeleniumWebDriver() as driver:
                driver.fetch(url, wait_selector="#jwContainer_0 video")
                candidates = driver.driver.execute_script("""
                    var containers = ['jwContainer_2', 'jwContainer_1', 'jwContainer_0'];
                    var urls = [];
                    for (var i = 0; i < containers.length; i++) {
                        try {
                            var f = jwplayer(containers[i]).getPlaylistItem().file;
                            if (f) urls.push(f);
                        } catch(e) {}
                    }
                    return urls;
                """)

            for candidate in candidates:
                try:
                    r = requests.get(
                        candidate,
                        headers={**HEADERS, "Range": "bytes=0-0"},
                        timeout=10,
                        stream=True,
                    )
                    if r.status_code in (200, 206):
                        if not event.is_set():
                            container.append(candidate)
                            event.set()
                        return
                except Exception:
                    continue

        except Exception as e:
            raise Exception(f"Could not extract video from DattebayoBR: {e}") from e


def load(languages_dict) -> None:
    can_load = any(lang in languages_dict for lang in DattebayoBR.languages)
    if not can_load:
        return
    rep.register(DattebayoBR())
