"""Fuzzy discovery matching tests for services.anilist.anilist_service.

Verifies that fuzzy title matching (auto_discover_anilist_id /
get_anilist_id_from_title) works from the consolidated
``services/anilist/discovery.py`` location. Only the external AniList HTTP
client (``anilist_client.search_anime``) is mocked; the fuzzy matching,
caching, and threshold logic run for real against a temporary disk cache.
"""

from unittest.mock import patch

from utils import cache as cache_module
from utils.cache import DiskCache
from models.models import AniListAnime, AniListTitle
from services.anilist import anilist_service as discovery


def _anime(anime_id: int, romaji: str, english: str | None = None) -> AniListAnime:
    return AniListAnime(id=anime_id, title=AniListTitle(romaji=romaji, english=english))


def test_get_anilist_id_from_title_returns_best_fuzzy_match(temp_dir, monkeypatch):
    """A near-identical scraper title resolves to the correct AniList ID."""
    disk_cache = DiskCache(cache_dir=temp_dir / "cache")
    monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

    search_results = [
        _anime(20, "Naruto"),
        _anime(1735, "Naruto Shippuuden", english="Naruto: Shippuden"),
    ]

    with patch.object(
        discovery.anilist_client, "search_anime", return_value=search_results
    ) as mock_search:
        anilist_id = discovery.get_anilist_id_from_title("Naruto Shippuden")

    assert anilist_id == 1735
    mock_search.assert_called_once_with("Naruto Shippuden")


def test_auto_discover_sorts_matches_by_score(temp_dir, monkeypatch):
    """auto_discover_anilist_id returns matches sorted by descending score."""
    disk_cache = DiskCache(cache_dir=temp_dir / "cache")
    monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

    search_results = [
        _anime(20, "Naruto"),
        _anime(1735, "Naruto Shippuuden"),
    ]

    with patch.object(discovery.anilist_client, "search_anime", return_value=search_results):
        results = discovery.auto_discover_anilist_id("naruto")

    assert results
    assert results[0].anilist_id == 20
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_get_anilist_id_from_title_no_results_returns_none(temp_dir, monkeypatch):
    """When AniList returns no candidates the result is None (and cached)."""
    disk_cache = DiskCache(cache_dir=temp_dir / "cache")
    monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

    with patch.object(discovery.anilist_client, "search_anime", return_value=[]) as mock_search:
        first = discovery.get_anilist_id_from_title("Totally Unknown Anime")
        # Second call should hit the negative cache, not the client again.
        second = discovery.get_anilist_id_from_title("Totally Unknown Anime")

    assert first is None
    assert second is None
    mock_search.assert_called_once()
