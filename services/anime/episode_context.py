"""Episode navigation context helpers.

Provides episode context information for playback navigation
(next, previous, reload) used by MPV IPC handlers.
"""

from models import EpisodeContext
from services.repository import rep
from utils.logging import get_logger

logger = get_logger(__name__)


def get_next_episode_context(
    anime_title: str,
    current_episode: int,
) -> EpisodeContext | None:
    """Get episode context for next episode (used by IPC handlers).

    Args:
        anime_title: Name of anime
        current_episode: Current episode number (1-indexed)

    Returns:
        EpisodeContext with url, title, episode info, or None if no next episode
    """

    episode_list = rep.get_episode_list(anime_title)
    if not episode_list:
        return None

    # Convert to 0-based index
    next_idx = current_episode  # Already incremented from IPC
    if next_idx >= len(episode_list):
        # No next episode available
        return None

    try:
        next_episode_title = episode_list[next_idx]
        # Get URL from repository if available
        url_and_source = rep.get_episode_url_and_source(anime_title, next_idx + 1)
        next_url = url_and_source[0] if url_and_source else None
        if not next_url:
            logger.info("Nao foi possivel encontrar a url do proximo episodio")
            return None

        return EpisodeContext(
            url=next_url,
            title=next_episode_title,
            episode=next_idx + 1,  # Convert back to 1-indexed
            total=len(episode_list),
        )
    except (IndexError, KeyError):
        return None
