"""Search repository for anime search and deduplication across sources."""

import time
import re
import threading
from typing import Optional
from collections import defaultdict
from os import cpu_count
from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED

from models.config import settings
from models.models import SearchResults, SearchMetadata, AnimeSearchResult
from services.anime.title_normalization import (
    are_language_version_markers_compatible,
    are_season_markers_compatible,
    get_compact_normalized_title_key,
    normalize_search_cache_key,
    normalize_title_for_dedup,
)
from utils.logging import get_logger

logger = get_logger(__name__)


class SearchRepository:
    """Singleton repository for anime search and deduplication.

    Handles:
    - Registering scraper plugins
    - Searching anime across multiple sources
    - Deduplicating results by title normalization
    - Caching search results
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if not SearchRepository._instance:
            SearchRepository._instance = super().__new__(cls)
            SearchRepository._initialized = False
        return SearchRepository._instance

    def __init__(self) -> None:
        if SearchRepository._initialized:
            return

        self.sources = {}
        self.anime_to_urls = defaultdict(list)
        self.norm_titles = {}
        self._last_search_metadata = {}
        self._add_lock = threading.Lock()

        SearchRepository._initialized = True

    @classmethod
    def reset_singleton(cls) -> None:
        """Reset singleton instance for testing. Use only in test fixtures."""
        cls._instance = None
        cls._initialized = False

    def register(self, plugin) -> None:
        self.sources[plugin.name] = plugin

    def get_active_sources(self) -> list[str]:
        return sorted(list(self.sources.keys()))

    def clear_search_results(self) -> None:
        self.anime_to_urls = defaultdict(list)
        self.norm_titles = {}

    def _build_search_results(self, query: str) -> SearchResults:
        results = []
        for title, sources_list in self.anime_to_urls.items():
            normalized_sources = [
                (url, source, params if isinstance(params, dict) else {})
                for url, source, params in sources_list
            ]
            anime = AnimeSearchResult(
                title=title,
                normalized_title=self.norm_titles.get(title, title),
                sources=tuple(normalized_sources),
            )
            results.append(anime)

        ranked = self._rank_search_results(results, query)
        return SearchResults(query=query, results=tuple(ranked), metadata={})

    @staticmethod
    def _strip_dublado(text: str) -> str:
        return text.replace(" dublado ", " ").replace(" dublado", "").replace("dublado ", "")

    @staticmethod
    def _normalize_for_similarity(text: str) -> str:
        text = SearchRepository._normalize_for_filter(text)
        return get_compact_normalized_title_key(SearchRepository._strip_dublado(text))

    @staticmethod
    def _normalize_words_for_similarity(text: str) -> list[str]:
        text = SearchRepository._normalize_for_filter(text)
        return SearchRepository._strip_dublado(text).split()

    @staticmethod
    def _contains_word_sequence(haystack: list[str], needle: list[str]) -> bool:
        if not needle:
            return True
        it = iter(haystack)
        return all(any(word == candidate for candidate in it) for word in needle)

    @staticmethod
    def _extract_numeric_tokens(text: str) -> list[str]:
        return re.findall(r"\d+", text)

    @staticmethod
    def _extract_result_title(result) -> str:
        return result.title if hasattr(result, "title") else result[1]

    @staticmethod
    def _title_features(title: str) -> tuple[str, str, list[str]]:
        norm = SearchRepository._normalize_for_filter(title)
        compact = SearchRepository._normalize_for_similarity(title)
        words = SearchRepository._normalize_words_for_similarity(title)
        return norm, compact, words

    @staticmethod
    def _fuzz_score(norm_a: str, compact_a: str, norm_b: str, compact_b: str) -> int:
        from thefuzz import fuzz

        return max(
            fuzz.ratio(norm_a, norm_b),
            fuzz.partial_ratio(norm_a, norm_b),
            fuzz.token_sort_ratio(norm_a, norm_b),
            fuzz.ratio(compact_a, compact_b),
        )

    @staticmethod
    def _apply_word_count_adjustment(score: int, title_words: list, ref_words: list) -> int:
        if len(title_words) < len(ref_words):
            if title_words == ref_words[: len(title_words)]:
                return 0
            return max(0, score - 50)
        elif len(title_words) > len(ref_words):
            return min(100, score + min(30, (len(title_words) - len(ref_words)) * 5))
        return score

    @staticmethod
    def _rank_search_results(
        results: list[AnimeSearchResult], query: str
    ) -> list[AnimeSearchResult]:
        """Rank search results by similarity to query."""
        norm_query, compact_query, query_words = SearchRepository._title_features(query)

        scored = []
        for result in results:
            title = SearchRepository._extract_result_title(result)
            norm_title, compact_title, title_words = SearchRepository._title_features(title)

            score = SearchRepository._fuzz_score(
                norm_query, compact_query, norm_title, compact_title
            )

            if query_words and title_words[: len(query_words)] == query_words:
                score = min(100, score + 45)
            elif query_words and all(w in title_words for w in query_words):
                score = min(100, score + 25)
            elif norm_query in norm_title:
                score = min(100, score + 15)
            elif compact_query in compact_title:
                score = min(100, score + 10)

            score = SearchRepository._apply_word_count_adjustment(score, title_words, query_words)
            is_prefix = int(bool(query_words and title_words[: len(query_words)] == query_words))
            scored.append((result, score, is_prefix, len(title_words), title))

        scored.sort(key=lambda x: (-x[1], -x[2], x[3], x[4]))
        return [x[0] for x in scored]

    @staticmethod
    def _rank_search_results_with_reference(
        results: list[AnimeSearchResult | tuple[str, str]], reference_title: str
    ) -> list[AnimeSearchResult | tuple[str, str]]:
        """Rank results using a canonical reference title."""
        reference_title = reference_title.split(" / ")[0]
        ref_norm, ref_compact, ref_words = SearchRepository._title_features(reference_title)
        ref_numbers = SearchRepository._extract_numeric_tokens(reference_title)

        scored = []
        for result in results:
            title = SearchRepository._extract_result_title(result)
            norm_title, compact_title, title_words = SearchRepository._title_features(title)
            title_numbers = SearchRepository._extract_numeric_tokens(title)

            score = SearchRepository._fuzz_score(ref_norm, ref_compact, norm_title, compact_title)

            if ref_words and title_words[: len(ref_words)] == ref_words:
                score = min(100, score + 40)
            elif ref_norm in norm_title:
                score = min(100, score + 20)
            elif ref_compact in compact_title:
                score = min(100, score + 10)

            if SearchRepository._contains_word_sequence(title_words, ref_words):
                score = min(100, score + 25)
            else:
                score = max(0, score - 25)

            if ref_numbers:
                if all(n in title_numbers for n in ref_numbers):
                    score = min(100, score + 25)
                elif any(n in title_numbers for n in ref_numbers):
                    score = min(100, score + 10)
                else:
                    score = max(0, score - 15)

            score = SearchRepository._apply_word_count_adjustment(score, title_words, ref_words)
            scored.append((result, score, len(title_words), title))

        scored.sort(key=lambda x: (-x[1], x[2], x[3]))
        return [x[0] for x in scored]

    @staticmethod
    def _normalize_for_filter(text: str) -> str:
        text = text.lower()
        for char in ["-", ":", "(", ")", "!", "?", ".", "–", "—"]:
            text = text.replace(char, " ")
        return " ".join(text.split())

    @staticmethod
    def _matches_filter_query(title: str, filter_by_query: str) -> bool:
        query_norm = SearchRepository._normalize_for_filter(filter_by_query)
        title_norm = SearchRepository._normalize_for_filter(title)
        query_compact = get_compact_normalized_title_key(query_norm)
        title_compact = get_compact_normalized_title_key(title_norm)
        query_words = query_norm.split()
        title_words = title_norm.split()
        return (
            query_norm in title_norm
            or query_compact in title_compact
            or all(w in title_words for w in query_words)
        )

    def _sorted_sources(self) -> list[tuple]:
        """Return sources sorted by priority order, then alphabetically."""
        sources = list(self.sources.items())
        priority = settings.plugins.priority_order
        if priority:
            priority_map = {name: i for i, name in enumerate(priority)}
            sources.sort(key=lambda x: priority_map.get(x[0], len(priority)))
        else:
            sources.sort(key=lambda x: x[0])
        return sources

    def _search_with_incremental_results(self, query: str, verbose: bool = True) -> None:
        """Search anime with incremental results respecting configured priority order."""
        if verbose:
            logger.info(f"⠼ Buscando '{query}'...")

        n_cpu = cpu_count() or 10
        executor = ThreadPoolExecutor(max_workers=min(len(self.sources), n_cpu))

        try:
            future_to_source = {
                executor.submit(plugin.search_anime, query): name
                for name, plugin in self._sorted_sources()
            }

            timeout = settings.performance.http_timeout * 6
            done, not_done = wait(
                future_to_source.keys(), timeout=timeout, return_when=ALL_COMPLETED
            )

            if not_done:
                timed_out = [future_to_source[f] for f in not_done]
                if verbose:
                    logger.info(
                        f"\n⚠️  Timeout em {len(timed_out)} fonte(s): {', '.join(timed_out)}"
                    )
                    logger.info(f"   Usando resultados parciais de {len(done)} fonte(s)")
                for future in not_done:
                    future.cancel()

            for future in done:
                source = future_to_source[future]
                try:
                    future.result()
                    if verbose and len(self.sources) > 1:
                        logger.info(f"✓ {source} ({len(self.anime_to_urls)} resultados)", end="\r")
                except Exception as e:
                    if verbose:
                        logger.info(f"❌ Erro em {source}: {e}")

            if verbose and len(self.sources) > 1:
                logger.info(" " * 70 + "\r", end="")

            if verbose:
                count = len(self.anime_to_urls)
                total = len(self.sources)
                if total > 1 and count > 0:
                    logger.info(f"✓ {count} resultado(s) de {total} fonte(s)")
        finally:
            executor.shutdown(wait=True)

    def _try_cache(self, query: str, verbose: bool) -> tuple[dict | None, int]:
        """Check cache for query. Returns (cached_data, check_time_ms)."""
        start = time.time()
        try:
            from utils.cache_manager import get_cache

            cached = get_cache().get(normalize_search_cache_key(query))
        except Exception as e:
            if verbose:
                logger.info(f"⚠️  Erro ao acessar cache: {e}")
            cached = None
        return cached, int((time.time() - start) * 1000)

    def _save_cache(self, query: str, verbose: bool) -> None:
        try:
            from utils.cache_manager import get_cache

            get_cache().set(
                normalize_search_cache_key(query),
                dict(self.anime_to_urls),
                ttl=settings.cache.search_cache_ttl_seconds,
            )
        except Exception as e:
            if verbose:
                logger.info(f"⚠️  Erro ao salvar cache: {e}")

    def _collect_scraper_sources(self) -> list[str]:
        return sorted({src for entries in self.anime_to_urls.values() for _, src, _ in entries})

    def add_anime(self, title: str, url: str, source: str, params: dict | None = None) -> None:
        """Add anime with multi-source deduplication via title normalization."""
        with self._add_lock:
            params = params or {}
            normalized_new = normalize_title_for_dedup(title)
            compact_new = get_compact_normalized_title_key(normalized_new)
            self.norm_titles[title] = normalized_new

            for existing_title in list(self.anime_to_urls):
                existing_norm = self.norm_titles.get(existing_title)
                if existing_norm is None:
                    existing_norm = normalize_title_for_dedup(existing_title)
                    self.norm_titles[existing_title] = existing_norm

                if normalized_new == existing_norm:
                    self.anime_to_urls[existing_title].append((url, source, params))
                    return

                if (
                    compact_new == get_compact_normalized_title_key(existing_norm)
                    and are_language_version_markers_compatible(normalized_new, existing_norm)
                    and are_season_markers_compatible(normalized_new, existing_norm)
                ):
                    self.anime_to_urls[existing_title].append((url, source, params))
                    return

            self.anime_to_urls[title].append((url, source, params))

    def _guard_sources(self, query: str) -> SearchResults | None:
        if not self.sources:
            logger.info("\n❌ Erro: Nenhum plugin carregado!")
            logger.info("Verifique se os plugins estão instalados em plugins/")
            return SearchResults(query=query, results=(), metadata={})
        return None

    def search_anime(self, query: str, verbose: bool = True) -> SearchResults:
        """Search for anime across all registered sources.

        Uses progressive search: starts with full query, decreases words if no results.
        Caches results for faster retrieval on subsequent queries.
        """
        search_start = time.time()

        if guard := self._guard_sources(query):
            return guard

        cached_data, cache_check_ms = self._try_cache(query, verbose)

        if cached_data and isinstance(cached_data, dict):
            if verbose:
                logger.info(f"ℹ️  Usando cache para '{query}' ({len(cached_data)} animes)")
            self.clear_search_results()
            for anime_title, sources_list in cached_data.items():
                for url, source, params in sources_list:
                    self.add_anime(anime_title, url, source, params)
            total_ms = int((time.time() - search_start) * 1000)
            self._last_search_metadata = {
                "original_query": query,
                "used_query": query,
                "used_words": len(query.split()),
                "total_words": len(query.split()),
                "min_words": settings.search.progressive_search_min_words,
                "source": "cache",
                "cache_hit": True,
                "cache_age_seconds": 0,
                "scraper_sources": [],
                "cache_check_time_ms": cache_check_ms,
                "scraper_execution_time_ms": 0,
                "total_execution_time_ms": total_ms,
            }
            return self._build_search_results(query)

        words = query.split()
        min_words = settings.search.progressive_search_min_words
        scraper_start = time.time()

        for num_words in range(len(words), min_words - 1, -1):
            partial_query = " ".join(words[:num_words])
            self.clear_search_results()
            self._search_with_incremental_results(partial_query, verbose=False)

            if len(self.anime_to_urls) > 0:
                if verbose and num_words < len(words):
                    logger.info(
                        f"ℹ️  Busca com: '{partial_query}' ({num_words}/{len(words)} palavras)"
                    )
                self._last_search_metadata = {
                    "original_query": query,
                    "used_query": partial_query,
                    "used_words": num_words,
                    "total_words": len(words),
                    "min_words": min_words,
                    "source": "scraper",
                    "cache_hit": False,
                    "cache_age_seconds": None,
                    "scraper_sources": self._collect_scraper_sources(),
                    "cache_check_time_ms": cache_check_ms,
                    "scraper_execution_time_ms": int((time.time() - scraper_start) * 1000),
                    "total_execution_time_ms": int((time.time() - search_start) * 1000),
                }
                break
            elif verbose and num_words < len(words):
                logger.info(
                    f"ℹ️  0 resultados com '{partial_query}' ({num_words} palavras) → tentando com menos..."
                )

        if len(self.anime_to_urls) > 0:
            self._save_cache(query, verbose)

        return self._build_search_results(query)

    def search_anime_with_word_limit(
        self, query: str, word_limit: int, verbose: bool = True
    ) -> SearchResults:
        """Search anime using only the first `word_limit` words of query.

        Useful for progressive search where user wants to continue with fewer words.
        """
        if guard := self._guard_sources(query):
            return guard

        words = query.split()
        min_words = settings.search.progressive_search_min_words
        word_limit = max(min_words, min(word_limit, len(words)))
        limited_query = " ".join(words[:word_limit])

        self._last_search_metadata = {
            "original_query": query,
            "used_query": limited_query,
            "used_words": word_limit,
            "total_words": len(words),
            "min_words": min_words,
        }

        self.clear_search_results()
        self._search_with_incremental_results(limited_query, verbose)
        return self._build_search_results(query)

    def get_search_metadata(self) -> SearchMetadata:
        """Get metadata about the last search performed."""
        if not self._last_search_metadata:
            return SearchMetadata(
                original_query=None,
                used_query=None,
                used_words=None,
                total_words=None,
                min_words=None,
                variant_tested=None,
                variant_index=None,
                total_variants=None,
                source=None,
            )
        return SearchMetadata.model_validate(self._last_search_metadata)

    def get_anime_titles(
        self, filter_by_query: Optional[str] = None, min_score: int | None = None
    ) -> list[str]:
        """Get anime titles, optionally filtered by exact match to query.

        Args:
            min_score: Ignored (kept for API compatibility)
        """
        titles = list(self.anime_to_urls.keys())
        if not filter_by_query:
            return sorted(titles)
        query_lower = filter_by_query.lower()
        return sorted(title for title in titles if query_lower in title.lower())

    def get_anime_titles_with_sources(
        self,
        filter_by_query: Optional[str] = None,
        original_query: Optional[str] = None,
        anilist_results: Optional[list] = None,
    ) -> list[str]:
        """Get anime titles with source indicators, ranked by relevance.

        Format: "Anime Title [source1, source2]"
        """
        titles = list(self.anime_to_urls.keys())

        if filter_by_query:
            titles = [
                t for t in titles if SearchRepository._matches_filter_query(t, filter_by_query)
            ]

        result = []
        for title in titles:
            sources = {src for _, src, _ in self.anime_to_urls[title] if src != "cache"}
            sources_str = ", ".join(sorted(sources)) if sources else "cached"
            result.append((f"{title} [{sources_str}]", title))

        if anilist_results:
            result = [
                item[0]
                for item in self._rank_search_results_with_reference(
                    result, anilist_results[0].title
                )
            ]
        elif original_query and " / " in original_query:
            result = [
                item[0] for item in self._rank_search_results_with_reference(result, original_query)
            ]
        elif original_query:
            result = [item[0] for item in self._rank_search_results(result, original_query)]
        else:
            result = [item[0] for item in sorted(result, key=lambda x: x[1])]

        return result
