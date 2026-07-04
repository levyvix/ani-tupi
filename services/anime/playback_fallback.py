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


def _normalize_candidate_urls(urls: str | list[str] | None) -> list[str]:
    """Normalize extractor output to a deduplicated URL list."""
    if not urls:
        return []
    if isinstance(urls, str):
        return [urls]
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


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
    extractor: Callable[[str, str], str | list[str] | None] | None = None,
) -> PlaybackFallbackResult:
    """Play episode trying each source in order until one succeeds.

    A source is considered failed when MPV returns a non-zero exit code
    that is NOT exit code 3 (user abort) for every candidate URL from that
    source. Exit code 3 means the user intentionally cancelled — in that
    case we stop immediately.

    Args:
        player: VideoPlayer instance with session state (autoplay, etc.)
        sources: List of (url, source_name) or (url, source_name, referrer) tuples sorted by priority.
            When ``extractor`` is provided, the first tuple element is treated as a
            page URL and resolved to one or more playable video URLs lazily, on demand.
        anime_title: Anime title for display and IPC context
        episode_number: Current episode number (1-indexed)
        total_episodes: Total episodes in scraper
        use_ipc: Enable IPC socket for keybinding events
        debug: Skip actual playback (testing mode)
        anilist_id: AniList ID for progress sync
        anilist_episodes: Total episodes from AniList
        extractor: Optional ``(page_url, source_name) -> urls | None`` callback.
            May return a single URL or an ordered list of candidates to try with MPV
            before moving to the next source. When None, tuple elements are already
            extracted video URLs.

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
    last_result = VideoPlaybackResult(exit_code=2, action="quit", data=None)

    for source_entry in sources:
        first, source = source_entry[0], source_entry[1]

        if extractor is not None:
            page_url = first
            try:
                candidates = _normalize_candidate_urls(extractor(page_url, source))
            except Exception as e:
                logger.debug(f"[{source}] erro ao extrair vídeo: {e!r}")
                continue
            referrer = source_entry[2] if len(source_entry) > 2 else page_url
        else:
            candidates = [first]
            referrer = source_entry[2] if len(source_entry) > 2 else None

        if not candidates:
            logger.debug(f"[{source}] não retornou URL de vídeo, pulando")
            continue

        last_result = VideoPlaybackResult(exit_code=2, action="quit", data=None)

        for candidate_idx, url in enumerate(candidates, start=1):
            if len(sources) > 1:
                attempt_num = len(sources_tried) + 1
                if len(candidates) > 1:
                    logger.info(
                        f"   🎬 Tentando fonte {attempt_num}/{len(sources)}: {source} "
                        f"(candidato {candidate_idx}/{len(candidates)})"
                    )
                else:
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
            last_result = result

            if result.exit_code == MPV_USER_ABORT_CODE:
                sources_tried.append((source, result.exit_code))
                return PlaybackFallbackResult(
                    playback_result=result,
                    source_used=source,
                    sources_tried=sources_tried,
                    all_failed=False,
                )

            if result.exit_code == 0:
                sources_tried.append((source, 0))
                return PlaybackFallbackResult(
                    playback_result=result,
                    source_used=source,
                    sources_tried=sources_tried,
                    all_failed=False,
                )

            if len(candidates) > 1 and candidate_idx < len(candidates):
                logger.info(
                    f"   ↪️  Candidato {candidate_idx} falhou (código: {result.exit_code}), "
                    "tentando próximo..."
                )

        sources_tried.append((source, last_result.exit_code))

        failed_sources_count = len(sources_tried)
        remaining = len(sources) - failed_sources_count

        logger.info(f"   ❌ Fonte '{source}' falhou (código: {last_result.exit_code})")

        if remaining > 0:
            logger.info(f"   🔄 Tentando próxima fonte ({remaining} restante(s))...")

    tried_names = [s for s, _ in sources_tried]
    logger.info(f"\n❌ Nenhuma fonte funcionou para o episódio {episode_number}.")
    logger.info(f"   Fontes tentadas: {', '.join(tried_names)}")
    logger.info("   💡 Tente trocar de fonte manualmente ou verifique sua conexão.")

    return PlaybackFallbackResult(
        playback_result=last_result,
        source_used=None,
        sources_tried=sources_tried,
        all_failed=True,
    )
