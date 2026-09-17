"""Interactive configuration for per-anime airing download sources."""

from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from models.download import AiringSourceBinding, AiringSourceCandidate
from services.anime.airing_downloads import AiringDownloadsService
from services.anime.airing_sources import AiringSourceStore
from services.anime.source_contexts import binding_from_source_candidates
from services.anilist.client import AiringWatchQueryResult, anilist_client
from services.core import ui_bridge
from services.repository import rep
from utils.logging import get_logger
from utils.title_normalization import dedup_signature, signatures_merge

logger = get_logger(__name__)


@dataclass(frozen=True)
class _SourceChoice:
    label: str
    binding: AiringSourceBinding


@dataclass
class _SourceGroup:
    title: str
    signature: tuple[str, int | None, frozenset[str]]
    season: int
    candidates: list[AiringSourceCandidate]


def _title(media: dict[str, Any]) -> str:
    title = media.get("title", {})
    if isinstance(title, dict):
        return str(title.get("romaji") or title.get("english") or title.get("native") or "Unknown")
    return str(title)


def _variant(title: str) -> str | None:
    lowered = title.lower()
    if "dublado" in lowered:
        return "dublado"
    if "legendado" in lowered:
        return "legendado"
    return None


def _episode_seasons(repository: Any, title: str, source: str, url: str, params: dict) -> list[int]:
    """Probe the selected source only to discover explicit season choices."""
    plugin = getattr(repository, "sources", {}).get(source)
    if plugin is None or not hasattr(plugin, "search_episodes"):
        return [1]
    try:
        batches = plugin.search_episodes(title, url, params) or []
    except Exception as exc:
        logger.info("Não foi possível consultar temporadas de %s: %s", source, exc)
        return [1]
    seasons = {
        season
        for batch in batches
        for season in [
            getattr(batch, "season", batch.get("season", 1) if isinstance(batch, dict) else 1)
        ]
        if isinstance(season, int) and season > 0
    }
    return sorted(seasons) or [1]


def _source_items_from_hierarchical_search(
    repository: Any, title: str
) -> list[tuple[str, tuple]] | None:
    """Reuse the normal hierarchical search and its populated source URLs."""
    if repository is not rep:
        return None
    try:
        from services.anime.search_service import contextual_incremental_search

        search = contextual_incremental_search(title, reference_title=title)
    except Exception as exc:
        logger.info("Busca hierárquica indisponível para %s: %s", title, exc)
        return None

    anime_to_urls = getattr(repository, "anime_to_urls", {})
    if not isinstance(anime_to_urls, dict):
        return None
    source_items: list[tuple[str, tuple]] = []
    for displayed_title in getattr(search, "titles_with_sources", ()):
        result_title = displayed_title.rsplit(" [", 1)[0]
        sources = anime_to_urls.get(result_title)
        if sources:
            source_items.append((result_title, tuple(sources)))
    return source_items


class AiringDownloadConfigurationService:
    """Walk current airing Watching entries and persist explicit choices."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        repository: Any | None = None,
        source_store: AiringSourceStore | None = None,
        menu: Callable[..., str | None] = ui_bridge.menu_navigate,
        progress: Callable[..., Any] = ui_bridge.loading,
    ) -> None:
        self.client = client or anilist_client
        self.repository = repository or rep
        self.source_store = source_store or AiringSourceStore()
        self.menu = menu
        self.progress = progress

    def configure(self) -> int:
        result = AiringDownloadsService(
            client=self.client,
            repository=self.repository,
            source_store=self.source_store,
        ).query_watching()
        if isinstance(result, AiringWatchQueryResult) and not result.ok:
            logger.error(
                "Falha ao consultar Watching no AniList: %s",
                result.error or result.error_kind,
            )
            return 1

        entries = (
            result.entries if isinstance(result, AiringWatchQueryResult) else list(result or [])
        )
        for entry in entries:
            self._configure_entry(entry)
        return 0

    def _configure_entry(self, entry: dict[str, Any]) -> None:
        media = entry.get("media", {})
        if not isinstance(media, dict):
            return
        anilist_id = media.get("id")
        if not isinstance(anilist_id, int) or anilist_id <= 0:
            return
        anime_title = _title(media)
        record = self.source_store.load(anilist_id)
        current = record.binding if record else None
        choices = self._search_choices(anime_title)
        options: list[str] = []
        labels: dict[str, _SourceChoice] = {}
        if current is not None:
            keep = f"✅ Manter {current.source}"
            options.append(keep)
            options.append("🗑️ Remover preferência explícita")
            labels[keep] = _SourceChoice(keep, current)
        for choice in choices:
            options.append(choice.label)
            labels[choice.label] = choice
        options.append("⏭️ Pular")
        selected = self.menu(options, msg=f"Fonte para pré-download: {anime_title}")
        if not selected or selected == "⏭️ Pular":
            return
        if selected == "🗑️ Remover preferência explícita":
            self.source_store.clear_configured(anilist_id)
            return
        choice = labels.get(selected)
        if choice is not None:
            self.source_store.save_binding(anilist_id, choice.binding)

    def _search_choices(self, anime_title: str) -> list[_SourceChoice]:
        self.repository.clear_search_results()
        try:
            with self.progress(f"Buscando '{anime_title}'..."):
                source_items = _source_items_from_hierarchical_search(self.repository, anime_title)
                if source_items is None:
                    results = self.repository.search_anime(anime_title, verbose=False)
                    source_items = [
                        (getattr(result, "title", anime_title), getattr(result, "sources", ()))
                        for result in getattr(results, "results", ())
                    ]
        except Exception as exc:
            logger.info("Busca sem resultado para %s: %s", anime_title, exc)
            return []

        source_requests: list[tuple[str, str, str, dict]] = []
        for result_title, sources in source_items:
            for source_item in sources:
                if not isinstance(source_item, (tuple, list)) or len(source_item) < 3:
                    continue
                url, source, params = source_item[:3]
                if isinstance(url, str) and isinstance(source, str):
                    source_requests.append(
                        (result_title, url, source, params if isinstance(params, dict) else {})
                    )

        def discover(
            request: tuple[str, str, str, dict],
        ) -> tuple[tuple[str, str, str, dict], list[int]]:
            result_title, url, source, params = request
            return request, _episode_seasons(self.repository, result_title, source, url, params)

        season_results: list[tuple[tuple[str, str, str, dict], list[int]]] = []
        if source_requests:
            with ThreadPoolExecutor(max_workers=min(8, len(source_requests))) as executor:
                season_results = list(executor.map(discover, source_requests))

        groups: list[_SourceGroup] = []
        for (result_title, url, source, params), seasons in season_results:
            signature = dedup_signature(result_title)
            for season in seasons:
                canonical_season = signature[1] or season
                candidate = AiringSourceCandidate(
                    title=result_title,
                    source=source,
                    anime_url=url,
                    params=params,
                    variant=_variant(result_title),
                    season=season,
                )
                group = next(
                    (
                        item
                        for item in groups
                        if item.season == canonical_season
                        and signatures_merge(item.signature, signature)
                    ),
                    None,
                )
                if group is None:
                    groups.append(
                        _SourceGroup(result_title, signature, canonical_season, [candidate])
                    )
                else:
                    if not any(
                        existing.source == candidate.source
                        and existing.anime_url == candidate.anime_url
                        and existing.season == candidate.season
                        for existing in group.candidates
                    ):
                        group.candidates.append(candidate)

        choices: list[_SourceChoice] = []
        for group in groups:
            binding = binding_from_source_candidates(group.title, group.candidates)
            if binding is None:
                continue
            sources = ", ".join(
                dict.fromkeys(
                    [binding.source, *(candidate.source for candidate in binding.alternatives)]
                )
            )
            label = f"📺 {group.title} [{sources}] / temporada {group.season}"
            choices.append(_SourceChoice(label, binding))
        return choices


def configure_airing_downloads(**kwargs: Any) -> int:
    """Configure source bindings through the interactive service."""
    return AiringDownloadConfigurationService(**kwargs).configure()


def configure(**kwargs: Any) -> int:
    """Short command adapter used by ``commands.airing_downloads``."""
    return configure_airing_downloads(**kwargs)


__all__ = ["AiringDownloadConfigurationService", "configure", "configure_airing_downloads"]
