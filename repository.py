import asyncio
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from multiprocessing.pool import ThreadPool
from os import cpu_count
from threading import Thread

from fuzzywuzzy import fuzz

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

    def __new__(cls):
        if not Repository._instance:
            Repository._instance = super().__new__(cls)
        return Repository._instance

    def register(self, plugin: PluginInterface) -> None:
        self.sources[plugin.name] = plugin

    def clear_search_results(self) -> None:
        """Clear all search results, keeping registered plugins."""
        self.anime_to_urls = defaultdict(list)
        self.anime_episodes_titles = defaultdict(list)
        self.anime_episodes_urls = defaultdict(list)
        self.norm_titles = {}

    def search_anime(self, query: str) -> None:
        if not self.sources:
            print("\n❌ Erro: Nenhum plugin carregado!")
            print("Verifique se os plugins estão instalados em plugins/")
            return

        # Progressive search: start with configured min_words, increase if no results
        words = query.split()
        min_words = settings.search.progressive_search_min_words

        # Store original query for later filtering
        self._last_query = query

        # If query has fewer or equal to min_words, just search normally
        if len(words) <= min_words:
            with ThreadPool(min(len(self.sources), cpu_count())) as pool:
                for source in self.sources:
                    pool.apply(self.sources[source].search_anime, args=(query,))
            return

        # Progressive search: min_words, min_words+1, ..., all words
        for num_words in range(min_words, len(words) + 1):
            partial_query = " ".join(words[:num_words])

            # Clear previous attempt results
            self.clear_search_results()

            # Search with current query
            with ThreadPool(min(len(self.sources), cpu_count())) as pool:
                for source in self.sources:
                    pool.apply(self.sources[source].search_anime, args=(partial_query,))

            # If found results, stop
            if self.anime_to_urls:
                if num_words < len(words):
                    print(f"ℹ️  Busca com: '{partial_query}' ({num_words}/{len(words)} palavras)")
                break

    def add_anime(self, title: str, url: str, source: str, params=None) -> None:
        """Add anime with fuzzy deduplication.

        This method assumes different seasons are different anime (like MAL).
        Plugin devs should scrape that way.

        Uses fuzzy matching threshold from config (default 98).
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

        # Use fuzzy threshold from config
        threshold = settings.search.fuzzy_threshold
        for key in self.anime_to_urls:
            if fuzz.ratio(title_, self.norm_titles[key]) >= threshold:
                self.anime_to_urls[key].append((url, source, params))
                return
        self.anime_to_urls[title].append((url, source, params))

    def get_anime_titles(
        self, filter_by_query: str = None, min_score: int | None = None
    ) -> list[str]:
        """Get anime titles, optionally filtered by relevance to query.

        Args:
            filter_by_query: If provided, only return titles with fuzzy score >= min_score
            min_score: Minimum fuzzy matching score (0-100). Defaults to config value.

        Returns:
            Sorted list of anime titles, filtered and scored if query provided.

        Raises:
            ValueError: If min_score is outside valid range (0-100).
        """
        # Use config default if min_score not provided
        if min_score is None:
            min_score = settings.search.min_score

        # Validate min_score
        if not 0 <= min_score <= 100:
            raise ValueError(f"min_score must be 0-100, got {min_score}")

        titles = list(self.anime_to_urls.keys())

        if not filter_by_query:
            return sorted(titles)

        # Normalize query for comparison
        query_norm = filter_by_query.lower()
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
            query_norm = query_norm.replace(key, val)

        # Score each title
        scored_titles = []
        for title in titles:
            title_norm = self.norm_titles[title]
            score = fuzz.ratio(query_norm, title_norm)
            if score >= min_score:
                scored_titles.append((score, title))

        # Sort by score (highest first), then alphabetically
        scored_titles.sort(key=lambda x: (-x[0], x[1]))
        return [title for score, title in scored_titles]

    def search_episodes(self, anime: str) -> None:
        if anime in self.anime_episodes_titles:
            return self.anime_episode_titles[anime]

        urls_and_scrapers = rep.anime_to_urls[anime]
        threads = [Thread(target=self.sources[source].search_episodes, args=(anime, url, params )) for url, source, params in urls_and_scrapers]

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
        return sorted(self.anime_episodes_titles[anime], key=lambda title_list: len(title_list))[-1]

    def search_player(self, anime: str, episode_num: int) -> None:
        """This method assumes all episode lists to be the same size, plugin devs should guarantee that OVA's are not considered."""
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
                tasks = [loop.run_in_executor(executor, self.sources[source].search_player_src, url, container, event) for url, source in selected_urls]
                _done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

                return container[0]

        return asyncio.run(search_all_sources())

rep = Repository()

if __name__=="__main__":
    rep3, rep2 = Repository(), Repository()
