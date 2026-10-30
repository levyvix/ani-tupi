"""Deterministic smoke coverage for the real anime search repository."""

from dataclasses import dataclass, field
from threading import Event

import httpx
import pytest

from models.models import AnimeMetadata, ScrapedEpisodes
from utils import cache as cache_module
from utils.cache import DiskCache


@dataclass
class SearchSmokePlugin:
    """Minimal scraper adapter that returns a real anime metadata model."""

    name: str = "search-smoke"
    queries: list[str] = field(default_factory=list)

    def search_anime(self, query: str) -> list[AnimeMetadata]:
        self.queries.append(query)
        return [
            AnimeMetadata(
                title="Dandadan",
                url="https://example.test/anime/dandadan",
                source=self.name,
                params={"language": "subtitled"},
            )
        ]

    def search_episodes(self, anime: str, url: str, params: dict | None) -> list[ScrapedEpisodes]:
        return []

    def search_player_src(self, url: str, container: list, event: Event) -> None:
        return None


@pytest.fixture
def search_repository(repository, temp_dir, monkeypatch):
    """Use the real repository and disk cache, isolated to a temporary path."""
    monkeypatch.setattr(cache_module, "_global_cache", DiskCache(temp_dir / "cache"))
    plugin = SearchSmokePlugin()
    repository.register(plugin)
    return repository, plugin


def test_search_repository_smoke_returns_metadata_without_network(search_repository, monkeypatch):
    """A real repository search should produce a usable result without HTTP."""
    repository, plugin = search_repository

    def reject_network(*args, **kwargs):
        raise AssertionError("The deterministic search smoke test must not use HTTP")

    monkeypatch.setattr(httpx, "request", reject_network)
    monkeypatch.setattr(httpx.Client, "request", reject_network)

    results = repository.search_anime("Dandadan", verbose=False)

    assert plugin.queries == ["Dandadan"]
    assert len(results.results) == 1
    anime = results.results[0]
    assert anime.title == "Dandadan"
    assert anime.sources == (
        ("https://example.test/anime/dandadan", "search-smoke", {"language": "subtitled"}),
    )
