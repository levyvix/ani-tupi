"""Business logic services layer.

Core services for ani-tupi, one package per domain:
- anime: Anime search, playback, local library, and AniList flows
- anilist: AniList API client, discovery, and cache adapters
- repository: Central data store (search, episodes, playback, players)
- manga: Manga search, reading, downloads, and local library
- core: Cross-cutting services (history, settings, update check, UI bridge)
"""

from services import (
    anime,
    anilist,
    repository,
    manga,
    core,
)

__all__ = [
    "anime",
    "anilist",
    "repository",
    "manga",
    "core",
]
