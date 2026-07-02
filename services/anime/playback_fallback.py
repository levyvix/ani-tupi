"""Automatic source fallback logic for episode playback.

When MPV fails to play an episode from one source, this module
tries the next available source automatically until one works
or all sources are exhausted.
"""

from typing import Callable, NamedTuple
from utils.video_player import VideoPlayer, VideoPlaybackResult
from utils.logging import get_logger

logger = get_logger(__name__)


# Exit code 3 indicates user abort (Ctrl+C) - stop immediately, don't fallback
MPV_USER_ABORT_CODE = 3


class PlaybackFallbackResult(NamedTuple):
    """Result from fallback-aware episode playback.

    Attributes:
        playback_result: The VideoPlaybackResult from the successful (or last) play attempt
        source_used: Name of the source that succeeded, or None if all failed
        sources_tried: List of (source_name, exit_code) for all attempted sources
        all_failed: True if every source returned a failure exit code
    """

    playback_result: VideoPlaybackResult
    source_used: str | None
    sources_tried: list[tuple[str, int]]
    all_failed: bool


def play_episode_with_fallback(
    player: VideoPlayer,
    sources: list[tuple[str, str] | tuple[str, str, str | None]],
    anime_title: str,
    episode_number: int,
    total_episodes: int,
    use_ipc: bool = True,
    debug: bool = False,
    anilist_id: int | None = None,
    anilist_episodes: int | None = None,
    extractor: Callable[[str, str], str | None] | None = None,
) -> PlaybackFallbackResult:
    """Play episode trying each source in order until one succeeds.

    A source is considered failed when MPV returns a non-zero exit code
    that is NOT exit code 3 (user abort). Exit code 3 means the user
    intentionally cancelled — in that case we stop immediately.

    Args:
        player: VideoPlayer instance with session state (autoplay, etc.)
    sources: List of (url, source_name) or (url, source_name, referrer) tuples sorted by priority.
        When ``extractor`` is provided, the first tuple element is treated as a
        page URL and resolved to a playable video URL lazily, on demand.
        anime_title: Anime title for display and IPC context
        episode_number: Current episode number (1-indexed)
        total_episodes: Total episodes in scraper
        use_ipc: Enable IPC socket for keybinding events
        debug: Skip actual playback (testing mode)
        anilist_id: AniList ID for progress sync
        anilist_episodes: Total episodes from AniList
        extractor: Optional ``(page_url, source_name) -> video_url | None`` callback.
            When set, video URLs are extracted lazily just before each source is
            played, so lower-priority sources are never touched once a higher
            one works. When None, tuple elements are already-extracted video URLs.

    Returns:
        PlaybackFallbackResult with outcome details
    """
    if not sources:
        error_result = VideoPlaybackResult(exit_code=2, action="quit", data=None)
        return PlaybackFallbackResult(
            playback_result=error_result,
            source_used=None,
            sources_tried=[],
            all_failed=True,
        )

    sources_tried: list[tuple[str, int]] = []

    for source_entry in sources:
        first, source = source_entry[0], source_entry[1]

        if extractor is not None:
            # Lazy extraction: `first` is a page URL; resolve to a video URL
            # only now, so lower-priority sources stay untouched on early success.
            page_url = first
            try:
                url = extractor(page_url, source)
            except Exception as e:
                logger.debug(f"[{source}] erro ao extrair vídeo: {e!r}")
                continue
            if not url:
                logger.debug(f"[{source}] não retornou URL de vídeo, pulando")
                continue
            referrer = source_entry[2] if len(source_entry) > 2 else page_url
        else:
            url = first
            referrer = source_entry[2] if len(source_entry) > 2 else None

        # Show progress if multiple sources
        if len(sources) > 1:
            attempt_num = len(sources_tried) + 1
            logger.info(f"   🎬 Tentando fonte {attempt_num}/{len(sources)}: {source}")

        result = player.play_episode(
            url=url,
            anime_title=anime_title,
            episode_number=episode_number,
            total_episodes=total_episodes,
            source=source,
            use_ipc=use_ipc,
            debug=debug,
            anilist_id=anilist_id,
            anilist_episodes=anilist_episodes,
            referrer=referrer,
        )

        sources_tried.append((source, result.exit_code))

        # User intentionally aborted — respect their intent, stop immediately
        if result.exit_code == MPV_USER_ABORT_CODE:
            return PlaybackFallbackResult(
                playback_result=result,
                source_used=source,
                sources_tried=sources_tried,
                all_failed=False,
            )

        # Successful playback (exit_code == 0) OR user action (next, previous, etc.)
        if result.exit_code == 0:
            return PlaybackFallbackResult(
                playback_result=result,
                source_used=source,
                sources_tried=sources_tried,
                all_failed=False,
            )

        # Failure — log and try next source
        failed_sources_count = len(sources_tried)
        remaining = len(sources) - failed_sources_count

        logger.info(f"   ❌ Fonte '{source}' falhou (código: {result.exit_code})")

        if remaining > 0:
            logger.info(f"   🔄 Tentando próxima fonte ({remaining} restante(s))...")

    # All sources exhausted
    tried_names = [s for s, _ in sources_tried]
    logger.info(f"\n❌ Nenhuma fonte funcionou para o episódio {episode_number}.")
    logger.info(f"   Fontes tentadas: {', '.join(tried_names)}")
    logger.info("   💡 Tente trocar de fonte manualmente ou verifique sua conexão.")

    last_result = VideoPlaybackResult(exit_code=2, action="quit", data=None)
    return PlaybackFallbackResult(
        playback_result=last_result,
        source_used=None,
        sources_tried=sources_tried,
        all_failed=True,
    )
