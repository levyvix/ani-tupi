"""Explicit registry for "awaiting" episode URLs discovered via homepage search.

Some sources (e.g. AnimesDigital) expose freshly released episodes on their
homepage before the regular episode listing catches up. When the flow finds
such an episode, it records a direct episode-page URL here so the playback
layer can extract the video from it instead of re-scraping the listing.

This replaces the previous hidden state that lived as an attribute on the
``anilist_anime_flow`` function object. State is now explicit and shared
through this small module-level store, which both the AniList flow (writer)
and the playback service (reader) reference.
"""

from utils.logging import get_logger

logger = get_logger(__name__)


class AwaitingEpisodeRegistry:
    """Maps ``anime_title -> {episode_number: episode_page_url}``.

    Instances are cheap; a shared module-level instance (``registry``) is used
    by the running application, while tests can create isolated instances.
    """

    def __init__(self) -> None:
        self._urls: dict[str, dict[int, str]] = {}

    def set(self, anime_title: str, episode_number: int, episode_url: str) -> None:
        """Record a direct episode-page URL for an awaiting episode."""
        self._urls.setdefault(anime_title, {})[episode_number] = episode_url

    def get(self, anime_title: str, episode_number: int) -> str | None:
        """Return the recorded episode-page URL, or ``None`` if not awaiting."""
        return self._urls.get(anime_title, {}).get(episode_number)

    def clear(self, anime_title: str) -> None:
        """Drop any awaiting URLs recorded for ``anime_title``."""
        self._urls.pop(anime_title, None)


# Shared instance used by the application flows.
registry = AwaitingEpisodeRegistry()
