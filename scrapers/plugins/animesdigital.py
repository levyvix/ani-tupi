"""AnimesDigital scraper plugin.

CRITICAL REQUIREMENT: When fetching episode lists from AnimesDigital series pages,
the ?odr=1 parameter MUST be present in the URL. Without this parameter,
episodes will not be displayed on the page and cannot be fetched.

The parameter enables proper episode ordering from 1 to end.
"""

import asyncio
import base64
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup
from thefuzz import fuzz

from scrapers.core.selenium_driver import SeleniumWebDriver
from scrapers.plugins.utils import load_plugin, store_player_source
from services.repository import rep

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30
API_URL = "https://animesdigital.org/func/listanime"
API_TOKEN = "c1deb78cd4"

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0"

BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Referer": "https://animesdigital.org",
}

API_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://animesdigital.org",
    "Connection": "keep-alive",
    "Referer": "https://animesdigital.org/animes-legendados-online",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


def _ensure_odr_param(url: str) -> str:
    if "odr=" in url:
        return url
    return url + ("&odr=1" if "?" in url else "?odr=1")


def _strip_audio_marker(title: str) -> str:
    return title.replace(" Dublado", "").replace(" dublado", "").strip()


def _parse_link_from_fragment(html: str) -> tuple[str, str] | None:
    soup = BeautifulSoup(html, "html.parser")
    link = soup.find("a", href=True)
    if not link:
        return None
    url = link.get("href")
    title_elem = link.find("span", class_="title_anime")
    title = title_elem.get_text(strip=True) if title_elem else ""
    if title and url:
        return title, url
    return None


class AnimeResult(TypedDict):
    title: str
    url: str
    image: str


class AnimesDigital:
    languages = ["pt-br"]
    name = "animesdigital"

    def _search_api(
        self, query: str, page: int = 1, limit: int = 200, audio_type: str = "legendado"
    ) -> tuple[list[AnimeResult], dict]:
        filters = {
            "filter_data": f"filter_letter=0&type_url=animes&filter_audio={audio_type}&filter_order=name",
            "filter_genre_add": [],
            "filter_genre_del": [],
        }
        payload = {
            "token": API_TOKEN,
            "pagina": str(page),
            "search": query,
            "limit": str(limit),
            "type": "lista",
            "filters": json.dumps(filters),
        }
        try:
            response = requests.post(
                API_URL, data=payload, headers=API_HEADERS, timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
            results = self._parse_html_results(data.get("results", []))
            metadata = {
                "page": data.get("page"),
                "total_results": data.get("total_results"),
                "total_page": data.get("total_page"),
            }
            return results, metadata
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ AnimesDigital API request failed for '{query}': {e}")
            return [], {}
        except json.JSONDecodeError as e:
            logger.error(f"❌ AnimesDigital failed to parse API response for '{query}': {e}")
            return [], {}

    def _parse_html_results(self, html_fragments: list[str]) -> list[AnimeResult]:
        results = []
        for html in html_fragments:
            try:
                parsed = _parse_link_from_fragment(html)
                if not parsed:
                    continue
                title, url = parsed
                soup = BeautifulSoup(html, "html.parser")
                link = soup.find("a", href=True)
                img = link.find("img") if link else None
                image = img.get("src") if img else ""
                results.append({"title": title, "url": url, "image": image})
            except Exception as e:
                logger.debug(f"Failed to parse HTML fragment: {e}")
        return results

    def _normalize_title_for_slug(self, title: str) -> str:
        normalized = re.sub(
            r"\s+(\d+)(?:nd|st|th|rd)\s+season\b", r" \1", title, flags=re.IGNORECASE
        )
        normalized = re.sub(r"\bseason\s+(\d+)\b", r"\1", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"[^a-zA-Z0-9\s]", "", normalized)
        normalized = " ".join(normalized.split())
        return normalized.lower().replace(" ", "-")

    def _extract_series_url(self, episode_url: str) -> str | None:
        try:
            resp = requests.get(episode_url, headers=BROWSER_HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            link = soup.select_one("div.epsL a[href*='/anime/a/']")
            if link:
                href = link.get("href")
                if href and not href.startswith("http"):
                    href = f"https://animesdigital.org{href}"
                return href
        except Exception as e:
            logger.debug(f"Failed to extract series URL from {episode_url}: {e}")
        return None

    def _merge_into(
        self,
        all_anime: dict,
        normalized: str,
        audio_type: str,
        url: str,
        image: str = "",
    ) -> None:
        if normalized not in all_anime:
            all_anime[normalized] = {
                "base_title": normalized,
                "legendado": None,
                "dublado": None,
                "image": image,
            }
        all_anime[normalized][audio_type] = url

    def _collect_api_results(self, query_words: list[str]) -> dict:
        all_anime: dict = {}
        for word_count in range(1, len(query_words) + 1):
            incremental_query = " ".join(query_words[:word_count])
            try:
                for audio_type in ["legendado", "dublado"]:
                    results, _ = self._search_api(incremental_query, audio_type=audio_type)
                    for result in results:
                        normalized = _strip_audio_marker(result["title"])
                        self._merge_into(
                            all_anime,
                            normalized,
                            audio_type,
                            result["url"],
                            result.get("image", ""),
                        )
            except Exception as e:
                logger.error(f"❌ AnimesDigital API search failed for '{incremental_query}': {e}")
        return all_anime

    def _collect_homepage_results(self, query_words: list[str]) -> dict:
        all_anime: dict = {}
        for word_count in range(1, len(query_words) + 1):
            incremental_query = " ".join(query_words[:word_count])
            for audio_type in ["legendado", "dublado"]:
                homepage_results = self.search_homepage_incremental(
                    incremental_query, audio_type=audio_type
                )
                seen_titles: set[str] = set()
                for ep in homepage_results:
                    title = ep.get("anime_title", "")
                    episode_url = ep.get("episode_url", "")
                    if not title or not episode_url or title in seen_titles:
                        continue
                    seen_titles.add(title)
                    series_url = self._extract_series_url(episode_url)
                    if series_url:
                        normalized = _strip_audio_marker(title)
                        self._merge_into(all_anime, normalized, audio_type, series_url)
                    else:
                        logger.debug(
                            f"Could not extract series URL for '{title}' from {episode_url}"
                        )
        return all_anime

    def _collect_slug_results(self, query: str) -> dict:
        all_anime: dict = {}
        complete_slug = self._normalize_title_for_slug(query)
        for audio_type in ["legendado", "dublado"]:
            slug = complete_slug if audio_type == "legendado" else f"{complete_slug}-dublado"
            url = _ensure_odr_param(f"https://animesdigital.org/anime/a/{slug}")
            try:
                try:
                    loop = asyncio.get_running_loop()
                    with ThreadPoolExecutor(max_workers=1) as executor:

                        def _fetch_url(u: str = url) -> object:
                            with SeleniumWebDriver() as driver:
                                return driver.fetch(u)

                        tree = loop.run_until_complete(loop.run_in_executor(executor, _fetch_url))
                except RuntimeError:
                    with SeleniumWebDriver() as driver:
                        tree = driver.fetch(url)

                if tree.select("div.item_ep"):
                    self._merge_into(all_anime, query, audio_type, url)
            except Exception as e:
                logger.debug(f"Complete slug failed for '{slug}': {e}")
        return all_anime

    def _add_deduplicated(self, all_anime: dict) -> None:
        seen_urls: set[str] = set()
        for data in all_anime.values():
            legendado_url = data["legendado"]
            dublado_url = data["dublado"]
            keep_legendado = legendado_url and legendado_url not in seen_urls
            keep_dublado = dublado_url and dublado_url not in seen_urls
            if keep_legendado:
                seen_urls.add(legendado_url)
                rep.add_anime(data["base_title"], legendado_url, AnimesDigital.name)
            if keep_dublado:
                seen_urls.add(dublado_url)
                rep.add_anime(f"{data['base_title']} Dublado", dublado_url, AnimesDigital.name)

    def search_anime(self, query: str) -> None:
        query_words = query.lower().split()
        all_anime = self._collect_api_results(query_words)

        for normalized, data in self._collect_homepage_results(query_words).items():
            if normalized not in all_anime:
                all_anime[normalized] = data
            else:
                for audio_type in ["legendado", "dublado"]:
                    if not all_anime[normalized][audio_type]:
                        all_anime[normalized][audio_type] = data[audio_type]

        if not all_anime:
            all_anime = self._collect_slug_results(query)

        self._add_deduplicated(all_anime)

    def _search_episodes_with_audio(
        self, search_query: str, audio_type: str = "dublado"
    ) -> list[dict]:
        payload = {
            "token": API_TOKEN,
            "search": search_query,
            "type": "lista",
            "filter_audio": audio_type,
            "limit": "200",
        }
        try:
            response = requests.post(
                API_URL, data=payload, headers=API_HEADERS, timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_episode_results(data.get("results", []))
        except Exception as e:
            logger.debug(f"Search failed for audio_type={audio_type}: {e}")
            return []

    def search_episodes(self, anime: str, url: str, params: dict | None) -> None:
        try:
            self._scrape_series_page(anime, url)

            animesdigital_urls = []
            for urls_list, source in rep.anime_episodes_urls.get(anime, []):
                if source == AnimesDigital.name:
                    animesdigital_urls = list(urls_list)
                    break

            audio_type = "dublado" if "dublado" in anime.lower() else "legendado"
            homepage_episodes = self.search_homepage_incremental(anime, audio_type=audio_type)

            if homepage_episodes:
                self._merge_homepage_episodes(
                    anime, animesdigital_urls, homepage_episodes, len(animesdigital_urls)
                )
        except Exception as e:
            logger.debug(f"AnimesDigital series page scraping failed for '{anime}': {e}")

    def _merge_homepage_episodes(
        self,
        anime: str,
        current_urls: list[str],
        homepage_episodes: list[dict],
        max_episode_on_page: int = 0,
    ) -> None:
        try:
            current_urls_set = set(current_urls)
            new_episodes = [
                ep
                for ep in homepage_episodes
                if ep["episode_url"] not in current_urls_set
                and ep["episode_number"] > max_episode_on_page
            ]

            if not new_episodes:
                return

            new_titles = [
                f"{ep['anime_title']} Episódio {ep['episode_number']}"
                if ep.get("anime_title")
                else f"Episódio {ep['episode_number']}"
                for ep in new_episodes
            ]
            new_urls = [ep["episode_url"] for ep in new_episodes]

            all_titles = [f"{anime} Episódio {i + 1}" for i in range(len(current_urls))]
            all_titles.extend(new_titles)
            rep.add_episode_list(anime, all_titles, current_urls + new_urls, AnimesDigital.name)
        except Exception as e:
            logger.debug(f"Error merging homepage episodes: {e}")

    def _parse_episode_results(self, html_fragments: list[str]) -> list[dict]:
        results = []
        seen_urls: set[str] = set()

        for html in html_fragments:
            try:
                parsed = _parse_link_from_fragment(html)
                if not parsed:
                    continue
                title, url = parsed
                if url in seen_urls:
                    continue
                if re.search(r"Episódio\s+\d+\.\d+", title):
                    continue
                ep_match = re.search(r"Episódio\s+(\d+)", title)
                ep_number = int(ep_match.group(1)) if ep_match else float("inf")
                results.append({"title": title, "url": url, "_ep_number": ep_number})
                seen_urls.add(url)
            except Exception as e:
                logger.debug(f"Failed to parse episode HTML fragment: {e}")

        results.sort(key=lambda x: x["_ep_number"])
        for r in results:
            del r["_ep_number"]
        return results

    def _scrape_series_page(self, anime: str, url: str) -> None:
        url = _ensure_odr_param(url)
        response = requests.get(url, headers=BROWSER_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        tree = BeautifulSoup(response.text, "html.parser")

        episode_titles: list[str] = []
        episode_urls: list[str] = []
        seen_urls: set[str] = set()

        for ep_div in tree.select("div.item_ep"):
            link = ep_div.select_one("a")
            if not link:
                continue
            href = link.get("href")
            title_elem = ep_div.select_one(".title_anime")
            if not (title_elem and href):
                continue
            title = " ".join(str(title_elem.text).split())
            if not title or re.search(r"Episódio\s+\d+\.\d+", title) or href in seen_urls:
                continue
            seen_urls.add(href)
            episode_urls.append(href)
            episode_titles.append(title)

        if episode_titles:
            rep.add_episode_list(anime, episode_titles, episode_urls, AnimesDigital.name)
        else:
            logger.debug(f"No episodes found for '{anime}' in series page scraping")

    def search_player_src(self, url: str, container: list, event) -> None:
        try:
            response = requests.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            html_content = response.text

            hls_url = None
            hls_match = re.search(
                r'https://api\.anivideo\.net/videohls\.php\?d=([^"<>&\s]+)', html_content
            )
            if hls_match:
                hls_url = unquote(hls_match.group(1))

            mp4_decoded = None
            mp4_encoded = None
            for mp4_url in re.findall(r'https://[^"<>\s]+\.mp4(?:[^\s"<>]*)?', html_content):
                if "animesdigital.org/" in mp4_url and "aHR0cHM6Ly9" in mp4_url:
                    mp4_encoded = mp4_url
                    match = re.search(r"animesdigital\.org/([A-Za-z0-9+/]+={0,2})/", mp4_url)
                    if match:
                        try:
                            mp4_decoded = base64.b64decode(match.group(1)).decode("utf-8")
                        except Exception:
                            pass
                    break

            selected_url = hls_url or mp4_decoded or mp4_encoded
            if selected_url and store_player_source(container, event, selected_url):
                return

            logger.debug("No direct video sources found, falling back to iframe method")
            self._extract_iframe_src(html_content, container, event)

        except Exception as e:
            raise Exception(f"Could not extract video from AnimesDigital: {e}") from e

    def _extract_iframe_src(self, html_content: str, container: list, event) -> None:
        try:
            iframe_matches = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html_content)
            for src in iframe_matches:
                if "api.anivideo" in src:
                    if store_player_source(container, event, src):
                        return
            if iframe_matches:
                store_player_source(container, event, iframe_matches[0])
        except Exception as e:
            logger.debug(f"Could not extract iframe src: {e}")

    def _fetch_homepage_episodes(self) -> list[dict]:
        response = requests.get(
            "https://animesdigital.org/home",
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        all_episodes = []
        seen_urls: set[str] = set()

        for link in soup.find_all("a", href=re.compile(r"/video/a/")):
            try:
                url = link.get("href", "")
                if not url.startswith("http"):
                    url = f"https://animesdigital.org{url}"
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                img = link.find("img")
                if not img:
                    continue
                full_title = img.get("title", "")
                if not full_title:
                    continue

                match = re.search(r"Episódio\s+(\d+)", full_title)
                if not match:
                    continue
                episode_number = int(match.group(1))
                anime_name = re.sub(r"\s*Episódio\s+\d+.*", "", full_title).strip()
                anime_name = re.sub(r"^Assistir\s+", "", anime_name).strip()

                if anime_name and episode_number > 0:
                    all_episodes.append(
                        {
                            "anime_title": anime_name,
                            "episode_number": episode_number,
                            "episode_url": url,
                        }
                    )
            except Exception as e:
                logger.debug(f"Error parsing episode link: {e}")

        return all_episodes

    def _incremental_fuzzy_match(
        self, episodes: list[dict], title: str
    ) -> list[tuple[int, str, dict]]:
        query_words = title.lower().split()
        best_matches: list[tuple[int, dict]] = []

        for word_count in range(1, len(query_words) + 1):
            search_query = " ".join(query_words[:word_count])
            current_matches = []

            for ep in episodes:
                anime_title_lower = ep["anime_title"].lower()
                if word_count == 1:
                    score = fuzz.partial_ratio(search_query, anime_title_lower)
                    threshold = 70
                else:
                    score = max(
                        fuzz.ratio(search_query, anime_title_lower),
                        fuzz.partial_ratio(search_query, anime_title_lower),
                    )
                    threshold = 65
                if score >= threshold:
                    current_matches.append((score, ep))

            if current_matches:
                current_matches.sort(key=lambda x: x[0], reverse=True)
                best_matches = current_matches
                top_score = best_matches[0][0]
                stop_threshold = 90 if word_count == 1 else 95
                if top_score > stop_threshold or word_count == len(query_words):
                    break

        final_query = " ".join(query_words)
        matched = []
        for _, ep in best_matches[:5]:
            final_score = max(
                fuzz.ratio(final_query, ep["anime_title"].lower()),
                fuzz.partial_ratio(final_query, ep["anime_title"].lower()),
            )
            if final_score >= 75:
                matched.append((final_score, ep["anime_title"], ep))
        return matched

    def _filter_by_audio(
        self, matches: list[tuple[int, str, dict]], audio_type: str
    ) -> list[tuple[int, str, dict]]:
        filtered = []
        for score, anime_title, ep in matches:
            is_dubbed = "dublado" in ep["anime_title"].lower()
            if audio_type == "dublado" and is_dubbed:
                filtered.append((score, anime_title, ep))
            elif audio_type != "dublado" and not is_dubbed:
                filtered.append((score, anime_title, ep))
        return filtered

    def search_homepage_incremental(self, title: str, audio_type: str = "legendado") -> list[dict]:
        try:
            all_episodes = self._fetch_homepage_episodes()
            if not all_episodes:
                logger.debug("No parseable episodes found on homepage")
                return []

            matched = self._incremental_fuzzy_match(all_episodes, title)
            matched = self._filter_by_audio(matched, audio_type)

            if not matched:
                return []

            anime_scores: dict[str, int] = {}
            for score, anime_title, _ in matched:
                if anime_title not in anime_scores or score > anime_scores[anime_title]:
                    anime_scores[anime_title] = score
            best_anime = max(anime_scores.items(), key=lambda x: x[1])[0]
            result = [ep for _, anime, ep in matched if anime == best_anime]
            result.sort(key=lambda ep: ep["episode_number"])

            logger.debug(
                f"AnimesDigital homepage search for '{title}': found {len(result)} episodes"
            )
            return result

        except requests.exceptions.Timeout:
            logger.debug("AnimesDigital homepage fetch timed out")
            return []
        except Exception as e:
            logger.debug(f"Error searching AnimesDigital homepage: {e}")
            return []


def load() -> None:
    load_plugin(AnimesDigital, rep.register)
