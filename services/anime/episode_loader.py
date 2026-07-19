"""Episode list loading logic.

Handles loading episodes from cache or by scraping via the repository.
"""

import json

from models.config import get_data_path
from services import ui_bridge
from services.repository import rep
from services.anilist.scraper_cache import get_scraper_cache, set_scraper_cache
from services.anime.mappings import load_anilist_urls
from utils.logging import get_logger

logger = get_logger(__name__)

# Use centralized path function from config
HISTORY_PATH = get_data_path()


def _read_local_progress(selected_anime: str) -> int:
    """Return the next episode to watch based on local history (0 if none)."""
    try:
        history_file = HISTORY_PATH / "history.json"
        with history_file.open() as f:
            history_data = json.load(f)
            if selected_anime in history_data:
                return history_data[selected_anime][1] + 1
    except (OSError, KeyError, IndexError):
        pass  # No local history
    return 0


def _load_episode_list(
    selected_anime: str,
    saved_title: str | None,
    saved_source: str | None,
    saved_url: str | None,
    anilist_id: int,
) -> tuple[list | None, int]:
    """Load the episode list from cache or by scraping.

    Returns ``(episode_list, scraper_episode_count)``. ``episode_list`` is
    ``None`` when loading failed (no episodes could be scraped).
    """
    cache_data = get_scraper_cache(selected_anime)

    if cache_data:
        logger.info(f"ℹ️  Usando cache ({cache_data.episode_count} eps disponíveis)")
        rep.search_episodes(selected_anime)
        return cache_data.episode_urls, cache_data.episode_count

    if selected_anime == saved_title:
        saved_urls = load_anilist_urls(anilist_id) if anilist_id else {}
        if saved_urls:
            sources_list = ", ".join(sorted(saved_urls.keys()))
            logger.info(f"📺 Carregando '{selected_anime}' da fonte {sources_list}...")
            for src, url in saved_urls.items():
                rep.add_anime(selected_anime, url, src)
        elif saved_url and saved_source:
            logger.info(f"📺 Carregando '{selected_anime}' da fonte {saved_source}...")
            rep.add_anime(selected_anime, saved_url, saved_source)

    with ui_bridge.loading("Carregando episódios..."):
        rep.search_episodes(selected_anime)
    episode_list = rep.get_episode_list(selected_anime)
    scraper_episode_count = len(episode_list)

    if not episode_list:
        logger.info(
            "\n❌ Nenhum episódio carregado — todos os scrapers falharam (timeout ou erro de rede)."
        )
        logger.info("   Tente novamente em alguns instantes.")
        ui_bridge.prompt("\nPressione Enter para voltar...")
        return None, 0

    set_scraper_cache(selected_anime, scraper_episode_count, episode_list)
    return episode_list, scraper_episode_count
