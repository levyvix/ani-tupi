"""Random anime service - picks a random anime from user's AniList and plays it.

This service provides functionality to:
- Fetch user's anime list from AniList (Watching + Plan to Watch)
- Filter out completed anime
- Pick a random anime from the list
- Search for the anime in available sources
- Start playback from first non-watched episode
"""

import random
from dataclasses import dataclass

from models.models import AniListMediaListEntry
from services.anilist_service import anilist_client
from services.repository import rep
from services.anime.playback_service import (
    prepare_playback_from_search,
    PlaybackContext,
    get_episode_url_and_source,
    navigate_episodes,
    sync_progress_to_anilist,
)
from utils.logging import get_logger
from utils.video_player import VideoPlayer
from ui.components import loading, menu_navigate
from services.history_service import save_history

logger = get_logger(__name__)


@dataclass
class RandomAnimeResult:
    """Result of picking a random anime."""

    success: bool
    title: str | None = None
    anilist_id: int | None = None
    cover: str | None = None
    progress: int = 0
    error_message: str | None = None


class RandomAnimeService:
    """Service for picking and playing a random anime from user's AniList."""

    def __init__(self):
        self.client = anilist_client

    def get_user_anime_list(self) -> list[AniListMediaListEntry]:
        """Fetch user's anime list (Watching + Plan to Watch).

        Returns:
            List of anime entries with title, id, progress, etc.
        """
        if not self.client.is_authenticated():
            return []

        watching = self.client.get_user_list("CURRENT") or []
        planning = self.client.get_user_list("PLANNING") or []

        all_anime = watching + planning
        return all_anime

    def filter_excluding_completed(
        self, anime_list: list[AniListMediaListEntry]
    ) -> list[AniListMediaListEntry]:
        """Filter out anime that are COMPLETED or still RELEASING.

        Args:
            anime_list: List of anime entries

        Returns:
            Filtered list without completed and airing anime
        """
        filtered = []
        for entry in anime_list:
            if entry.status == "COMPLETED":
                continue
            if entry.media and entry.media.status == "RELEASING":
                continue
            filtered.append(entry)
        return filtered

    def get_anime_info(self, anime_entry: AniListMediaListEntry) -> RandomAnimeResult:
        """Get anime details from an entry.

        Args:
            anime_entry: Anime entry from AniList

        Returns:
            RandomAnimeResult with title, id, cover, progress
        """
        media = anime_entry.media
        if not media:
            return RandomAnimeResult(success=False, error_message="Invalid anime entry")

        title = media.title.romaji or media.title.english or "Unknown"
        anilist_id = media.id
        progress = anime_entry.progress or 0

        return RandomAnimeResult(
            success=True,
            title=title,
            anilist_id=anilist_id,
            cover=None,
            progress=progress,
        )

    def search_and_prepare(
        self, anime_title: str, start_episode: int = 0
    ) -> PlaybackContext | None:
        """Search for anime and prepare playback context.

        Args:
            anime_title: Title to search for
            start_episode: Episode index to start from (0-indexed)

        Returns:
            PlaybackContext or None if not found
        """
        with loading(f"Buscando {anime_title}..."):
            rep.search_anime(anime_title, verbose=False)
            titles = rep.get_anime_titles(anime_title)

        if not titles:
            return None

        selected = titles[0]

        with loading("Carregando episódios..."):
            rep.search_episodes(selected)

        ctx = prepare_playback_from_search(selected, episode_idx=start_episode, source=None)

        return ctx

    def find_available_anime(
        self, anime_list: list[AniListMediaListEntry]
    ) -> tuple[AniListMediaListEntry, PlaybackContext] | None:
        """Find an anime from the list that's available in sources.

        Tries each anime until one is found in the scrapers.
        Starts from user's progress and finds first available episode.

        Args:
            anime_list: List of anime entries from AniList

        Returns:
            Tuple of (anime_entry, context) or None if none found
        """
        max_tries = 10
        for entry in anime_list[:max_tries]:
            info = self.get_anime_info(entry)
            if not info.success:
                continue

            ctx = self.search_and_prepare(info.title, start_episode=info.progress)
            if ctx:
                first_available = self._find_first_available_episode(ctx)
                if first_available > 0:
                    ctx = navigate_episodes(ctx, "choose", first_available - 1)
                    return (entry, ctx)

        return None

    def _find_first_available_episode(self, ctx: PlaybackContext) -> int:
        """Find the first episode that has a video URL available.

        Args:
            ctx: Playback context

        Returns:
            Episode number (1-indexed) that's available, or 0 if none found
        """
        for ep in range(1, min(ctx.num_episodes + 1, 5)):
            url_result = get_episode_url_and_source(ctx.anime_title, ep)
            if url_result.success and url_result.player_url:
                return ep
        return 0

    def play_anime(self, ctx: PlaybackContext, args) -> None:
        """Start playing the anime and handle post-playback flow.

        Args:
            ctx: Playback context
            args: Command line arguments
        """
        player = VideoPlayer()
        episode = ctx.episode_idx + 1

        with loading("Buscando vídeo..."):
            url_result = get_episode_url_and_source(ctx.anime_title, episode)

        if not (url_result.success and url_result.player_url):
            logger.info("❌ Não foi possível encontrar o vídeo deste anime.")
            return

        player.play_episode(
            url=url_result.player_url,
            anime_title=ctx.anime_title,
            episode_number=episode,
            total_episodes=ctx.num_episodes,
            source=url_result.source or "unknown",
        )

        self.handle_post_playback(ctx, episode, url_result.source)

    def handle_post_playback(self, ctx: PlaybackContext, episode: int, source: str | None) -> None:
        """Handle post-playback confirmation and options.

        Args:
            ctx: Playback context
            episode: Episode number watched
            source: Video source name
        """
        confirm_options = ["✅ Sim, assisti até o final", "❌ Não, parei antes."]
        confirm = menu_navigate(
            confirm_options, msg=f"Você assistiu o episódio {episode} até o final?"
        )

        confirmed = confirm == "✅ Sim, assisti até o final"

        if confirmed:
            save_history(
                ctx.anime_title,
                episode - 1,
                ctx.anilist_id,
                source or "random",
                total_episodes=ctx.num_episodes,
            )

            if ctx.anilist_id:
                success = sync_progress_to_anilist(
                    ctx.anilist_id, episode, ctx.num_episodes, ctx.anime_title
                )
                if success:
                    logger.info("✅ Progresso salvo no AniList!")
                else:
                    logger.info("⚠️ Não foi possível salvar no AniList")

        if confirmed and ctx.anilist_id and episode == ctx.num_episodes:
            logger.info("🎉 Você completou a série!")
            return

        opts = []
        if episode < ctx.num_episodes:
            opts.append("▶️ Próximo episódio")
        opts.append("🔁 Replay")
        opts.append("🔙 Sair")

        selected = menu_navigate(opts, msg="O que quer fazer agora?")

        if selected == "▶️ Próximo episódio":
            ctx = navigate_episodes(ctx, "next")
            self.play_anime(ctx, None)
        elif selected == "🔁 Replay":
            self.play_anime(ctx, None)


def handle_random_anime(args) -> None:
    """Main entry point for --random flag.

    Args:
        args: Command line arguments
    """
    service = RandomAnimeService()

    if not service.client.is_authenticated():
        logger.info("❌ Você precisa estar autenticado no AniList para usar --random")
        logger.info("   Execute: ani-tupi anilist auth")
        return

    with loading("Buscando sua lista..."):
        anime_list = service.get_user_anime_list()

    if not anime_list:
        logger.info("❌ Sua lista está vazia ou você não tem anime em Watching/Plan to Watch")
        return

    available_anime = service.filter_excluding_completed(anime_list)

    if not available_anime:
        logger.info(
            "❌ Você não tem anime disponível para sortear (todos Completed ou em lançamento)"
        )
        return

    random.shuffle(available_anime)

    result = service.find_available_anime(available_anime)
    if not result:
        logger.info("❌ Nenhum anime da sua lista está disponível nas fontes")
        return

    picked, ctx = result
    info = service.get_anime_info(picked)

    logger.info(f"🎲 {ctx.anime_title}")
    if info.progress > 0:
        logger.info(f"   Episódio {info.progress + 1} (você está em {info.progress})")
    else:
        logger.info(f"   {ctx.num_episodes} eps")

    service.play_anime(ctx, args)
