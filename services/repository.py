import asyncio
from typing import Optional
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from os import cpu_count
from threading import Thread

from models.config import settings
from scrapers.loader import PluginInterface
from models.models import EpisodeData


class Repository:
    """SingletonRepository
    get for methods called by main that return some value
    search for methods called by main that don't return but affects state
    add for methods called by any plugin that affects state
    register should be called by a loader function.
    """

    _instance = None

    def __init__(self) -> None:
        self.sources = {}
        self.anime_to_urls = defaultdict(list)
        self.anime_episodes_titles = defaultdict(list)
        self.anime_episodes_urls = defaultdict(list)
        self.norm_titles = {}
        self._last_search_metadata = {}
        # Mapping from anime title to AniList ID (for cache key)
        self.anime_to_anilist_id = {}

    def __new__(cls):
        if not Repository._instance:
            Repository._instance = super().__new__(cls)
        return Repository._instance

    def register(self, plugin: PluginInterface) -> None:
        self.sources[plugin.name] = plugin

    def get_active_sources(self) -> list[str]:
        """Get list of currently registered plugin names.

        Returns:
            List of plugin names (e.g., ["animefire", "animesonlinecc"])
        """
        return sorted(list(self.sources.keys()))

    def clear_search_results(self) -> None:
        """Clear all search results, keeping registered plugins."""
        self.anime_to_urls = defaultdict(list)
        self.anime_episodes_titles = defaultdict(list)
        self.anime_episodes_urls = defaultdict(list)
        self.norm_titles = {}

    def search_anime(self, query: str, verbose: bool = True) -> None:
        if not self.sources:
            print("\n❌ Erro: Nenhum plugin carregado!")
            print("Verifique se os plugins estão instalados em plugins/")
            return

        # CACHE CHECK: Try to get search results from cache first
        cache_key = f"search:{query.lower()}"
        try:
            from utils.cache_manager import get_cache as get_dc

            dc = get_dc()
            cached_results = dc.get(cache_key)
        except Exception as e:
            if verbose:
                print(f"⚠️  Erro ao acessar cache: {e}")
            cached_results = None

        if cached_results and isinstance(cached_results, dict):
            # Cache hit! Load results directly without scraping
            if verbose:
                print(f"ℹ️  Usando cache para '{query}' ({len(cached_results)} animes)")

            for anime_title, sources_list in cached_results.items():
                for url, source, params in sources_list:
                    self.add_anime(anime_title, url, source, params)

            # Still auto-discover IDs for cached results
            if settings.cache.anilist_auto_discover:
                from utils.anilist_discovery import auto_discover_anilist_id

                for anime_title in self.anime_to_urls.keys():
                    if anime_title not in self.anime_to_anilist_id:
                        anilist_id = auto_discover_anilist_id(anime_title)
                        if anilist_id:
                            self.anime_to_anilist_id[anime_title] = anilist_id

            # Set search metadata for consistency
            self._last_search_metadata = {
                "original_query": query,
                "used_query": query,
                "used_words": len(query.split()),
                "total_words": len(query.split()),
                "min_words": settings.search.progressive_search_min_words,
                "source": "cache",
            }
            return  # Done! Use cached results

        # Progressive search: start with all words, decrease if no results
        words = query.split()
        min_words = settings.search.progressive_search_min_words

        # Store original query for later filtering
        self._last_query = query

        # Progressive search (DECRESCENTE): len(words), len(words)-1, ..., min_words
        # Tries full query first, then progressively removes words from the end
        for num_words in range(len(words), min_words - 1, -1):
            partial_query = " ".join(words[:num_words])

            # Clear previous attempt results
            self.clear_search_results()

            # Search with current query (incremental)
            self._search_with_incremental_results(partial_query, verbose=False)

            # If found results, stop
            results_found = len(self.anime_to_urls)
            if results_found > 0:
                if verbose and num_words < len(words):
                    print(f"ℹ️  Busca com: '{partial_query}' ({num_words}/{len(words)} palavras)")
                # Store metadata about the search
                self._last_search_metadata = {
                    "original_query": query,
                    "used_query": partial_query,
                    "used_words": num_words,
                    "total_words": len(words),
                    "min_words": min_words,
                }
                break
            elif verbose and num_words < len(words):
                # No results with this word count, will try fewer words
                print(
                    f"ℹ️  0 resultados com '{partial_query}' ({num_words} palavras) → tentando com menos..."
                )

        # Auto-discover AniList IDs for search results (non-blocking)
        if settings.cache.anilist_auto_discover:
            from utils.anilist_discovery import auto_discover_anilist_id

            for anime_title in self.anime_to_urls.keys():
                if anime_title not in self.anime_to_anilist_id:
                    anilist_id = auto_discover_anilist_id(anime_title)
                    if anilist_id:
                        self.anime_to_anilist_id[anime_title] = anilist_id

        # CACHE SAVE: Save search results to cache
        if len(self.anime_to_urls) > 0:
            try:
                from utils.cache_manager import get_cache as get_dc

                dc = get_dc()
                cache_key = f"search:{query.lower()}"
                # Convert anime_to_urls to dict format for caching
                cache_data = dict(self.anime_to_urls)
                dc.set(cache_key, cache_data, expire=settings.cache.duration_hours * 3600)
            except Exception as e:
                if verbose:
                    print(f"⚠️  Erro ao salvar cache: {e}")

    def search_anime_with_word_limit(
        self, query: str, word_limit: int, verbose: bool = True
    ) -> None:
        """Search anime with a word limit.

        Searches using only the first `word_limit` words of the query.
        Useful for progressive search where user wants to continue with fewer words.

        Args:
            query: Original query (may have more words than word_limit)
            word_limit: Number of words to use from the start of query
            verbose: Show progress messages

        Example:
            search_anime_with_word_limit("Dan Da Dan Season 2", 2)
            # Searches for "Dan Da"
        """
        if not self.sources:
            print("\n❌ Erro: Nenhum plugin carregado!")
            print("Verifique se os plugins estão instalados em plugins/")
            return

        words = query.split()
        min_words = settings.search.progressive_search_min_words

        # Ensure word_limit is within valid range
        word_limit = max(min_words, min(word_limit, len(words)))

        # Create limited query
        limited_query = " ".join(words[:word_limit])

        # Store metadata
        self._last_search_metadata = {
            "original_query": query,
            "used_query": limited_query,
            "used_words": word_limit,
            "total_words": len(words),
            "min_words": min_words,
        }

        # Clear previous results
        self.clear_search_results()

        # Execute search
        self._search_with_incremental_results(limited_query, verbose)

    def get_search_metadata(self) -> dict:
        """Get metadata about the last search performed.

        Returns:
            Dict with keys:
            - original_query: The full query user typed
            - used_query: The actual query used (after reduction)
            - used_words: Number of words used in final search
            - total_words: Total number of words in original query
            - min_words: Minimum word limit (from config)

            Returns empty dict if no search has been performed yet.
        """
        return self._last_search_metadata

    @staticmethod
    def _normalize_for_filter(text: str) -> str:
        """Normalize text for filtering (same logic as add_anime).

        Removes punctuation, converts to lowercase, removes multiple spaces.
        Used for both queries and titles before comparison.
        """
        text = text.lower()
        # Remove punctuation and special characters
        for char in ["-", ":", "(", ")", "!", "?", "."]:
            text = text.replace(char, " ")
        # Remove multiple spaces
        text = " ".join(text.split())
        return text

    def _search_with_incremental_results(self, query: str, verbose: bool = True) -> None:
        """Search anime with incremental results."""
        from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED

        if verbose:
            print(f"⠼ Buscando '{query}'...")

        n_cpu = cpu_count()
        if not n_cpu:
            n_cpu = 10

        executor = ThreadPoolExecutor(max_workers=min(len(self.sources), n_cpu))

        try:
            # Get a snapshot of sources to avoid race conditions
            sources_list = list(self.sources.items())

            # Submit all search tasks
            future_to_source = {}
            for source_name, plugin in sources_list:
                future = executor.submit(plugin.search_anime, query)
                future_to_source[future] = source_name

            # Wait for all tasks to complete
            done, _ = wait(future_to_source.keys(), return_when=ALL_COMPLETED)

            # Process completed futures
            for future in done:
                source = future_to_source[future]
                try:
                    future.result()
                    if verbose and len(self.sources) > 1:
                        count = len(self.anime_to_urls)
                        print(f"✓ {source} ({count} resultados)", end="\r")
                except Exception as e:
                    if verbose:
                        print(f"❌ Erro em {source}: {e}")

            # Clear progress line and show summary
            if verbose and len(self.sources) > 1:
                print(" " * 70 + "\r", end="")

            if verbose:
                count = len(self.anime_to_urls)
                total = len(self.sources)
                if total > 1 and count > 0:
                    print(f"✓ {count} resultado(s) de {total} fonte(s)")

        finally:
            # Shutdown executor and wait for all tasks
            executor.shutdown(wait=True)

    def add_anime(self, title: str, url: str, source: str, params=None) -> None:
        """Add anime with exact deduplication.

        This method assumes different seasons are different anime (like MAL).
        Plugin devs should scrape that way.

        Uses exact matching: only consolidates if normalized titles are 100% identical.
        This preserves dubbed/subbed/season distinctions.
        """
        title_ = title.lower()
        table = {
            "clássico": "",
            "classico": "",
            ":": "",
            "part": "season",
            "temporada": "season",
            "(": "",
            ")": "",
            " ": "",
        }

        for key, val in table.items():
            title_ = title_.replace(key, val)

        self.norm_titles[title] = title_

        # Exact matching: only consolidate if normalized titles are identical
        for key in self.anime_to_urls:
            if title_ == self.norm_titles[key]:
                self.anime_to_urls[key].append((url, source, params))
                return
        self.anime_to_urls[title].append((url, source, params))

    def get_anime_titles(
        self, filter_by_query: Optional[str] = None, min_score: int | None = None
    ) -> list[str]:
        """Get anime titles, optionally filtered by exact match to query.

        Args:
            filter_by_query: If provided, only return titles matching query.
            min_score: Ignored (kept for API compatibility)

        Returns:
            Sorted list of anime titles, filtered if query provided.
        """
        titles = list(self.anime_to_urls.keys())

        if not filter_by_query:
            return sorted(titles)

        # Simple case-insensitive substring matching
        query_lower = filter_by_query.lower()
        filtered = [title for title in titles if query_lower in title.lower()]
        return sorted(filtered)

    def get_anime_titles_with_sources(
        self, filter_by_query: Optional[str] = None, original_query: Optional[str] = None
    ) -> list[str]:
        """Get anime titles with source indicators, ranked by relevance.

        Shows which sources have each anime, helpful for multi-source scenarios.
        Format: "Anime Title [source1, source2]"

        Args:
            filter_by_query: If provided, only return titles matching query.
            original_query: If provided, rank results by fuzzy matching score.

        Returns:
            List of anime titles with source indicators, ranked by relevance
        """
        from fuzzywuzzy import fuzz

        titles = list(self.anime_to_urls.keys())

        if filter_by_query:
            # Improved filtering: normalize both query and titles before matching
            query_normalized = self._normalize_for_filter(filter_by_query)
            titles = [
                title for title in titles if query_normalized in self._normalize_for_filter(title)
            ]

        # Build titles with sources
        result = []
        for title in titles:
            urls_and_sources = self.anime_to_urls[title]
            sources = set(source for _url, source, _params in urls_and_sources)
            sources_str = ", ".join(sorted(sources))
            result.append((f"{title} [{sources_str}]", title))

        # Rank by relevance if original_query provided
        if original_query:
            # Calculate fuzzy matching score for each title
            scored_results = []
            for result_with_source, original_title in result:
                score = fuzz.ratio(original_query.lower(), original_title.lower())
                scored_results.append((result_with_source, score))

            # Sort by score (descending), then alphabetically by title
            scored_results.sort(key=lambda x: (-x[1], x[0]))
            result = [item[0] for item in scored_results]
        else:
            # Default: sort alphabetically by title
            result = [item[0] for item in sorted(result, key=lambda x: x[1])]

        return result

    def search_episodes(self, anime: str, source_filter: str | None = None) -> None:
        """Search for episodes from all sources or a specific source.

        Args:
            anime: Anime title to search episodes for
            source_filter: Optional source name to search only that source (e.g., "animefire")
        """
        if anime in self.anime_episodes_titles:
            return self.anime_episode_titles[anime]

        urls_and_scrapers = rep.anime_to_urls[anime]

        # Filter by source if specified
        if source_filter:
            urls_and_scrapers = [
                (url, source, params)
                for url, source, params in urls_and_scrapers
                if source == source_filter
            ]

        # Build threads safely, avoiding potential race conditions
        threads = []
        for url, source, params in urls_and_scrapers:
            if source in self.sources:
                th = Thread(
                    target=self.sources[source].search_episodes,
                    args=(anime, url, params),
                )
                threads.append(th)

        for th in threads:
            th.start()

        for th in threads:
            th.join()
        return None

    def add_episode_list(
        self, anime: str, title_list: list[str], url_list: list[str], source: str
    ) -> None:
        """Add episode list with validation.

        Args:
            anime: Anime title
            title_list: List of episode titles
            url_list: List of episode URLs
            source: Plugin source name

        Raises:
            ValueError: If title_list and url_list have different lengths.
        """
        # Validate using EpisodeData model
        episode_data = EpisodeData(
            anime_title=anime,
            episode_titles=title_list,
            episode_urls=url_list,
            source=source,
        )

        self.anime_episodes_titles[anime].append(episode_data.episode_titles)
        self.anime_episodes_urls[anime].append((episode_data.episode_urls, source))

    def get_episode_list(self, anime: str):
        episodes = self.anime_episodes_titles[anime]
        if not episodes:
            return []
        episode_list = sorted(episodes, key=lambda title_list: len(title_list))[-1]
        return episode_list

    def load_from_cache(self, anime: str, cache_data: dict) -> None:
        """Populate repository from cached data.

        Cache-first approach: When anime is found in cache, load its data
        directly into the repository without searching scrapers.

        Args:
            anime: Anime title
            cache_data: Dict with keys 'episode_urls' and 'episode_count'
        """
        if not cache_data:
            return

        episode_urls = cache_data.get("episode_urls", [])
        if not episode_urls:
            return

        # Generate episode titles from URLs (format: "Episódio 1", "Episódio 2", etc)
        episode_titles = [f"Episódio {i + 1}" for i in range(len(episode_urls))]

        # Add to repository as if it came from a "cache" source
        self.anime_episodes_titles[anime].append(episode_titles)
        self.anime_episodes_urls[anime].append((episode_urls, "cache"))

        # Add dummy entry to anime_to_urls so repository knows about this anime
        # (not needed for playback, but maintains consistency)
        if anime not in self.anime_to_urls:
            self.anime_to_urls[anime].append(("cached", "cache", None))

    def get_episode_url_and_source(self, anime: str, episode_num: int) -> tuple[str, str] | None:
        """Get episode URL and source name for a specific episode.

        Args:
            anime: Anime title
            episode_num: Episode number (1-indexed)

        Returns:
            Tuple of (episode_url, source_name) or None if not found
        """
        # Validate episode_num
        if episode_num < 1:
            return None

        for urls, source in self.anime_episodes_urls[anime]:
            if len(urls) >= episode_num:
                return (urls[episode_num - 1], source)

        return None

    def search_player(self, anime: str, episode_num: int) -> None:
        """Search for video URLs with caching.

        Cache video URLs to speed up rewatching (7-15s → 100ms!)
        Assumes all episode lists are the same size.
        Plugin devs should guarantee that OVAs are not considered.
        """
        from utils.anilist_discovery import auto_discover_anilist_id

        selected_urls = []
        for urls, source in self.anime_episodes_urls[anime]:
            if len(urls) >= episode_num:
                selected_urls.append((urls[episode_num - 1], source))

        # Defensive check: No sources have this episode available
        if not selected_urls:
            active_sources = self.get_active_sources()
            if active_sources:
                print(f"   ❌ Episódio {episode_num} não disponível nas fontes ativas.")
                print(f"   💡 Fontes ativas: {', '.join(active_sources)}")
            else:
                print(f"   ❌ Nenhuma fonte ativa para buscar episódio {episode_num}.")
            return None

        # Get or discover anilist_id for cache key
        anilist_id = self.anime_to_anilist_id.get(anime)
        if anilist_id is None and settings.cache.anilist_auto_discover:
            anilist_id = auto_discover_anilist_id(anime)
            if anilist_id:
                self.anime_to_anilist_id[anime] = anilist_id

        # Use anilist_id if available, fallback to anime title
        cache_key = anilist_id if anilist_id else anime

        # CACHE DISABLED for video URLs - tokens expire too quickly
        # Blogger URLs with tokens expire in minutes, caching causes playback failures
        # Only episode lists are cached, not video stream URLs

        # Cache miss - search all sources in parallel
        async def search_all_sources():
            nonlocal selected_urls, self, cache_key
            event = asyncio.Event()
            container = []
            loop = asyncio.get_running_loop()

            # Show which sources are being tried
            sources_list = [source for _, source in selected_urls]
            if len(sources_list) > 1:
                print(f"   🔄 Tentando fontes: {', '.join(sources_list)}")

            # Wrapper to catch exceptions from plugins
            def safe_plugin_call(plugin_func, url, source):
                try:
                    plugin_func(url, container, event)
                    if container:  # Only print if this source succeeded
                        print(f"   ✅ Vídeo encontrado em: {source}")
                except Exception as e:
                    # Extract just the first line of error (avoid huge stack traces)
                    error_msg = str(e).split("\n")[0]
                    print(f"   ❌ {source} falhou: {error_msg[:80]}")
                    # Don't re-raise - let other sources try

            # PRIORIDADE: Separar AnimeFiree das outras fontes
            animefire_urls = [
                (url, source) for url, source in selected_urls if source == "animefire"
            ]
            other_urls = [(url, source) for url, source in selected_urls if source != "animefire"]

            with ThreadPoolExecutor(max_workers=cpu_count()) as executor:
                # Se AnimeFiree está disponível, tentar primeiro
                if animefire_urls:
                    animefire_tasks = [
                        loop.run_in_executor(
                            executor,
                            safe_plugin_call,
                            self.sources[source].search_player_src,
                            url,
                            source,
                        )
                        for url, source in animefire_urls
                    ]

                    # Esperar por AnimeFiree (com timeout de 15s)
                    try:
                        _done, _pending = await asyncio.wait(
                            animefire_tasks, return_when=asyncio.FIRST_COMPLETED, timeout=15
                        )
                    except asyncio.TimeoutError:
                        _pending = set(animefire_tasks)

                    # Se AnimeFiree encontrou, retornar imediatamente
                    if container:
                        return container[0]

                    # Se AnimeFiree falhou, tentar outras fontes
                    if other_urls:
                        other_tasks = [
                            loop.run_in_executor(
                                executor,
                                safe_plugin_call,
                                self.sources[source].search_player_src,
                                url,
                                source,
                            )
                            for url, source in other_urls
                        ]
                        _done, _pending = await asyncio.wait(
                            other_tasks, return_when=asyncio.FIRST_COMPLETED
                        )

                        # Se container is empty after first task, wait for remaining tasks
                        while not container and _pending:
                            _done, _pending = await asyncio.wait(
                                _pending, return_when=asyncio.FIRST_COMPLETED
                            )

                else:
                    # Se AnimeFiree não está disponível, race todas as fontes normalmente
                    tasks = [
                        loop.run_in_executor(
                            executor,
                            safe_plugin_call,
                            self.sources[source].search_player_src,
                            url,
                            source,
                        )
                        for url, source in selected_urls
                    ]

                    # Wait for all tasks to complete (any task that finds a URL will set event)
                    # Continue until all tasks finish or one succeeds
                    _done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

                    # If container is empty after first task, wait for remaining tasks
                    while not container and _pending:
                        _done, _pending = await asyncio.wait(
                            _pending, return_when=asyncio.FIRST_COMPLETED
                        )

                # Get video URL if found, otherwise return None
                video_url = container[0] if container else None

                # Save to cache for future use
                # DON'T cache video URLs - they expire too quickly
                # Caching Blogger URLs causes playback failures due to token expiration
                return video_url

        return asyncio.run(search_all_sources())


rep = Repository()

if __name__ == "__main__":
    rep3, rep2 = Repository(), Repository()
