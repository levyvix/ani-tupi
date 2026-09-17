"""Shared source-context construction for search, playback, and airing."""

from __future__ import annotations

from typing import Any

from models.config import settings
from models.download import AiringSourceBinding, AiringSourceCandidate

__all__ = ["binding_from_source_candidates", "source_candidates_for", "source_names_for"]


def _source_variant(title: str) -> str | None:
    lowered = title.lower()
    if "dublado" in lowered:
        return "dublado"
    if "legendado" in lowered:
        return "legendado"
    return None


def source_candidates_for(
    repository: Any,
    repository_title: str,
    selected_source: str | None = None,
) -> list[AiringSourceCandidate]:
    """Convert repository search results into ordered source contexts."""
    source_map = getattr(repository, "anime_to_urls", {})
    entries = source_map.get(repository_title, ()) if isinstance(source_map, dict) else ()
    allowed = (
        {part.strip() for part in selected_source.split(",") if part.strip()}
        if selected_source
        else None
    )
    candidates: list[AiringSourceCandidate] = []
    for item in entries:
        if not isinstance(item, (tuple, list)) or len(item) < 3:
            continue
        anime_url, source, params = item[:3]
        if not isinstance(anime_url, str) or not isinstance(source, str):
            continue
        if allowed is not None and source not in allowed:
            continue
        try:
            candidate = AiringSourceCandidate(
                title=repository_title,
                source=source,
                anime_url=anime_url,
                params=params if isinstance(params, dict) else {},
                variant=_source_variant(repository_title),
            )
        except ValueError:
            continue
        if not any(
            existing.source == candidate.source and existing.anime_url == candidate.anime_url
            for existing in candidates
        ):
            candidates.append(candidate)

    priority = {name: index for index, name in enumerate(settings.plugins.priority_order)}
    return sorted(
        candidates,
        key=lambda candidate: (
            priority.get(candidate.source, len(priority)),
            candidate.source,
            candidate.anime_url,
        ),
    )


def binding_from_source_candidates(
    title: str,
    candidates: list[AiringSourceCandidate],
    preferred_source: str | None = None,
) -> AiringSourceBinding | None:
    """Create one aggregate binding while retaining every source context."""
    if not candidates:
        return None
    ordered = list(candidates)
    if preferred_source:
        preferred = next(
            (candidate for candidate in ordered if candidate.source == preferred_source),
            None,
        )
        if preferred is not None:
            ordered.remove(preferred)
            ordered.insert(0, preferred)
    primary, *alternatives = ordered
    return AiringSourceBinding(
        title=title,
        source=primary.source,
        anime_url=primary.anime_url,
        params=primary.params,
        variant=primary.variant,
        alternatives=alternatives,
    )


def source_names_for(binding: AiringSourceBinding) -> str:
    """Return the aggregate source label for a shared binding."""
    return ", ".join(
        dict.fromkeys([binding.source, *(candidate.source for candidate in binding.alternatives)])
    )
