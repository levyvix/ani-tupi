import importlib
import sys
from abc import ABC, abstractstaticmethod
from os import listdir
from os.path import abspath, dirname, isfile, join


class PluginInterface(ABC):
    """Abstract base class for anime scraper plugins.

    All plugins must implement these static methods.
    """

    name: str = ""  # Plugin identifier (e.g., "animefire")
    languages: list[str] = []  # Supported languages (e.g., ["pt-br"])

    @abstractstaticmethod
    def search_anime(query: str) -> None:
        """Search for anime by title.

        Args:
            query: Search query string

        Must call: Repository.add_anime(title, url, source, params)
        """
        raise NotImplementedError

    @abstractstaticmethod
    def search_episodes(anime: str, url: str, params: dict | None) -> None:
        """Fetch episode list for anime.

        Args:
            anime: Anime title
            url: Anime URL from search_anime
            params: Optional extra parameters from search_anime

        Must call: Repository.add_episode_list(anime, titles, urls, source)
        """
        raise NotImplementedError

    @abstractstaticmethod
    def search_player_src(url: str, container: list, event) -> None:
        """Extract video playback URL from episode URL.

        Args:
            url: Episode URL from search_episodes
            container: List to append video URL to
            event: asyncio.Event to signal completion

        Implementation:
            1. Extract video URL (m3u8 or mp4)
            2. container.append(url)
            3. event.set()
            4. Return immediately (runs in thread pool)
        """
        raise NotImplementedError


def get_resource_path(relative_path):
    """Get the path to resources, whether running as script or executable."""
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller executable
        return join(sys._MEIPASS, relative_path)
    # Use directory where this file is located (works for both dev and installed)
    return join(dirname(abspath(__file__)), relative_path)


def load_plugins(languages: dict, plugins=None) -> None:
    path = get_resource_path("plugins/")
    system = {"__init__.py", "utils.py"}
    plugins = (
        plugins
        if plugins is not None
        else [
            file[:-3]
            for file in listdir(path)
            if isfile(join(path, file)) and file not in system
        ]
    )
    for plugin in plugins:
        plugin = importlib.import_module("plugins." + plugin)
        plugin.load(languages)
