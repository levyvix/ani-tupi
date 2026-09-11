"""Selection of safe airing episodes for a single monitor cycle.

This module intentionally stops at source selection and episode selection. It
does not download or update AniList progress.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from models.download import AiringEpisodeCandidate, AiringSourceBinding
from services.anilist.client import AiringWatchQueryResult, anilist_client
from services.anime.airing_sources import EffectiveAiringSource, get_effective_source
from services.repository import rep
from utils.logging import get_logger

__all__ = [
    "AiringDownloadSelectionError",
    "AiringMonitorQueryError",
    "AiringDownloadsService",
    "AiringEpisodeSelector",
    "filter_current_releasing",
    "select_published_episodes",
]


logger = get_logger(__name__)
_NUMBER_RE = re.compile(r"\d+")
_SPECIAL_WORDS = re.compile(r"\b(?:special|ova|ona|movie|recap|extra)\b", re.IGNORECASE)


class AiringMonitorQueryError(RuntimeError):
    """The current AniList list could not be obtained."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class AiringDownloadSelectionError(RuntimeError):
    """The linked source cannot provide an unambiguous episode list."""


@dataclass(frozen=True)
class AiringSelection:
    """Source context and the selected published episodes for one anime."""

    source: EffectiveAiringSource
    episodes: tuple[AiringEpisodeCandidate, ...]
    candidates_by_episode: dict[int, tuple[AiringEpisodeCandidate, ...]] = field(
        default_factory=dict
    )


def filter_current_releasing(entries: list[dict]) -> list[dict]:
    """Filter and deduplicate raw Watching entries defensively."""
    result: list[dict] = []
    seen_ids: set[int] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        list_status = entry.get("status")
        media = entry.get("media")
        if list_status is not None and list_status != "CURRENT":
            continue
        if not isinstance(media, dict) or media.get("status") != "RELEASING":
            continue
        media_id = media.get("id")
        if not isinstance(media_id, int) or media_id <= 0 or media_id in seen_ids:
            continue
        seen_ids.add(media_id)
        result.append(entry)
    return result


def _batch_values(batch: Any) -> tuple[list[str], list[str], str, int | None]:
    """Read the plugin episode contract without positional-number fallback."""
    titles = getattr(batch, "titles", None)
    urls = getattr(batch, "urls", None)
    source = getattr(batch, "source", None)
    season = getattr(batch, "season", None)
    if isinstance(batch, dict):
        titles = batch.get("titles")
        urls = batch.get("urls")
        source = batch.get("source")
        season = batch.get("season", 1)
    if not isinstance(titles, list) or not isinstance(urls, list) or not isinstance(source, str):
        raise AiringDownloadSelectionError("source returned an invalid episode batch")
    if len(titles) != len(urls):
        raise AiringDownloadSelectionError("source returned unaligned episode titles and URLs")
    return titles, urls, source, season


def _episode_number(title: str) -> int | None:
    if not isinstance(title, str) or _SPECIAL_WORDS.search(title):
        return None
    numbers = _NUMBER_RE.findall(title)
    if not numbers:
        return None
    number = int(numbers[-1])
    return number if number > 0 else None


def _future_airing_cutoff(media: dict, now: float) -> int | None:
    next_airing = media.get("nextAiringEpisode")
    if not isinstance(next_airing, dict):
        return None
    episode = next_airing.get("episode")
    airing_at = next_airing.get("airingAt")
    if not isinstance(episode, int) or episode < 1:
        return None
    if isinstance(airing_at, (int, float)) and airing_at > now:
        return episode
    return None


def select_published_episodes(
    entry: dict,
    binding: AiringSourceBinding,
    batches: list[Any],
    *,
    now: float | None = None,
) -> list[AiringEpisodeCandidate]:
    """Select only real, numbered episodes above AniList progress.

    A source list is treated as a set of explicit episode labels. Missing
    numbers remain missing; no positional fallback or range expansion is used.
    """
    if binding.season is None:
        raise AiringDownloadSelectionError("source season is ambiguous")
    media = entry.get("media")
    if not isinstance(media, dict) or media.get("status") != "RELEASING":
        return []

    progress = entry.get("progress", 0)
    progress = progress if isinstance(progress, int) and progress >= 0 else 0
    cutoff = _future_airing_cutoff(media, time.time() if now is None else now)
    candidates: dict[int, AiringEpisodeCandidate] = {}
    ambiguous: set[int] = set()

    for batch in batches or []:
        titles, urls, source, season = _batch_values(batch)
        if source != binding.source:
            raise AiringDownloadSelectionError(
                f"linked source returned data labelled as {source!r}"
            )
        if season != binding.season:
            continue
        for title, url in zip(titles, urls):
            source_number = _episode_number(title)
            if source_number is None or not isinstance(url, str):
                continue
            episode_number = binding.anilist_episode_number(source_number)
            if episode_number <= progress or (cutoff is not None and episode_number >= cutoff):
                continue
            try:
                candidate = AiringEpisodeCandidate(
                    episode_number=episode_number,
                    source_episode_number=source_number,
                    title=title,
                    url=url,
                    source=source,
                    season=season,
                )
            except ValueError:
                continue
            previous = candidates.get(episode_number)
            if previous is not None and previous.url != candidate.url:
                ambiguous.add(episode_number)
            else:
                candidates.setdefault(episode_number, candidate)

    return [candidates[number] for number in sorted(candidates) if number not in ambiguous]


class AiringDownloadsService:
    """Coordinate the monitor's read-only AniList and source selection."""

    def __init__(self, client=None, repository=None, source_store=None) -> None:
        self.client = client or anilist_client
        self.repository = repository or rep
        self.source_store = source_store

    def query_watching(self) -> AiringWatchQueryResult:
        """Return current releasing entries, retaining authentication/API errors."""
        result = self.client.get_watching_releasing_entries()
        if not isinstance(result, AiringWatchQueryResult):
            # Keep the service usable with a narrow legacy test double while
            # still making a successful empty list explicit.
            entries = result if isinstance(result, list) else []
            return AiringWatchQueryResult(filter_current_releasing(entries))
        if not result.ok:
            return result
        return AiringWatchQueryResult(filter_current_releasing(result.entries))

    def get_watching_releasing(self) -> list[dict]:
        """Return entries or raise a typed error; an empty list is successful."""
        result = self.query_watching()
        if not result.ok:
            raise AiringMonitorQueryError(
                result.error_kind or "api", result.error or "query failed"
            )
        return result.entries

    def effective_source(self, anilist_id: int) -> EffectiveAiringSource:
        if hasattr(self.source_store, "effective"):
            return self.source_store.effective(anilist_id)
        return get_effective_source(anilist_id, self.source_store)

    def fetch_source_episodes(self, binding: AiringSourceBinding) -> list[Any]:
        """Refresh episodes from exactly the linked plugin and saved page."""
        sources = getattr(self.repository, "sources", {})
        plugin = sources.get(binding.source) if isinstance(sources, dict) else None
        if plugin is None:
            raise AiringDownloadSelectionError(f"source {binding.source!r} is unavailable")
        try:
            batches = plugin.search_episodes(binding.title, binding.anime_url, binding.params)
        except Exception as exc:
            raise AiringDownloadSelectionError(
                f"source {binding.source!r} failed to list episodes: {exc}"
            ) from exc
        return list(batches or [])

    @staticmethod
    def _source_bindings(binding: AiringSourceBinding) -> list[AiringSourceBinding]:
        """Expand one aggregate binding into its ordered source contexts."""
        primary = binding.model_copy(update={"alternatives": []})
        bindings = [primary]
        for alternative in binding.alternatives:
            bindings.append(
                binding.model_copy(
                    update={
                        "title": alternative.title,
                        "source": alternative.source,
                        "anime_url": alternative.anime_url,
                        "params": alternative.params,
                        "variant": alternative.variant,
                        "season": alternative.season,
                        "alternatives": [],
                    }
                )
            )
        return bindings

    def select_for_entry(self, entry: dict) -> AiringSelection:
        """Resolve one binding and merge published episodes across its sources."""
        media = entry.get("media") if isinstance(entry, dict) else None
        anilist_id = media.get("id") if isinstance(media, dict) else None
        if not isinstance(anilist_id, int) or anilist_id <= 0:
            raise AiringDownloadSelectionError("Watching entry has no valid AniList ID")
        source = self.effective_source(anilist_id)
        if source.binding is None:
            raise AiringDownloadSelectionError(source.reason or "no usable source binding")
        merged: dict[int, list[AiringEpisodeCandidate]] = {}
        errors: list[AiringDownloadSelectionError] = []
        fetched_source = False
        for binding in self._source_bindings(source.binding):
            try:
                batches = self.fetch_source_episodes(binding)
                episodes = select_published_episodes(entry, binding, batches)
            except AiringDownloadSelectionError as exc:
                errors.append(exc)
                continue
            fetched_source = True
            for episode in episodes:
                candidates = merged.setdefault(episode.episode_number, [])
                if not any(
                    item.source == episode.source and item.url == episode.url for item in candidates
                ):
                    candidates.append(episode)

        if not fetched_source and errors:
            raise AiringDownloadSelectionError(
                "all aggregated sources failed: " + "; ".join(str(error) for error in errors)
            ) from errors[-1]
        candidates_by_episode = {number: tuple(candidates) for number, candidates in merged.items()}
        episodes = tuple(
            candidates_by_episode[number][0] for number in sorted(candidates_by_episode)
        )
        return AiringSelection(source, episodes, candidates_by_episode)


AiringEpisodeSelector = AiringDownloadsService
