"""AniList progress synchronization.

Handles syncing watched episode progress to AniList and managing status transitions.
"""

from models.models import Status
from services.anilist import anilist_client
from utils.logging import get_logger

logger = get_logger(__name__)


def _sync_anilist_progress(
    anilist_id: int,
    episode: int,
    num_episodes: int,
) -> None:
    """Sync watched episode progress to AniList and update status if needed.

    Handles PLANNING → CURRENT promotion, CURRENT → COMPLETED on last episode.
    Logs warnings on failure without raising.

    Args:
        anilist_id: AniList media ID
        episode: Episode number just watched (1-indexed)
        num_episodes: Total episodes available (from scrapers)
    """
    if not anilist_client.is_authenticated() or not anilist_id:
        return

    if not anilist_client.is_in_any_list(anilist_id):
        logger.info("📝 Adicionando à sua lista do AniList...")
        anilist_client.add_to_list(anilist_id, Status.CURRENT)
    else:
        entry = anilist_client.get_media_list_entry(anilist_id)
        if entry:
            if entry.status == "PLANNING":
                logger.info("📝 Movendo de 'Planejo Assistir' para 'Assistindo'...")
                anilist_client.add_to_list(anilist_id, Status.CURRENT)
            elif entry.status == "CURRENT" and episode == num_episodes:
                logger.info("✅ Marcando como 'Completo'...")
                anilist_client.change_status(anilist_id, Status.COMPLETED)

    logger.info(f"🔄 Sincronizando progresso com AniList (Ep {episode})...")
    success = anilist_client.update_progress(anilist_id, episode)
    if success:
        logger.info("✅ Progresso salvo no AniList!")
    else:
        viewer = anilist_client.get_viewer_info()
        if not viewer:
            logger.info("⚠️  Token do AniList expirou")
            logger.info("   Execute: ani-tupi anilist auth")
        else:
            logger.info("⚠️  Não foi possível salvar no AniList (continuando...)")
