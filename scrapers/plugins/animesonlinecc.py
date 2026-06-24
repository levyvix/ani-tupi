import re
import urllib.parse

import requests
from bs4 import BeautifulSoup

from scrapers.core.blogger_resolver import resolve_blogger_token
from scrapers.plugins.utils import load_plugin, store_player_source
from services.repository import rep

BASE_URL = "https://animesonlinecc.to"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Accept-Language": "pt-BR,pt;q=0.9",
}
REQUEST_TIMEOUT = 15


class AnimesOnlineCC:
    languages = ["pt-br"]
    name = "animesonlinecc"
    base_url = BASE_URL

    def search_anime(self, query: str) -> None:
        try:
            url = f"{BASE_URL}/search/{urllib.parse.quote(query)}"
            r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for article in soup.select("article"):
                a = article.find("a", href=re.compile(r"/anime/"))
                if not a:
                    continue
                title_el = article.find(["h2", "h3"])
                title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)
                link = a.get("href", "")
                if title and link:
                    rep.add_anime(title, link, self.name)
        except requests.RequestException:
            pass

    def search_episodes(self, anime: str, url: str, params: dict | None) -> None:
        try:
            r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            seen = set()
            titles = []
            urls = []
            for a in soup.find_all("a", href=re.compile(r"/episodio/")):
                ep_url = a.get("href", "")
                num_match = re.search(r"-episodio-(\d+)/?$", ep_url)
                # Skip nav links (no episode number) and relative URLs
                if not ep_url.startswith("http") or not num_match or ep_url in seen:
                    continue
                seen.add(ep_url)
                title = a.get_text(strip=True) or f"Episódio {num_match.group(1)}"
                titles.append(title)
                urls.append(ep_url)

            if titles and urls:
                rep.add_episode_list(anime, titles, urls, self.name)
        except requests.RequestException:
            pass

    def search_player_src(self, url: str, container: list, event) -> None:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        for iframe in soup.find_all("iframe", src=re.compile(r"blogger\.com/video\.g")):
            src = iframe.get("src", "")
            m = re.search(r"token=([^&\s\"']+)", src)
            if not m:
                continue
            token = m.group(1)
            video_url = resolve_blogger_token(token)
            if store_player_source(container, event, video_url):
                return

        raise ValueError("No blogger iframe found in AnimesOnlineCC episode page")


def load() -> None:
    load_plugin(AnimesOnlineCC, rep.register)
