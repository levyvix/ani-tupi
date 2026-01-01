import asyncio
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from multiprocessing.pool import ThreadPool
from os import cpu_count
from threading import Thread

from config import settings
from loader import PluginInterface
from models import EpisodeData


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
                print(f"ℹ️  0 resultados com '{partial_query}' ({num_words} palavras) → tentando com menos...")

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

    @staticmethod
    def _calculate_timeout(query: str) -> float:
        """Calculate adaptive timeout based on query specificity.

        Queries with more words are more specific and may take longer to find results.

        Args:
            query: The search query

        Returns:
            Timeout in seconds: 10s for 1-2 words, 15s for 3-4 words, 20s for 5+ words
        """
        word_count = len(query.split())

        if word_count <= 2:
            return 10.0  # Generic search
        elif word_count <= 4:
            return 15.0  # Specific search
        else:
            return 20.0  # Very specific search

    def _search_with_incremental_results(self, query: str, verbose: bool = True) -> None:
        """Search anime with incremental results, with adaptive timeout for slow sources."""
        from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED

        if verbose:
            print(f"⠼ Buscando '{query}'...")

        # Adaptive timeout based on query specificity
        # More specific queries (more words) = more time for scrapers
        TIMEOUT_SECONDS = self._calculate_timeout(query)

        executor = ThreadPoolExecutor(max_workers=min(len(self.sources), cpu_count()))

        try:
            # Submit all search tasks
            future_to_source = {
                executor.submit(self.sources[source].search_anime, query): source
                for source in self.sources
            }

            # Wait with hard timeout - returns immediately after timeout
            done, pending = wait(
                future_to_source.keys(),
                timeout=TIMEOUT_SECONDS,
                return_when=ALL_COMPLETED
            )

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

            completed = len(done)
            total = len(self.sources)

            if verbose:
                count = len(self.anime_to_urls)
                if pending:
                    print(f"⏱️ Timeout ({TIMEOUT_SECONDS}s) - {len(pending)} fonte(s) ignorada(s)")
                    print(f"📊 {count} resultado(s) de {completed}/{total} fonte(s)")
                elif completed > 1 and count > 0:
                    # All completed successfully (show count only if multiple sources)
                    print(f"✓ {count} resultado(s) de {completed}/{total} fonte(s)")

        finally:
            # Shutdown executor WITHOUT waiting for pending tasks
            executor.shutdown(wait=False, cancel_futures=True)

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
        self, filter_by_query: str = None, min_score: int | None = None
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
        self, filter_by_query: str = None, original_query: str = None
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
                title for title in titles
                if query_normalized in self._normalize_for_filter(title)
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

    def search_episodes(self, anime: str) -> None:
        if anime in self.anime_episodes_titles:
            return self.anime_episode_titles[anime]

        urls_and_scrapers = rep.anime_to_urls[anime]
        threads = [
            Thread(
                target=self.sources[source].search_episodes,
                args=(anime, url, params),
            )
            for url, source, params in urls_and_scrapers
        ]

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
        episode_list = sorted(self.anime_episodes_titles[anime], key=lambda title_list: len(title_list))[-1]
        return list(reversed(episode_list))

    def search_player(self, anime: str, episode_num: int) -> None:
        """Search for video URLs.

        Assumes all episode lists are the same size.
        Plugin devs should guarantee that OVAs are not considered.
        """
        selected_urls = []
        for urls, source in self.anime_episodes_urls[anime]:
            if len(urls) >= episode_num:
                selected_urls.append((urls[episode_num - 1], source))

        async def search_all_sources():
            nonlocal selected_urls, self
            event = asyncio.Event()
            container = []
            loop = asyncio.get_running_loop()
            with ThreadPoolExecutor(max_workers=cpu_count()) as executor:
                tasks = [
                    loop.run_in_executor(
                        executor,
                        self.sources[source].search_player_src,
                        url,
                        container,
                        event,
                    )
                    for url, source in selected_urls
                ]
                _done, _pending = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )

                return container[0]

        return asyncio.run(search_all_sources())

rep = Repository()

if __name__=="__main__":
    rep3, rep2 = Repository(), Repository()
