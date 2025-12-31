import asyncio
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from multiprocessing.pool import ThreadPool
from os import cpu_count
from threading import Thread

from fuzzywuzzy import fuzz

from loader import PluginInterface


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

        # Progressive search: start with 2 words, increase if no results
        words = query.split()
        min_words = 2

        # Store original query for later filtering
        self._last_query = query

        # If query has 2 or fewer words, just search normally
        if len(words) <= min_words:
            with ThreadPool(min(len(self.sources), cpu_count())) as pool:
                for source in self.sources:
                    pool.apply(self.sources[source].search_anime, args=(query,))
            return

        # Progressive search: 2 words, 3 words, ..., all words
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

    def add_anime(self, title: str, url: str, source:str, params=None) -> None:
        """This method assumes that different seasons are different anime, like MAL, so plugin devs should take scrape that way."""
        title_ = title.lower()
        table = {"clássico": "",
                 "classico": "",
                 "dublado": "",
                 "legendado": "",
                 ":":"",
                 "part":"season",
                 "temporada":"season",
                 "(":"",
                 ")":"",
                 " ": ""}

        for key, val in table.items():
            title_ = title_.replace(key, val)

        self.norm_titles[title] = title_

        threshold = 98
        for key in self.anime_to_urls:
            if fuzz.ratio(title_, self.norm_titles[key]) >= threshold:
                self.anime_to_urls[key].append((url, source, params))
                return
        self.anime_to_urls[title].append((url, source, params))

    def get_anime_titles(self, filter_by_query: str = None, min_score: int = 70) -> list[str]:
        """Get anime titles, optionally filtered by relevance to query.

        Args:
            filter_by_query: If provided, only return titles with fuzzy score >= min_score
            min_score: Minimum fuzzy matching score (0-100) to include result
        """
        titles = list(self.anime_to_urls.keys())

        if not filter_by_query:
            return sorted(titles)

        # Normalize query for comparison
        query_norm = filter_by_query.lower()
        table = {
            'clássico': '', 'classico': '',
            'dublado': '', 'legendado': '',
            ':': '', 'part': 'season', 'temporada': 'season',
            '(': '', ')': '', ' ': ''
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

    def add_episode_list(self, anime: str, title_list: list[str], url_list: list[str], source: str) -> None:
        self.anime_episodes_titles[anime].append(title_list)
        self.anime_episodes_urls[anime].append((url_list, source))

    def get_episode_list(self, anime: str):
        return sorted(self.anime_episodes_titles[anime], key=lambda title_list: len(title_list))[0]

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
