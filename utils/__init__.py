"""Utilities and helper functions.

Consolidated utilities:
- video_player: MPV integration for video playback with IPC support for episode navigation
- scraper_cache: SQLite-based episode caching
- cache_manager: Cache management operations
- anilist_discovery: AniList ID discovery

Key exports from video_player:
- play_episode(): New IPC-aware playback with episode navigation
- play_video(): Legacy blocking playback (backward compatible)
- VideoPlaybackResult: NamedTuple for playback results with action data
"""

from utils import (
    anilist_discovery,
    cache_manager,
    scraper_cache,
    video_player,
)
from utils.video_player import (
    VideoPlaybackResult,
    play_episode,
    play_video,
)

__all__ = [
    "anilist_discovery",
    "cache_manager",
    "scraper_cache",
    "video_player",
    # New IPC-aware exports
    "VideoPlaybackResult",
    "play_episode",
    "play_video",
]
