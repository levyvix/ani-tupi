"""Manga scraper plugin loader.

Dynamic loading system for manga scrapers. Similar to anime scraper loader
but adapted for manga-specific operations (search, chapter listing, page extraction).
Uses StealthyFetcher with adaptive mode for robust scraping.
"""

import importlib
from os import listdir
from os.path import abspath, dirname, isfile, join
from typing import Protocol
from utils.logging import get_logger

logger = get_logger(__name__)


class MangaScraperProtocol(Protocol):
    """Protocol for manga scraper plugins.

    Plugins implementing this protocol provide manga search and reading functionality.
    Uses structural typing (duck typing) - no inheritance required.
    """

    name: str  # Plugin identifier (e.g., "mugiwaras", "mangadex")

    def search_manga(self, query: str) -> list[dict]:
        """Search for manga by title.

        Args:
            query: Search query string

        Returns:
            List of manga results with structure:
            [
                {
                    "id": "unique-id",
                    "title": "Manga Title",
                    "url": "https://...",
                    "description": "Description",  # optional
                    "status": "ongoing",  # optional
                    "year": 2020,  # optional
                }
            ]
        """
        ...

    def get_chapters(self, manga_id: str, manga_url: str) -> list[dict]:
        """Fetch chapter list for a manga.

        Args:
            manga_id: Manga ID from search_manga
            manga_url: Manga URL from search_manga

        Returns:
            List of chapters with structure:
            [
                {
                    "id": "chapter-id",
                    "number": "1",
                    "title": "Chapter Title",  # optional
                    "url": "https://...",
                }
            ]
        """
        ...

    def get_chapter_pages(self, chapter_id: str, chapter_url: str) -> list[str]:
        """Fetch image URLs for a chapter.

        Args:
            chapter_id: Chapter ID from get_chapters
            chapter_url: Chapter URL from get_chapters

        Returns:
            List of image URLs in reading order
        """
        ...


# For backwards compatibility with existing code
MangaScraperInterface = MangaScraperProtocol


def get_resource_path(relative_path):
    """Get the path to resources relative to this loader."""
    return join(dirname(abspath(__file__)), relative_path)


def load_manga_plugins() -> dict[str, MangaScraperProtocol]:
    """Load all manga scraper plugins.

    Returns:
        Dictionary mapping plugin names to plugin instances
    """

    path = get_resource_path("plugins/")
    system = {"__init__.py", "utils.py"}

    # Get all available plugin files
    try:
        all_plugin_files = [
            file[:-3] for file in listdir(path) if isfile(join(path, file)) and file not in system
        ]
    except FileNotFoundError:
        return {}

    plugins = {}

    # Load each plugin
    for plugin in all_plugin_files:
        try:
            plugin_module = importlib.import_module(f"manga_scrapers.plugins.{plugin}")
            # Call plugin's load function which returns plugin instance or None
            plugin_instance = plugin_module.load()
            if plugin_instance is not None:
                plugins[plugin_instance.name] = plugin_instance
        except Exception as e:
            logger.info(f"⚠️  Falha ao carregar plugin {plugin}: {e}")
            continue

    return plugins
