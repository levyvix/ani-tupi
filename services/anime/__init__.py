"""Anime service modules - business logic for anime operations.

One module per service:
- ``search_service``: incremental search, filtering and ranking
- ``episode_service``: episode loading, selection, context and URL patterns
- ``playback_service``: extraction, source fallback and the playback flow
- ``anime_persistence``: AniList mappings and the user's source choice
- ``metadata_provider``: external anime metadata access
- plus AniList integration, source management and progress calculation
"""

from utils.title_normalization import normalize_anime_title
from .anime_persistence import (
    load_anilist_mapping,
    save_anilist_mapping,
    load_anilist_search_title,
)
from .episode_service import get_next_episode_context
from .anilist_integration import (
    offer_sequel_and_continue,
    anilist_anime_flow,
)
from .source_management import switch_anime_source
from .search_service import search_anime_flow
from services.anilist.anilist_service import AniListDiscoveryResult, discover_anilist_info
from .progress_service import (
    EpisodeProgressInfo,
    ProgressContext,
    get_episode_progress_info,
    calculate_watch_context,
)
from .playback_service import (
    PlaybackContext,
    EpisodePlaybackResult,
    prepare_playback_from_search,
    prepare_playback_from_history,
    get_episode_url_and_source,
    sync_progress_to_anilist,
    navigate_episodes,
)

__all__ = [
    "normalize_anime_title",
    "load_anilist_mapping",
    "save_anilist_mapping",
    "load_anilist_search_title",
    "get_next_episode_context",
    "offer_sequel_and_continue",
    "anilist_anime_flow",
    "switch_anime_source",
    "search_anime_flow",
    "AniListDiscoveryResult",
    "discover_anilist_info",
    "EpisodeProgressInfo",
    "ProgressContext",
    "get_episode_progress_info",
    "calculate_watch_context",
    "PlaybackContext",
    "EpisodePlaybackResult",
    "prepare_playback_from_search",
    "prepare_playback_from_history",
    "get_episode_url_and_source",
    "sync_progress_to_anilist",
    "navigate_episodes",
]
