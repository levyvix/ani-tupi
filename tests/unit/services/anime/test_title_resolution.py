"""Tests for manual anime title resolution and fallback search flow."""

from __future__ import annotations

from argparse import Namespace
from contextlib import nullcontext
from unittest.mock import Mock, patch

from models.models import AniListAnime, AniListTitle, AnimeTitleResolution, ScraperCacheData
from services.anime.search import IncrementalSearchState, search_anime_flow
from services.anime.title_resolution import AniListTitleResolver, AnimeTitleResolver


class FakeCache:
    """Small in-memory cache for resolver tests."""

    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ttl=None):
        self.data[key] = value


class StaticProvider:
    """Static resolver provider for deterministic tests."""

    def __init__(self, name: str, result: AnimeTitleResolution | None):
        self.name = name
        self.result = result
        self.calls = 0

    def resolve(self, query: str) -> AnimeTitleResolution | None:
        self.calls += 1
        return self.result


def make_state(
    results: list[str], query: str = "query", word_count: int = 1
) -> IncrementalSearchState:
    """Create search state with a single result set."""
    state = IncrementalSearchState()
    if results:
        state.add_result(word_count=word_count, query=query, results=results, used_query=query)
    return state


def build_args(query: str, episode: int = 1, season=None) -> Namespace:
    """Build argparse namespace for manual search flow tests."""
    return Namespace(query=query, episode=episode, season=season)


def test_anilist_title_resolver_prefers_romaji_title():
    """AniList resolver should return romaji title and aliases when confidence is good."""
    result = AniListAnime(
        id=1,
        title=AniListTitle(
            romaji="Boku no Hero Academia",
            english="My Hero Academia",
            native="僕のヒーローアカデミア",
        ),
    )

    with patch(
        "services.anime.title_resolution.anilist_client.search_anime", return_value=[result]
    ):
        resolution = AniListTitleResolver().resolve("my hero")

    assert resolution is not None
    assert resolution.resolved_title == "Boku no Hero Academia"
    assert resolution.provider == "anilist"
    assert "My Hero Academia" in resolution.aliases


def test_anime_title_resolver_falls_back_to_jikan_and_caches():
    """Resolver should use Jikan when AniList yields nothing and cache the accepted result."""
    cache = FakeCache()
    weak_provider = StaticProvider("anilist", None)
    jikan_result = AnimeTitleResolution(
        original_query="my hero",
        resolved_title="Boku no Hero Academia",
        provider="jikan",
        confidence=92,
        aliases=("Boku no Hero Academia", "My Hero Academia"),
    )
    fallback_provider = StaticProvider("jikan", jikan_result)
    resolver = AnimeTitleResolver(providers=[weak_provider, fallback_provider], cache=cache)

    resolution = resolver.resolve("my hero")

    assert resolution == jikan_result
    assert weak_provider.calls == 1
    assert fallback_provider.calls == 1
    assert cache.data


def test_anime_title_resolver_reuses_cache_without_calling_provider():
    """Cached title resolutions should bypass provider calls on repeated queries."""
    cache = FakeCache()
    cached_result = AnimeTitleResolution(
        original_query="my hero",
        resolved_title="Boku no Hero Academia",
        provider="anilist",
        confidence=90,
        aliases=("Boku no Hero Academia",),
    )
    cache.set("title-resolution:anime:search:my-hero:any", cached_result.model_dump())
    provider = StaticProvider("anilist", None)
    resolver = AnimeTitleResolver(providers=[provider], cache=cache)

    resolution = resolver.resolve("my hero")

    assert resolution == cached_result
    assert provider.calls == 0


def test_anime_title_resolver_ignores_weak_match():
    """Weak matches should not be used for retrying manual searches."""
    cache = FakeCache()
    weak_result = AnimeTitleResolution(
        original_query="abc",
        resolved_title="Completely Different Title",
        provider="anilist",
        confidence=30,
        aliases=("Completely Different Title",),
    )
    provider = StaticProvider("anilist", weak_result)
    resolver = AnimeTitleResolver(providers=[provider], cache=cache)

    resolution = resolver.resolve("abc")

    assert resolution is None
    assert provider.calls == 1
    assert cache.data == {}


@patch("services.anime.search.loading", side_effect=lambda *args, **kwargs: nullcontext())
@patch("services.anime.search._resolve_search_query")
@patch("services.anime.search.get_cache")
def test_search_anime_flow_cache_hit_skips_resolution(
    mock_get_cache,
    mock_resolve_query,
    mock_loading,
):
    """Existing cache hits should keep the old behavior and skip title resolution."""
    mock_get_cache.return_value = ScraperCacheData(
        episode_urls=["https://example.com/ep1"],
        episode_count=1,
        timestamp=0,
    )

    mock_rep = Mock()
    mock_rep.get_available_seasons.return_value = [1]
    mock_rep.get_episode_list.return_value = ["Episode 1"]

    with patch("services.anime.search.rep", mock_rep):
        result = search_anime_flow(build_args("Dandadan"))

    assert result == ("Dandadan", 0, None)
    mock_rep.load_from_cache.assert_called_once()
    mock_rep.search_anime.assert_called_once_with("Dandadan", verbose=False)
    mock_resolve_query.assert_not_called()


@patch("services.anime.search.loading", side_effect=lambda *args, **kwargs: nullcontext())
@patch("services.anime.search.menu_navigate", return_value="Boku no Hero Academia [animefire]")
@patch(
    "services.anime.search._resolve_search_query",
    return_value=AnimeTitleResolution(
        original_query="my hero",
        resolved_title="Boku no Hero Academia",
        provider="anilist",
        confidence=91,
        aliases=("Boku no Hero Academia", "My Hero Academia"),
    ),
)
@patch("services.anime.search.get_cache", return_value=None)
@patch("services.anime.search.incremental_search_anime")
def test_search_anime_flow_retries_with_resolved_title(
    mock_incremental_search,
    mock_get_cache,
    mock_resolve_query,
    mock_menu,
    mock_loading,
):
    """Manual search should retry with the resolved title after direct search fails."""
    mock_incremental_search.side_effect = [
        (IncrementalSearchState(), []),
        (
            make_state(["Boku no Hero Academia [animefire]"], query="boku", word_count=1),
            ["Boku no Hero Academia [animefire]"],
        ),
    ]

    mock_rep = Mock()
    mock_rep.get_available_seasons.return_value = [1]
    mock_rep.get_episode_list.return_value = ["Episode 1"]

    with patch("services.anime.search.rep", mock_rep):
        result = search_anime_flow(build_args("my hero"))

    assert result == ("Boku no Hero Academia", 0, "animefire")
    assert mock_incremental_search.call_args_list[0].args == ("my hero",)
    assert mock_incremental_search.call_args_list[1].args == ("Boku no Hero Academia",)
    mock_resolve_query.assert_called_once_with("my hero")


@patch("services.anime.search.loading", side_effect=lambda *args, **kwargs: nullcontext())
@patch("services.anime.search._resolve_search_query", return_value=None)
@patch("services.anime.search.get_cache", return_value=None)
@patch(
    "services.anime.search.incremental_search_anime", return_value=(IncrementalSearchState(), [])
)
def test_search_anime_flow_fails_cleanly_when_resolution_fails(
    mock_incremental_search,
    mock_get_cache,
    mock_resolve_query,
    mock_loading,
):
    """Manual search should return cleanly when neither direct nor resolved search finds results."""
    mock_rep = Mock()

    with patch("services.anime.search.rep", mock_rep):
        result = search_anime_flow(build_args("unknown title"))

    assert result == (None, None, None)
    mock_resolve_query.assert_called_once_with("unknown title")
