"""Dattebayo BR scraper — search, episode listing, and signed R2 playback URLs."""

from __future__ import annotations

import re
import urllib.parse
from utils.logging import get_logger

import httpx
from bs4 import BeautifulSoup

from models.models import AnimeMetadata, ScrapedEpisodes
from scrapers.plugins.utils import DEFAULT_HEADERS, load_plugin, store_player_source

logger = get_logger(__name__)

BASE_URL = "https://www.dattebayo-br.com"
R2_BASE = "https://1db850bdcbe958d7be70519d81551be4.r2.cloudflarestorage.com"
SIGN_API = "https://ads.animeyabu.net/"
HEADERS = DEFAULT_HEADERS
REQUEST_TIMEOUT = 20

VIDEO_PATH_RE = re.compile(r"/videos/(\d+)/?")
PLAYER_VIDEO_URL_RE = re.compile(
    r"var\s+vid\s*=\s*(['\"])(https://[^'\"]+\.mp4)\1",
    re.IGNORECASE,
)
R2_HOST_SUFFIX = ".r2.cloudflarestorage.com"
QUALITY_PATHS = {
    "fullhd": "fful",
    "hd": "f333",
    "sd": "fiphonec",
}
PLAYBACK_QUALITIES = ("fullhd", "hd", "sd")


def _extract_episode_number(text: str) -> int:
    lowered = text.lower()
    for pattern in (
        r"epis[oó]dio\s*(\d+)",
        r"\bep\s*(\d+)\b",
        r"(\d+)",
    ):
        if match := re.search(pattern, lowered):
            return int(match.group(1))
    return 0


def _absolute_url(href: str) -> str:
    if href.startswith("http"):
        return href
    return urllib.parse.urljoin(BASE_URL, href)


def _request_headers(referer: str) -> dict[str, str]:
    return {
        **HEADERS,
        "Referer": referer,
        "Origin": BASE_URL,
    }


def extract_video_id(episode_url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(episode_url)
    except ValueError as exc:
        raise ValueError(f"URL de episódio inválida: {episode_url}") from exc

    expected_origin = urllib.parse.urlsplit(BASE_URL)
    match = VIDEO_PATH_RE.fullmatch(parsed.path)
    if (
        parsed.scheme != expected_origin.scheme
        or parsed.netloc != expected_origin.netloc
        or parsed.query
        or parsed.fragment
        or not match
    ):
        raise ValueError(f"URL de episódio inválida: {episode_url}")
    return match.group(1)


def unsigned_video_url(video_id: str, *, quality: str = "fullhd") -> str:
    path = QUALITY_PATHS.get(quality)
    if not path:
        raise ValueError(f"Qualidade inválida: {quality!r}")
    return f"{R2_BASE}/{path}/{video_id}.mp4"


def extract_unsigned_video_urls(
    page_html: str,
    episode_url: str,
    *,
    qualities: tuple[str, ...] = PLAYBACK_QUALITIES,
) -> list[str]:
    """Extract validated R2 video URLs from an episode page, ordered by quality."""
    video_id = extract_video_id(episode_url)
    quality_by_path = {
        QUALITY_PATHS[quality]: quality for quality in qualities if quality in QUALITY_PATHS
    }
    candidates: dict[str, str] = {}

    for match in PLAYER_VIDEO_URL_RE.finditer(page_html):
        candidate = match.group(2)
        try:
            parsed = urllib.parse.urlsplit(candidate)
        except ValueError:
            continue
        host = parsed.hostname or ""
        path_parts = parsed.path.strip("/").split("/")

        if (
            parsed.scheme != "https"
            or not host.endswith(R2_HOST_SUFFIX)
            or parsed.netloc != host
            or parsed.query
            or parsed.fragment
            or len(path_parts) != 2
            or path_parts[1] != f"{video_id}.mp4"
        ):
            continue

        quality = quality_by_path.get(path_parts[0])
        if quality:
            candidates.setdefault(quality, candidate)

    return [candidates[quality] for quality in qualities if quality in candidates]


def sign_video_url(
    client: httpx.Client,
    unsigned_url: str,
    *,
    referer: str,
) -> str:
    sign_url = f"{SIGN_API}?url={urllib.parse.quote(unsigned_url, safe='')}"
    response = client.get(
        sign_url,
        headers=_request_headers(referer),
        follow_redirects=False,
    )
    response.raise_for_status()

    payload = response.json()
    if not payload or not isinstance(payload, list):
        raise ValueError("Resposta inesperada da API de assinatura")

    query = payload[0].get("publicidade")
    if not query:
        raise ValueError("API de assinatura não retornou publicidade")

    return unsigned_url + (query if query.startswith("?") else f"?{query}")


def _is_playable(client: httpx.Client, video_url: str, *, referer: str) -> bool:
    try:
        response = client.get(
            video_url,
            headers={**_request_headers(referer), "Range": "bytes=0-0"},
            timeout=10,
            follow_redirects=False,
        )
        return response.status_code in (200, 206)
    except httpx.HTTPError:
        return False


def resolve_signed_video_url(
    client: httpx.Client,
    episode_url: str,
    *,
    qualities: tuple[str, ...] = PLAYBACK_QUALITIES,
) -> str:
    video_id = extract_video_id(episode_url)

    try:
        response = client.get(
            episode_url,
            headers=_request_headers(episode_url),
            follow_redirects=False,
        )
        response.raise_for_status()
        unsigned_urls = extract_unsigned_video_urls(
            response.text,
            episode_url,
            qualities=qualities,
        )
    except httpx.HTTPError as exc:
        logger.debug("Dattebayo player page failed for %s: %s", video_id, exc)
        unsigned_urls = []

    fallback_urls = [unsigned_video_url(video_id, quality=quality) for quality in qualities]
    unsigned_urls = list(dict.fromkeys([*unsigned_urls, *fallback_urls]))

    quality_by_path = {path: quality for quality, path in QUALITY_PATHS.items()}
    for unsigned in unsigned_urls:
        quality_path = urllib.parse.urlsplit(unsigned).path.strip("/").split("/", 1)[0]
        quality = quality_by_path.get(quality_path, "unknown")
        try:
            signed = sign_video_url(client, unsigned, referer=episode_url)
        except (httpx.HTTPError, ValueError) as exc:
            logger.debug("Dattebayo sign failed for %s (%s): %s", video_id, quality, exc)
            continue
        if _is_playable(client, signed, referer=episode_url):
            return signed
    raise ValueError(f"Nenhuma fonte reproduzível encontrada para {episode_url}")


def _parse_anime_items(soup: BeautifulSoup) -> list[AnimeMetadata]:
    results: list[AnimeMetadata] = []
    seen: set[str] = set()

    for item in soup.select(".ultimosAnimesHomeItem"):
        anchor = item.select_one("a[href*='/animes/']")
        if not anchor:
            continue
        href = _absolute_url(str(anchor.get("href", "")))
        if "/letra/" in href or href in seen:
            continue
        title_el = item.select_one(".ultimosAnimesHomeItemInfosNome")
        title = title_el.get_text(strip=True) if title_el else anchor.get_text(strip=True)
        if title and href:
            seen.add(href)
            results.append(AnimeMetadata(title=title, url=href, source="dattebayo"))
    return results


def _parse_episode_items(soup: BeautifulSoup) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for item in soup.select(".ultimosEpisodiosHomeItem"):
        anchor = item.select_one("a[href*='/videos/']")
        if not anchor:
            continue
        href = _absolute_url(str(anchor.get("href", "")))
        name_el = item.select_one(".ultimosEpisodiosHomeItemInfosNome")
        title = name_el.get_text(strip=True) if name_el else str(anchor.get("title", "")).strip()
        if title and href:
            results.append((title, href))
    return results


class Dattebayo:
    name = "dattebayo"
    base_url = BASE_URL

    def search_anime(self, query: str) -> list[AnimeMetadata]:
        try:
            url = f"{BASE_URL}/busca?busca={urllib.parse.quote(query)}"
            response = httpx.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
            )
            response.raise_for_status()
            return _parse_anime_items(BeautifulSoup(response.text, "html.parser"))
        except httpx.HTTPError as exc:
            logger.debug("Dattebayo search_anime failed for %r: %s", query, exc)
            return []

    def list_animes(self, page: int = 1) -> list[AnimeMetadata]:
        """Lista animes do catálogo (/animes), paginado."""
        try:
            if page <= 1:
                url = f"{BASE_URL}/animes"
            else:
                url = f"{BASE_URL}/animes/page/{page}"
            response = httpx.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
            )
            response.raise_for_status()
            return _parse_anime_items(BeautifulSoup(response.text, "html.parser"))
        except httpx.HTTPError as exc:
            logger.debug("Dattebayo list_animes failed for page %s: %s", page, exc)
            return []

    def _fetch_episode_page(self, url: str) -> list[tuple[str, str]]:
        response = httpx.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        response.raise_for_status()
        return _parse_episode_items(BeautifulSoup(response.text, "html.parser"))

    def search_episodes(self, anime: str, url: str, params: dict | None) -> list[ScrapedEpisodes]:
        _ = params
        try:
            all_items: list[tuple[str, str]] = []
            page = 1
            while True:
                page_url = url if page == 1 else f"{url.rstrip('/')}/page/{page}"
                items = self._fetch_episode_page(page_url)
                if not items:
                    break
                all_items.extend(items)
                page += 1

            seen: set[int] = set()
            deduped: list[tuple[str, str]] = []
            for title, episode_url in all_items:
                number = _extract_episode_number(title)
                if number > 0 and number not in seen:
                    seen.add(number)
                    deduped.append((title, episode_url))

            paired = sorted(deduped, key=lambda item: _extract_episode_number(item[0]))
            if paired:
                titles, urls = zip(*paired, strict=True)
                return [ScrapedEpisodes(titles=list(titles), urls=list(urls), source=self.name)]
            return []
        except httpx.HTTPError as exc:
            logger.debug("Dattebayo search_episodes failed for %r: %s", anime, exc)
            return []

    def search_player_src(self, url: str, container: list, event) -> None:
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
                video_url = resolve_signed_video_url(client, url)
            if store_player_source(container, event, video_url):
                return
            raise ValueError("Falha ao armazenar fonte de vídeo do Dattebayo")
        except Exception as exc:
            raise type(exc)(f"Dattebayo: {exc}") from exc


def load(register) -> None:
    load_plugin(Dattebayo, register)
