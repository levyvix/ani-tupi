"""Business logic services layer.

Core services for ani-tupi:
- anime_service: Anime search and playback logic
- anilist: AniList API client, discovery, and cache adapters
- history_service: Watch history management
- manga_service: Manga search and reading
- repository: Central data store
"""

from services import (
    anime_service,
    anilist,
    history_service,
    manga_service,
    repository,
)

__all__ = [
    "anime_service",
    "anilist",
    "history_service",
    "manga_service",
    "repository",
]
