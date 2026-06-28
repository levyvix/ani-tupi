import re
import urllib.parse

import requests
from bs4 import BeautifulSoup

from scrapers.plugins.utils import load_plugin, store_player_source
from models.models import AnimeMetadata
from services.repository import rep

BASE_URL = "https://www.anroll.info"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Accept-Language": "pt-BR,pt;q=0.9",
}
REQUEST_TIMEOUT = 15


class AnRoll:
    name = "anroll"
    base_url = BASE_URL

    def search_anime(self, query: str) -> list[AnimeMetadata]:
        results = []
        try:
            url = f"{BASE_URL}/search/?q={urllib.parse.quote(query)}"
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.select("a.relative.cursor-pointer.group"):
                href = str(a.get("href", ""))
                if "/anime/" not in href or "episodio" in href:
                    continue
                text = a.get_text(strip=True)
                title = re.sub(r"^(DUB|LEG)HD", "", text).strip()
                title = re.sub(r"\s*\d{4}$", "", title).strip()
                title = re.sub(r"\s*\(?Legendado\)?\s*$", "", title, flags=re.IGNORECASE).strip()
                if title and href:
                    results.append(AnimeMetadata(title=title, url=href, source=self.name))
        except requests.RequestException:
            pass
        return results

    def search_episodes(self, anime: str, url: str, params: dict | None) -> None:
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            titles = []
            urls = []
            for a in soup.find_all("a", href=True):
                href = str(a.get("href", ""))
                m = re.search(r"/temporada-(\d+)/episodio-(\d+)$", href)
                if not m:
                    continue
                if href and not href.startswith("http"):
                    href = BASE_URL + href
                t = int(m.group(1))
                ep = int(m.group(2))
                label = f"T{t:02d} Ep.{ep:03d}"
                titles.append(label)
                urls.append(href)
            if titles and urls:
                rep.add_episode_list(anime, titles, urls, self.name)
        except requests.RequestException:
            pass

    def search_player_src(self, url: str, container: list, event) -> None:
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            text = response.text

            slug_m = re.search(r'slug:\s*"([^"]+)"', text)
            temp_m = re.search(r"temporada:\s*(\d+)", text)
            ep_m = re.search(r"episodio:\s*(\d+)", text)
            fallback_m = re.search(r'FALLBACK_URL\s*=\s*"(https?://[^"]+)"', text)

            if not (slug_m and temp_m and ep_m):
                raise ValueError("urlConfig not found in anroll.info episode page")

            slug = slug_m.group(1)
            temporada = int(temp_m.group(1))
            episodio = int(ep_m.group(1))
            cdn_base = fallback_m.group(1) if fallback_m else "https://forks-animes.telabrasil.shop"

            pt = slug[0].upper()
            temp_num = f"{temporada:02d}"
            ep_num = f"{episodio:02d}"

            stream_url = f"{cdn_base}/{pt}/{slug}/{temp_num}-temporada/{ep_num}/stream.m3u8"

            if store_player_source(container, event, stream_url):
                return

            raise ValueError("Failed to store video source for anroll.info")
        except Exception as e:
            raise type(e)(f"Anroll: {e}") from e


def load() -> None:
    load_plugin(AnRoll, rep.register)
