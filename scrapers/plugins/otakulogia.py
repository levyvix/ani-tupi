"""Otakulogia scraper — GraphQL API backed search, episodes and playback.

Unlike the HTML scrapers, otakulogia.com is a SPA that talks to a public
GraphQL API (``https://api.otakulogia.com/graphql``). Video URLs come back as
direct, unsigned MP4 links in the JSON payload — no iframe hop or Blogger token
resolution required.

API surface used (queries return a JSON scalar wrapped in a random key, so the
array is located by scanning the object values):

* ``SearchVideo({searchText})`` -> catalog entries (``cid``, ``category_name``)
* ``CheckTemporada({catId})``    -> season list (``temporadas[].tid``)
* ``VideoByCatId({catId,page,tid?})`` -> episodes (``video_ep``, ``video_url``)
* ``SingleVideo({videoId})``     -> single episode, resolved at playback time
"""

from __future__ import annotations

import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import httpx

from models.models import AnimeMetadata, ScrapedEpisodes
from scrapers.plugins.utils import (
    DEFAULT_HEADERS,
    http_request_with_retry,
    load_plugin,
    store_player_source,
)
from utils.title_normalization import roman_to_int
from utils.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://otakulogia.com"
API_URL = "https://api.otakulogia.com/graphql"
REQUEST_TIMEOUT = 20
MAX_PAGES = 30
LEGACY_SEARCH_MAX_LENGTH = 100

HEADERS = {
    **DEFAULT_HEADERS,
    "Content-Type": "application/json",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/",
}

SEARCH_QUERY = "query SearchVideo($input: SearchInput!){ SearchVideo(input: $input) }"
ANIME_BY_SLUG_QUERY = """query AnimeBySlug($slug: String!) {
    animeBySlug(slug: $slug) {
        id upstreamCid name slug nameEn year status synopsis posterUrl audioMix hasNewEpisode
    }
}"""
ANIME_CATALOG_DETAIL_QUERY = """query AnimeCatalogDetail($upstreamCid: Int!, $upstreamTid: Int) {
    animeCatalogDetail(upstreamCid: $upstreamCid, upstreamTid: $upstreamTid) {
        anime { id upstreamCid name slug }
        seasons { upstreamTid name slug audioType }
        episodes {
            id upstreamId title slug episodeNumber upstreamTempId
            videoUrl videoUrlFhd videoUrlSd videoType audioType
        }
    }
}"""
TEMPORADA_QUERY = "query CheckTemporada($catId: String!){ CheckTemporada(catId: $catId) }"
BYCAT_QUERY = "query VideoByCatId($input: VideoByCatInput!){ VideoByCatId(input: $input) }"
SINGLE_QUERY = "query SingleVideo($input: SingleVideoInput!){ SingleVideo(input: $input) }"

_WATCH_RE = re.compile(r"/watch/(\d+)")
_EP_NUM_RE = re.compile(r"\bEP\.?\s*(\d+)", re.IGNORECASE)
_SEASON_NAME_RE = re.compile(r"(?:temporada|\bt)\s*0*(\d+)", re.IGNORECASE)
_PART_NAME_RE = re.compile(r"\bparte\s+([ivx]+|\d+)\b", re.IGNORECASE)


def _gql(query: str, variables: dict) -> dict | None:
    """Execute a GraphQL query, returning the ``data`` object (or None)."""
    response = http_request_with_retry(
        "POST",
        API_URL,
        headers=HEADERS,
        json={"query": query, "variables": variables},
        timeout=REQUEST_TIMEOUT,
    )
    payload = response.json()
    if payload.get("errors"):
        logger.debug(f"Otakulogia GraphQL errors: {payload['errors'][:1]}")
    return payload.get("data")


def _unwrap(raw) -> list[dict]:
    """Locate the record array inside a JSON-scalar response.

    Responses look like ``{"FAG_ab12": [ {...}, ... ]}`` — the wrapping key is
    random, so the first list of objects among the values is returned.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        for value in raw.values():
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _episode_number(episode: dict, fallback: int) -> int:
    """Parse the episode number from the ``video_ep`` label (e.g. "EP 51 | LEG")."""
    label = str(episode.get("video_ep") or episode.get("video_title") or "")
    match = _EP_NUM_RE.search(label)
    return int(match.group(1)) if match else fallback


def _resolve_cid(url: str, params: dict | None) -> str | None:
    """Recover the catalog id from params first, then the synthetic URL."""
    if isinstance(params, dict) and params.get("cid"):
        return str(params["cid"])
    match = re.search(r"/anime/(\d+)", url)
    return match.group(1) if match else None


def _language_of(name: str) -> str:
    """Return the display language suffix parsed from a temporada name."""
    lowered = name.lower()
    if "dublado" in lowered:
        return "Dublado"
    if "legendado" in lowered:
        return "Legendado"
    return ""


def _effective_season(name: str) -> int | None:
    """Return the user-facing season number parsed from a temporada name.

    Otakulogia splits catalogs either into numbered seasons ("Temporada 02") or
    into parts within a season ("T01: Parte III"). Parts are the progression users
    think of as seasons, so a part number takes precedence; otherwise the temporada
    number is used. Returns None for entries with neither (movies, OVAs, specials).
    """
    part_match = _PART_NAME_RE.search(name)
    if part_match:
        token = part_match.group(1)
        return int(token) if token.isdigit() else roman_to_int(token)
    season_match = _SEASON_NAME_RE.search(name)
    return int(season_match.group(1)) if season_match else None


def _temporada_entry(cid: str, category: str, temp: dict) -> AnimeMetadata:
    """Build one AnimeMetadata for a single temporada (numbered season or movie)."""
    name = str(temp.get("name") or "")
    tid = temp.get("tid")
    language = _language_of(name)
    url = f"{BASE_URL}/anime/{cid}"
    season = _effective_season(name)
    if season is not None:
        # Always anchor on the catalog title: part names like "T01: Parte III"
        # carry no anime name of their own and would otherwise isolate the source.
        if season == 1 and language == "Legendado":
            title = category
        else:
            title = f"{category} Temporada {season}"
        if language and title != category:
            title = f"{title} {language}"
        params = {"cid": cid, "season": season}
        if tid is not None:
            params["tid"] = int(tid)
    else:
        title = name or category
        params = {"cid": cid}
        if tid is not None:
            params["tid"] = int(tid)
    return AnimeMetadata(title=title, url=url, source=Otakulogia.name, params=params)


def _slugify_title(title: str) -> str:
    """Build the public anime route slug used by Otakulogia's current catalog."""
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")


def _metadata_from_slug_search(query: str) -> list[AnimeMetadata]:
    """Resolve an exact title through the current slug-based catalog API.

    The legacy ``SearchVideo`` operation no longer indexes every public anime
    route. ``AnimeBySlug`` does, so use it when the legacy search has no hits.
    """
    slug = _slugify_title(query)
    if not slug:
        return []

    try:
        data = _gql(ANIME_BY_SLUG_QUERY, {"slug": slug})
        anime = (data or {}).get("animeBySlug")
        if not isinstance(anime, dict):
            return []

        cid = anime.get("upstreamCid")
        title = str(anime.get("name") or "").strip()
        anime_slug = str(anime.get("slug") or slug).strip()
        if not cid or not title or not anime_slug:
            return []

        params_base = {"cid": str(cid), "slug": anime_slug}
        try:
            catalog_data = _gql(ANIME_CATALOG_DETAIL_QUERY, {"upstreamCid": int(cid)})
        except httpx.HTTPError as exc:
            logger.debug(f"Otakulogia season lookup failed for {query!r}: {exc}")
            catalog_data = None
        catalog = (catalog_data or {}).get("animeCatalogDetail")
        seasons = catalog.get("seasons") if isinstance(catalog, dict) else None
        if not isinstance(seasons, list) or not seasons:
            return [
                AnimeMetadata(
                    title=title,
                    url=f"{BASE_URL}/anime/{anime_slug}",
                    source=Otakulogia.name,
                    params=params_base,
                )
            ]

        results = []
        for season_data in seasons:
            if not isinstance(season_data, dict):
                continue
            tid = season_data.get("upstreamTid")
            name = str(season_data.get("name") or "").strip()
            if tid is None:
                continue

            language = _language_of(name)
            season = _effective_season(name)
            if season is None:
                display_title = name or title
            elif season == 1 and language == "Legendado":
                display_title = title
            else:
                display_title = f"{title} Temporada {season}"
            if language and display_title != title:
                display_title = f"{display_title} {language}"

            results.append(
                AnimeMetadata(
                    title=display_title,
                    url=f"{BASE_URL}/anime/{anime_slug}",
                    source=Otakulogia.name,
                    params={
                        **params_base,
                        "tid": int(tid),
                        **({"season": season} if season else {}),
                    },
                )
            )

        return results or [
            AnimeMetadata(
                title=title,
                url=f"{BASE_URL}/anime/{anime_slug}",
                source=Otakulogia.name,
                params=params_base,
            )
        ]
    except httpx.HTTPError as exc:
        logger.debug(f"Otakulogia slug search failed for {query!r}: {exc}")
        return []


class Otakulogia:
    name = "otakulogia"
    base_url = BASE_URL

    def _fetch_temporadas(self, cid: str) -> list[dict]:
        """Return the temporada list for a catalog, or [] for a flat catalog.

        Never raises: a per-catalog failure is isolated (logged at debug and
        degraded to []) so one bad catalog cannot abort the whole search.
        """
        try:
            data = _gql(TEMPORADA_QUERY, {"catId": cid})
            info = (data or {}).get("CheckTemporada")
            if isinstance(info, str):
                try:
                    info = json.loads(info)
                except (ValueError, TypeError):
                    info = None
            if not isinstance(info, dict) or not info.get("has_temporada"):
                return []
            return [t for t in (info.get("temporadas") or []) if isinstance(t, dict)]
        except Exception as exc:
            logger.debug(f"Otakulogia CheckTemporada failed for cid {cid}: {exc}")
            return []

    def search_anime(self, query: str) -> list[AnimeMetadata]:
        if len(query) > LEGACY_SEARCH_MAX_LENGTH:
            return _metadata_from_slug_search(query)

        results: list[AnimeMetadata] = []
        try:
            data = _gql(SEARCH_QUERY, {"input": {"searchText": query}})
            catalogs: list[tuple[str, str]] = []
            for entry in _unwrap((data or {}).get("SearchVideo")):
                cid = entry.get("cid")
                title = (entry.get("category_name") or "").strip()
                if cid and title:
                    catalogs.append((str(cid), title))

            if catalogs:
                with ThreadPoolExecutor(max_workers=min(len(catalogs), 8)) as executor:
                    temporada_lists = list(
                        executor.map(lambda pair: self._fetch_temporadas(pair[0]), catalogs)
                    )

                for (cid, title), temporadas in zip(catalogs, temporada_lists):
                    if not temporadas:
                        results.append(
                            AnimeMetadata(
                                title=title,
                                url=f"{BASE_URL}/anime/{cid}",
                                source=self.name,
                                params={"cid": str(cid)},
                            )
                        )
                        continue
                    for temp in temporadas:
                        results.append(_temporada_entry(cid, title, temp))
        except httpx.HTTPError as exc:
            logger.debug(f"Otakulogia search_anime failed for {query!r}: {exc}")
        return results or _metadata_from_slug_search(query)

    def _pick_temporada(self, cid: str, requested_season: int | None) -> tuple[int | None, int]:
        """Return ``(tid, season)`` for the catalog, honoring a requested season.

        Falls back to the first temporada (season inferred from its name) when the
        catalog is split into seasons; returns ``(None, 1)`` for flat catalogs.
        The ``tid`` must be an ``int`` — the API rejects a string-typed season id.
        """
        data = _gql(TEMPORADA_QUERY, {"catId": cid})
        info = (data or {}).get("CheckTemporada")
        if isinstance(info, str):
            try:
                info = json.loads(info)
            except (ValueError, TypeError):
                info = None
        if not isinstance(info, dict) or not info.get("has_temporada"):
            return None, 1

        temporadas = info.get("temporadas") or []
        if not temporadas:
            return None, 1

        def season_of(temp: dict) -> int:
            return _effective_season(str(temp.get("name") or "")) or 1

        if requested_season is not None:
            for temp in temporadas:
                if temp.get("tid") is not None and season_of(temp) == requested_season:
                    return int(temp["tid"]), requested_season

        first = temporadas[0]
        tid = first.get("tid")
        return (int(tid) if tid is not None else None), season_of(first)

    def search_episodes(self, anime: str, url: str, params: dict | None) -> list[ScrapedEpisodes]:
        cid = _resolve_cid(url, params)
        if not cid:
            logger.debug(f"Otakulogia: could not resolve cid from {url!r}")
            return []

        if isinstance(params, dict) and params.get("slug"):
            return self._search_slug_catalog_episodes(anime, cid, params)

        requested_season = None
        tid_param = None
        if isinstance(params, dict):
            if params.get("season"):
                requested_season = int(params["season"])
            if params.get("tid") is not None:
                tid_param = int(params["tid"])

        try:
            if tid_param is not None:
                tid, season = tid_param, (requested_season or 1)
            else:
                tid, season = self._pick_temporada(cid, requested_season)

            episodes: dict[int, str] = {}
            for page in range(1, MAX_PAGES + 1):
                variables = {"catId": cid, "page": page}
                if tid is not None:
                    variables["tid"] = tid
                data = _gql(BYCAT_QUERY, {"input": variables})
                batch = _unwrap((data or {}).get("VideoByCatId"))
                if not batch:
                    break
                for index, episode in enumerate(batch):
                    video_id = episode.get("id")
                    if not video_id:
                        continue
                    number = _episode_number(episode, fallback=len(episodes) + index + 1)
                    episodes.setdefault(number, f"{BASE_URL}/watch/{video_id}")

            if not episodes:
                return []

            ordered = sorted(episodes.items())
            # Otakulogia keeps a continuous episode count across seasons/parts
            # (e.g. season 3 starts at "EP 25"). Rebase to the local minimum so
            # each temporada begins at episode 1, as the UI expects.
            offset = ordered[0][0] - 1
            titles = [f"Episódio {number - offset}" for number, _ in ordered]
            urls = [episode_url for _, episode_url in ordered]
            return [ScrapedEpisodes(titles=titles, urls=urls, source=self.name, season=season)]
        except httpx.HTTPError as exc:
            logger.debug(f"Otakulogia search_episodes failed for {anime!r}: {exc}")
            return []

    def _search_slug_catalog_episodes(
        self, anime: str, cid: str, params: dict
    ) -> list[ScrapedEpisodes]:
        """Load episode URLs from the current catalog API for slug-based results."""
        try:
            variables = {"upstreamCid": int(cid)}
            tid = params.get("tid")
            if tid is not None:
                variables["upstreamTid"] = int(tid)
            data = _gql(ANIME_CATALOG_DETAIL_QUERY, variables)
            catalog = (data or {}).get("animeCatalogDetail")
            if not isinstance(catalog, dict):
                return []

            episodes_by_number: dict[int, str] = {}
            for index, episode in enumerate(catalog.get("episodes") or []):
                if not isinstance(episode, dict):
                    continue
                video_id = episode.get("upstreamId")
                title = str(episode.get("title") or episode.get("video_ep") or "")
                if video_id is None:
                    continue
                number = _episode_number({"video_ep": title}, fallback=index + 1)
                episodes_by_number.setdefault(number, f"{BASE_URL}/watch/{video_id}")

            if not episodes_by_number:
                return []

            ordered = sorted(episodes_by_number.items())
            offset = ordered[0][0] - 1
            titles = [f"Episódio {number - offset}" for number, _ in ordered]
            urls = [episode_url for _, episode_url in ordered]
            season = int(params.get("season") or 1)
            return [ScrapedEpisodes(titles=titles, urls=urls, source=self.name, season=season)]
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            logger.debug(f"Otakulogia catalog episode fetch failed for {anime!r}: {exc}")
            return []

    def search_player_src(self, url: str, container: list, event) -> None:
        try:
            match = _WATCH_RE.search(url)
            if not match:
                raise ValueError(f"URL de episódio inválida: {url}")
            video_id = match.group(1)

            data = _gql(SINGLE_QUERY, {"input": {"videoId": video_id}})
            records = _unwrap((data or {}).get("SingleVideo"))
            if not records:
                raise ValueError(f"SingleVideo não retornou vídeo para {video_id}")

            video = records[0]
            candidates = [
                video.get("video_url_fhd"),
                video.get("video_url"),
                video.get("video_url_sd"),
            ]
            stored = False
            for candidate in candidates:
                if candidate and str(candidate).startswith("http"):
                    if store_player_source(container, event, str(candidate)):
                        stored = True
            if not stored:
                raise ValueError(f"Nenhuma fonte reproduzível para {video_id}")
        except Exception as exc:
            raise type(exc)(f"Otakulogia: {exc}") from exc


def load(register) -> None:
    load_plugin(Otakulogia, register)
