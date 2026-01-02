"""Command handlers for ani-tupi CLI.

Each module handles a specific user interaction flow:
- anime.py: Anime search, selection, and playback
- anilist.py: AniList integration (auth and menu)
- manga.py: Manga search and reading
- sources.py: Plugin/source management
"""

from commands.anime import anime
from commands.anilist import anilist_auth, anilist_menu
from commands.manga import manga
from commands.sources import manage_sources

__all__ = ["anime", "anilist_auth", "anilist_menu", "manga", "manage_sources"]
