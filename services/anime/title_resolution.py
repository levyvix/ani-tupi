"""Title resolution for manual anime searches."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Protocol

from fuzzywuzzy import fuzz

from models.config import settings
from models.models import AniListAnime, AnimeTitleResolution, JikanAnimeEntry
from services.anilist_service import anilist_client
from services.jikan_client import jikan_client
from services.anime.title_normalization import normalize_search_cache_key
from utils.cache import get_cache
from utils.logging import get_logger

logger = get_logger(__name__)


class TitleResolverProvider(Protocol):
    """Provider interface for external title resolution."""

    name: str

    def resolve(self, query: str) -> AnimeTitleResolution | None:
        """Resolve a user query into a canonical anime title."""
        ...


def _unique_aliases(values: list[str | None]) -> tuple[str, ...]:
    aliases: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        normalized = value.strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        aliases.append(normalized)
    return tuple(aliases)


def _calculate_confidence(query: str, candidates: tuple[str, ...]) -> int:
    if not candidates:
        return 0
    query_text = query.strip().lower()
    return max(
        max(
            fuzz.token_sort_ratio(query_text, candidate.lower()),
            fuzz.WRatio(query_text, candidate.lower()),
        )
        for candidate in candidates
    )


def _run_with_timeout(fn, timeout: float):
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn)
        return future.result(timeout=timeout)


@dataclass(frozen=True)
class AniListTitleResolver:
    """Resolve titles using AniList search results."""

    name: str = "anilist"

    def resolve(self, query: str) -> AnimeTitleResolution | None:
        try:
            results = _run_with_timeout(
                lambda: anilist_client.search_anime(query),
                settings.search.title_resolution_timeout_seconds,
            )
        except FutureTimeoutError:
            logger.warning("AniList title resolution timed out for '%s'", query)
            return None
        except Exception as e:
            logger.warning("AniList title resolution failed for '%s': %s", query, e)
            return None

        if not results:
            return None

        best_match: AniListAnime | None = None
        best_aliases: tuple[str, ...] = ()
        best_confidence = -1

        for result in results:
            aliases = _unique_aliases(
                [
                    result.title.romaji,
                    result.title.english,
                    result.title.native,
                ]
            )
            confidence = _calculate_confidence(query, aliases)
            if confidence > best_confidence:
                best_match = result
                best_aliases = aliases
                best_confidence = confidence

        if best_match is None:
            return None

        resolved_title = (
            best_match.title.romaji or best_match.title.english or best_match.title.native or ""
        ).strip()
        if not resolved_title:
            return None

        return AnimeTitleResolution(
            original_query=query,
            resolved_title=resolved_title,
            provider=self.name,
            confidence=best_confidence,
            aliases=best_aliases,
        )


@dataclass(frozen=True)
class JikanTitleResolver:
    """Resolve titles using Jikan/MAL as fallback."""

    name: str = "jikan"

    def resolve(self, query: str) -> AnimeTitleResolution | None:
        try:
            results = jikan_client.search_anime(query, limit=5)
        except Exception as e:
            logger.warning("Jikan title resolution failed for '%s': %s", query, e)
            return None

        if not results:
            return None

        best_match: JikanAnimeEntry | None = None
        best_aliases: tuple[str, ...] = ()
        best_confidence = -1

        for result in results:
            aliases = _unique_aliases(
                [
                    result.title,
                    result.title_english,
                    result.title_japanese,
                    *result.synonyms,
                    *[
                        title_item.get("title")
                        for title_item in result.titles
                        if isinstance(title_item, dict)
                    ],
                ]
            )
            confidence = _calculate_confidence(query, aliases)
            if confidence > best_confidence:
                best_match = result
                best_aliases = aliases
                best_confidence = confidence

        if best_match is None:
            return None

        resolved_title = (best_match.title or best_match.title_english or "").strip()
        if not resolved_title:
            return None

        return AnimeTitleResolution(
            original_query=query,
            resolved_title=resolved_title,
            provider=self.name,
            confidence=best_confidence,
            aliases=best_aliases,
        )


class AnimeTitleResolver:
    """Resolve anime titles with cache and provider fallback."""

    def __init__(
        self,
        providers: list[TitleResolverProvider] | None = None,
        cache=None,
    ) -> None:
        self.providers = providers or [JikanTitleResolver()]
        self.cache = cache or get_cache()

    def resolve(self, query: str) -> AnimeTitleResolution | None:
        normalized_query = query.strip()
        if not normalized_query or not settings.search.enable_title_resolution:
            return None

        cache_key = self._cache_key(normalized_query)
        cached = self.cache.get(cache_key)
        if cached:
            try:
                result = AnimeTitleResolution.model_validate(cached)
                logger.debug("Using cached title resolution for '%s'", query)
                return result
            except Exception:
                pass

        for provider in self.providers:
            result = provider.resolve(normalized_query)
            if result is None:
                continue
            self.cache.set(
                cache_key,
                result.model_dump(),
                ttl=settings.search.title_resolution_cache_ttl_seconds,
            )
            return result

        return None

    @staticmethod
    def _cache_key(query: str) -> str:
        return f"title-resolution:anime:{normalize_search_cache_key(query, language='any')}"
