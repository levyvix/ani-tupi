import asyncio
from os import cpu_count
from loader import PluginInterface
from typing import Callable
from collections import defaultdict
from threading import Thread, Condition
from concurrent.futures import ThreadPoolExecutor
from multiprocessing.pool import ThreadPool
from fuzzywuzzy import fuzz


class Repository:
    """ SingletonRepository 
        get for methods called by main that return some value
        search for methods called by main that don't return but affects state
        add for methods called by any plugin that affects state
        register should be called by a loader function 
    """

    _instance = None
    
    def __init__(self) -> None:
        self.sources = dict()
        self.anime_to_urls = defaultdict(list)
        self.anime_episodes_titles = defaultdict(list)
        self.anime_episodes_urls = defaultdict(list)
        self.norm_titles = dict()

    def __new__(cls):
        if not Repository._instance:
            Repository._instance = super(Repository, cls).__new__(cls)
        return Repository._instance

    def register(self, plugin: PluginInterface) -> None:
        self.sources[plugin.name] = plugin

    def clear_search_results(self) -> None:
        """Clear all search results, keeping registered plugins"""
        self.anime_to_urls = defaultdict(list)
        self.anime_episodes_titles = defaultdict(list)
        self.anime_episodes_urls = defaultdict(list)
        self.norm_titles = dict()

    def search_anime(self, query: str) -> None:
        with ThreadPool(min(len(self.sources), cpu_count())) as pool:
            for source in self.sources:
                pool.apply(self.sources[source].search_anime, args=(query,))

    def add_anime(self, title: str, url: str, source:str, params=None) -> None:
        """
        This method assumes that different seasons are different anime, like MAL, so plugin devs should take scrape that way.
        """
        title_ = title.lower()
        table = {"clássico": "", 
                 "classico": "", 
                 ":":"", 
                 "part":"season", 
                 "temporada":"season",
                 "(":"",
                 ")":"",
                 " ": ""}

        for key, val in table.items():
            title_ = title_.replace(key, val)
        
        self.norm_titles[title] = title_

        threshold = 95
        for key in self.anime_to_urls.keys():
            if fuzz.ratio(title_, self.norm_titles[key]) >= threshold:
                self.anime_to_urls[key].append((url, source, params))
                return
        self.anime_to_urls[title].append((url, source, params))

    def get_anime_titles(self) -> list[str]:
        return sorted(list(self.anime_to_urls.keys()))
    
    def search_episodes(self, anime: str) -> None:
        if anime in self.anime_episodes_titles:
            return self.anime_episode_titles[anime]

        urls_and_scrapers = rep.anime_to_urls[anime]
        threads = [Thread(target=self.sources[source].search_episodes, args=(anime, url, params, )) for url, source, params in urls_and_scrapers]
        
        for th in threads:
            th.start()

        for th in threads:
            th.join()
    
    def add_episode_list(self, anime: str, title_list: list[str], url_list: list[str], source: str) -> None:
        self.anime_episodes_titles[anime].append(title_list)
        self.anime_episodes_urls[anime].append((url_list, source))
    
    def get_episode_list(self, anime: str):
        return sorted(self.anime_episodes_titles[anime], key=lambda title_list: len(title_list))[0]

    def search_player(self, anime: str, episode_num: int) -> None:
        """
        This method assumes all episode lists to be the same size, plugin devs should guarantee that OVA's are not considered.
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
                tasks = [loop.run_in_executor(executor, self.sources[source].search_player_src, url, container, event) for url, source in selected_urls]
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED) 

                #for task in pending:
                #    task.cancel()
                return container[0]

        return asyncio.run(search_all_sources())
        
rep = Repository()

if __name__=="__main__":
    rep3, rep2 = Repository(), Repository()
    print(rep3 is rep2)
