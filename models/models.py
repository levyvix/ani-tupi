"""Pydantic data models for structured data transfer.

This module is a backward-compatible re-export hub. The model definitions live
in cohesive domain submodules:

- ``models.anime``   — anime/search/episode/watch-history models
- ``models.manga``   — manga metadata, chapters, reading history
- ``models.anilist`` — AniList and Jikan/MyAnimeList API models
- ``models.cache``   — scraper cache models
- ``models.download``— anime download and offline-sync models
- ``models.update``  — update-check and video playback models

Every name previously importable from ``models.models`` is re-exported here, so
existing ``from models.models import X`` imports keep working unchanged.
"""

from models.anilist import (
    AiringAnimeEntry,
    AniListActivity,
    AniListAnime,
    AniListAnimeStatistics,
    AniListManga,
    AniListMediaListEntry,
    AniListRelationEdge,
    AniListRelationNode,
    AniListSearchResult,
    AniListStatistics,
    AniListTitle,
    AniListViewerInfo,
    AnimeMetadataEntry,
)
from models.anime import (
    AnimeMetadata,
    AnimeSearchResult,
    AnimeTitleResolution,
    EpisodeContext,
    EpisodeData,
    HistoryEntry,
    ScrapedEpisodes,
    SearchMetadata,
    SearchResults,
    Status,
)
from models.cache import CacheStats, ScraperCacheData
from models.download import (
    AnimeDownloadDatabase,
    AnimeDownloadHistory,
    DownloadedEpisode,
    DownloadResult,
    OfflineSyncQueue,
    OfflineSyncQueueEntry,
)
from models.manga import (
    ChapterData,
    LocalChapter,
    MangaHistoryEntry,
    MangaMetadata,
    MangaStatus,
)
from models.update import UpdateCheckResult, UpdateCheckState, VideoUrl

# Resolve forward reference MangaMetadata.anilist_data -> AniListManga now that
# both classes are imported into a shared namespace.
MangaMetadata.model_rebuild()

__all__ = [
    # anime
    "AnimeMetadata",
    "EpisodeData",
    "ScrapedEpisodes",
    "AnimeTitleResolution",
    "EpisodeContext",
    "SearchMetadata",
    "Status",
    "AnimeSearchResult",
    "SearchResults",
    "HistoryEntry",
    # manga
    "MangaStatus",
    "MangaMetadata",
    "ChapterData",
    "LocalChapter",
    "MangaHistoryEntry",
    # anilist
    "AniListSearchResult",
    "AniListTitle",
    "AniListAnimeStatistics",
    "AniListStatistics",
    "AniListViewerInfo",
    "AiringAnimeEntry",
    "AniListAnime",
    "AnimeMetadataEntry",
    "AniListManga",
    "AniListMediaListEntry",
    "AniListActivity",
    "AniListRelationNode",
    "AniListRelationEdge",
    # cache
    "ScraperCacheData",
    "CacheStats",
    # download
    "DownloadedEpisode",
    "DownloadResult",
    "AnimeDownloadHistory",
    "AnimeDownloadDatabase",
    "OfflineSyncQueueEntry",
    "OfflineSyncQueue",
    # update / video
    "VideoUrl",
    "UpdateCheckState",
    "UpdateCheckResult",
]
