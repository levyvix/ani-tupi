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
    """Play episode using rank-major fallback until one attempt succeeds.

    Candidates are tried by quality rank across all sources: the best-quality
    URL (rank 0) of every source is attempted first, then the next-best (rank 1)
    of every source, and so on. This prefers high quality everywhere before
    falling back to lower-quality streams.

    An attempt fails when MPV returns a non-zero exit code that is NOT exit
    code 3 (user abort). Exit code 3 means the user intentionally cancelled —
    in that case we stop immediately.

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

    # Lazily extract each source's candidate URLs the first time we reach it,
    # then cache so the rank-major loop below can revisit every source per rank.
    candidate_cache: dict[int, list[str]] = {}
    referrer_cache: dict[int, str | None] = {}

    def get_candidates(idx: int) -> list[str]:
        if idx in candidate_cache:
            return candidate_cache[idx]
        entry = sources[idx]
        first, source = entry[0], entry[1]
        if extractor is not None:
            try:
                candidates = _normalize_candidate_urls(extractor(first, source))
            except Exception as e:
                logger.debug(f"[{source}] erro ao extrair vídeo: {e!r}")
                candidates = []
            referrer_cache[idx] = entry[2] if len(entry) > 2 else first
        else:
            candidates = [first]
            referrer_cache[idx] = entry[2] if len(entry) > 2 else None
        if not candidates:
            logger.debug(f"[{source}] não retornou URL de vídeo, pulando")
        candidate_cache[idx] = candidates
        return candidates

    # Rank-major playback: try candidate #rank of every source before moving to
    # the next (lower-quality) rank. rank 0 = best quality across all sources.
    rank = 0
    while True:
        played_at_rank = False
        for idx in range(len(sources)):
            source = sources[idx][1]
            candidates = get_candidates(idx)
            if rank >= len(candidates):
                continue
            played_at_rank = True
            url = candidates[rank]

            attempt_num = len(sources_tried) + 1
            if len(sources) > 1:
                logger.info(
                    f"   🎬 Tentativa {attempt_num}: {source} "
                    f"(qualidade {rank + 1}/{len(candidates)})"
                )

            logger.debug(f"[{source}] reproduzindo URL (rank {rank}): {url}")

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
                referrer=referrer_cache[idx],
            )
            last_result = result
            sources_tried.append((source, result.exit_code))

            if result.exit_code in (MPV_USER_ABORT_CODE, 0):
                return PlaybackFallbackResult(
                    playback_result=result,
                    source_used=source,
                    sources_tried=sources_tried,
                    all_failed=False,
                )

            logger.info(
                f"   ❌ '{source}' (qualidade {rank + 1}) falhou (código: {result.exit_code})"
            )

        if not played_at_rank:
            break
        rank += 1

    tried_names = list(dict.fromkeys(s for s, _ in sources_tried))
    logger.info(f"\n❌ Nenhuma fonte funcionou para o episódio {episode_number}.")
    logger.info(f"   Fontes tentadas: {', '.join(tried_names)}")
    logger.info("   💡 Tente trocar de fonte manualmente ou verifique sua conexão.")

    return PlaybackFallbackResult(
        playback_result=last_result,
        source_used=None,
        sources_tried=sources_tried,
        all_failed=True,
    )
