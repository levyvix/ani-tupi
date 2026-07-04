"""Tests for manual anime title resolution and fallback search flow."""

from __future__ import annotations

from argparse import Namespace
from contextlib import nullcontext
from unittest.mock import Mock, patch

from models.models import AniListAnime, AniListTitle, AnimeTitleResolution, ScraperCacheData
from services.anime.search import (
    ContextualSearchResults,
    DualSearchResults,
    IncrementalSearchState,
    ManualSearchSelection,
    _ensure_anime_sources_in_repo,
    search_anime_flow,
)
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
    """The resolver should still use the best-matching provider result."""
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

    assert resolution == weak_result
    assert provider.calls == 1
    assert cache.data


@patch("services.anime.search.loading", side_effect=lambda *args, **kwargs: nullcontext())
@patch(
    "services.anime.search._resolve_search_query",
    return_value=AnimeTitleResolution(
        original_query="Dandadan",
        resolved_title="Dandadan Kanzenban",
        provider="jikan",
        confidence=94,
        aliases=("Dandadan Kanzenban", "Dandadan"),
    ),
)
@patch("services.anime.search.get_cache")
def test_search_anime_flow_cache_hit_prefers_original_query_before_jikan_resolution(
    mock_get_cache,
    mock_resolve_query,
    mock_loading,
):
    """Cache hits should use the original query first without forcing Jikan title replacement."""
    mock_get_cache.return_value = ScraperCacheData(
        episode_urls=["https://example.com/ep1"],
        episode_count=1,
        timestamp=0,
    )

    mock_rep = Mock()
    mock_rep.get_available_seasons.return_value = [1]
    mock_rep.get_episode_list.return_value = ["Episode 1"]

    with (
        patch("services.anime.search.rep", mock_rep),
        patch(
            "services.anime.search.run_dual_contextual_search",
            return_value=DualSearchResults(
                user_query="Dandadan",
                user_results=ContextualSearchResults(
                    state=make_state(["Dandadan [animefire]"], query="dandadan", word_count=1),
                    titles_with_sources=["Dandadan [animefire]"],
                    used_query="dandadan",
                ),
                official_query="Dandadan Kanzenban",
                official_results=ContextualSearchResults(
                    state=make_state([], query="dandadan", word_count=1),
                    titles_with_sources=[],
                    used_query="dandadan",
                ),
            ),
        ),
        patch(
            "services.anime.search._select_from_dual_search_results",
            return_value=ManualSearchSelection(
                selected_anime="Dandadan",
                source="animefire",
                was_cancelled=False,
            ),
        ),
    ):
        result = search_anime_flow(build_args("Dandadan"))

    assert result == ("Dandadan", 0, "animefire")
    mock_rep.search_episodes.assert_called_once_with("Dandadan")
    mock_resolve_query.assert_called_once_with("Dandadan")


@patch("services.anime.search.loading", side_effect=lambda *args, **kwargs: nullcontext())
@patch("services.anime.search.menu_navigate", return_value="Boku no Hero Academia [animefire]")
@patch(
    "services.anime.search._resolve_search_query",
    return_value=AnimeTitleResolution(
        original_query="my hero",
        resolved_title="Boku no Hero Academia",
        provider="jikan",
        confidence=91,
        aliases=("Boku no Hero Academia", "My Hero Academia"),
    ),
)
@patch("services.anime.search.get_cache", return_value=None)
@patch(
    "services.anime.search.run_dual_contextual_search",
    return_value=DualSearchResults(
        user_query="my hero",
        user_results=ContextualSearchResults(
            state=make_state(
                ["My Hero Academia: Vigilantes [animefire]"], query="my hero", word_count=2
            ),
            titles_with_sources=["My Hero Academia: Vigilantes [animefire]"],
            used_query="my hero",
        ),
        official_query="Boku no Hero Academia",
        official_results=ContextualSearchResults(
            state=make_state(["Boku no Hero Academia [animefire]"], query="boku no", word_count=2),
            titles_with_sources=["Boku no Hero Academia [animefire]"],
            used_query="boku no",
        ),
    ),
)
@patch(
    "services.anime.search._select_from_dual_search_results",
    return_value=ManualSearchSelection(
        selected_anime="Boku no Hero Academia",
        source="animefire",
        was_cancelled=False,
        search_query_used="boku no",
    ),
)
def test_search_anime_flow_retries_with_resolved_title(
    mock_dual_select,
    mock_run_dual,
    mock_get_cache,
    mock_resolve_query,
    mock_menu,
    mock_loading,
):
    """Manual search should present user and official-title results together when resolution exists."""

    mock_rep = Mock()
    mock_rep.get_available_seasons.return_value = [1]
    mock_rep.get_episode_list.return_value = ["Episode 1"]

    with patch("services.anime.search.rep", mock_rep):
        result = search_anime_flow(build_args("my hero"))

    assert result == ("Boku no Hero Academia", 0, "animefire")
    mock_resolve_query.assert_called_once_with("my hero")
    mock_run_dual.assert_called_once_with("my hero", "Boku no Hero Academia")


@patch("services.anime.search.loading", side_effect=lambda *args, **kwargs: nullcontext())
@patch(
    "services.anime.search._resolve_search_query",
    return_value=AnimeTitleResolution(
        original_query="angel next door",
        resolved_title="Otonari no Tenshi-sama",
        provider="jikan",
        confidence=90,
        aliases=("Otonari no Tenshi-sama", "The Angel Next Door Spoils Me Rotten"),
    ),
)
@patch("services.anime.search.get_cache", return_value=None)
@patch(
    "services.anime.search.run_dual_contextual_search",
    return_value=DualSearchResults(
        user_query="angel next door",
        user_results=ContextualSearchResults(
            state=make_state(["Angel Beats! [animefire]"], query="angel", word_count=1),
            titles_with_sources=["Angel Beats! [animefire]"],
            used_query="angel",
        ),
        official_query="Otonari no Tenshi-sama",
        official_results=ContextualSearchResults(
            state=make_state(
                ["Otonari no Tenshi-sama [animefire]"], query="otonari no", word_count=2
            ),
            titles_with_sources=["Otonari no Tenshi-sama [animefire]"],
            used_query="otonari no",
        ),
    ),
)
@patch(
    "services.anime.search._select_from_dual_search_results",
    return_value=ManualSearchSelection(
        selected_anime="Otonari no Tenshi-sama",
        source="animefire",
        was_cancelled=False,
        search_query_used="otonari no",
    ),
)
def test_search_anime_flow_retries_with_resolved_title_when_original_results_are_weak(
    mock_dual_select,
    mock_run_dual,
    mock_get_cache,
    mock_resolve_query,
    mock_loading,
):
    """Resolved title should be searched alongside the user query and shown in the same chooser."""
    mock_rep = Mock()
    mock_rep.get_available_seasons.return_value = [1]
    mock_rep.get_episode_list.return_value = ["Episode 1"]
    mock_rep.search_episodes.return_value = None

    with patch("services.anime.search.rep", mock_rep):
        result = search_anime_flow(build_args("angel next door"))

    assert result == ("Otonari no Tenshi-sama", 0, "animefire")
    mock_run_dual.assert_called_once_with("angel next door", "Otonari no Tenshi-sama")


@patch("services.anime.search.loading", side_effect=lambda *args, **kwargs: nullcontext())
@patch(
    "services.anime.search.menu_navigate",
    return_value="Otonari no Tenshi-sama Season 2 [animefire]",
)
@patch(
    "services.anime.search._resolve_search_query",
    return_value=AnimeTitleResolution(
        original_query="angel next door",
        resolved_title="Otonari no Tenshi-sama",
        provider="jikan",
        confidence=90,
        aliases=("Otonari no Tenshi-sama", "The Angel Next Door Spoils Me Rotten"),
    ),
)
@patch("services.anime.search.get_cache", return_value=None)
@patch(
    "services.anime.search.run_dual_contextual_search",
    return_value=DualSearchResults(
        user_query="angel next door",
        user_results=ContextualSearchResults(
            state=make_state(
                ["Angel Next Door [animefire]"], query="angel next door", word_count=3
            ),
            titles_with_sources=["Angel Next Door [animefire]"],
            used_query="angel next door",
        ),
        official_query="Otonari no Tenshi-sama",
        official_results=ContextualSearchResults(
            state=make_state(
                ["Otonari no Tenshi-sama Season 2 [animefire]"],
                query="otonari no",
                word_count=2,
            ),
            titles_with_sources=["Otonari no Tenshi-sama Season 2 [animefire]"],
            used_query="otonari no",
        ),
    ),
)
@patch(
    "services.anime.search._select_from_dual_search_results",
    return_value=ManualSearchSelection(
        selected_anime="Otonari no Tenshi-sama Season 2",
        source="animefire",
        was_cancelled=False,
        search_query_used="otonari no",
    ),
)
def test_search_anime_flow_retries_with_resolved_title_when_season_missing(
    mock_dual_select,
    mock_run_dual,
    mock_get_cache,
    mock_resolve_query,
    mock_menu,
    mock_loading,
):
    """Season filtering should not force Jikan resolution if scraper-first search already found a match."""
    mock_rep = Mock()
    mock_rep.get_available_seasons.return_value = [1, 2]
    mock_rep.get_episode_list.return_value = [f"Episode {i}" for i in range(1, 13)]
    mock_rep.search_episodes.return_value = None

    with patch("services.anime.search.rep", mock_rep):
        result = search_anime_flow(build_args("angel next door", episode=4, season=2))

    assert result == ("Otonari no Tenshi-sama Season 2", 3, "animefire")
    assert mock_resolve_query.call_count == 1
    mock_run_dual.assert_called_once_with("angel next door", "Otonari no Tenshi-sama")


@patch("services.anime.search.loading", side_effect=lambda *args, **kwargs: nullcontext())
@patch(
    "services.anime.search.menu_navigate",
    return_value="Otonari no Tenshi-sama Season 2 [animefire]",
)
@patch(
    "services.anime.search._resolve_search_query",
    return_value=AnimeTitleResolution(
        original_query="angel next door",
        resolved_title="Otonari no Tenshi-sama",
        provider="jikan",
        confidence=90,
        aliases=("Otonari no Tenshi-sama", "The Angel Next Door Spoils Me Rotten"),
    ),
)
@patch(
    "services.anime.search.get_cache",
    return_value=ScraperCacheData(
        episode_urls=["https://example.com/ep1"],
        episode_count=1,
        timestamp=0,
    ),
)
@patch(
    "services.anime.search.run_dual_contextual_search",
    return_value=DualSearchResults(
        user_query="angel next door",
        user_results=ContextualSearchResults(
            state=make_state(
                ["Angel Next Door [animefire]"], query="angel next door", word_count=3
            ),
            titles_with_sources=["Angel Next Door [animefire]"],
            used_query="angel next door",
        ),
        official_query="Otonari no Tenshi-sama",
        official_results=ContextualSearchResults(
            state=make_state(
                ["Otonari no Tenshi-sama Season 2 [animefire]"],
                query="otonari no",
                word_count=2,
            ),
            titles_with_sources=["Otonari no Tenshi-sama Season 2 [animefire]"],
            used_query="otonari no",
        ),
    ),
)
@patch(
    "services.anime.search._select_from_dual_search_results",
    return_value=ManualSearchSelection(
        selected_anime="Otonari no Tenshi-sama Season 2",
        source="animefire",
        was_cancelled=False,
        search_query_used="otonari no",
    ),
)
def test_search_anime_flow_cache_path_prefers_original_query_when_cached(
    mock_dual_select,
    mock_run_dual,
    mock_get_cache,
    mock_resolve_query,
    mock_menu,
    mock_loading,
):
    """Dual search should still allow selecting the official-title result when caches exist."""

    mock_rep = Mock()
    mock_rep.get_available_seasons.return_value = [1, 2]
    mock_rep.get_episode_list.return_value = [f"Episode {i}" for i in range(1, 13)]
    mock_rep.search_episodes.return_value = None

    with patch("services.anime.search.rep", mock_rep):
        result = search_anime_flow(build_args("angel next door", episode=4, season=2))

    assert result == ("Otonari no Tenshi-sama Season 2", 3, "animefire")
    assert mock_resolve_query.call_count == 1
    mock_run_dual.assert_called_once_with("angel next door", "Otonari no Tenshi-sama")


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


def test_ensure_anime_sources_in_repo_after_dual_search_worker():
    """Dual search menus must re-register sources in the main process."""
    from scrapers import loader

    loader.load_plugins()
    from services.repository import rep

    rep.clear_search_results()
    selected = "Koko wa Ore ni Makasete Saki ni Ike to Ittekara"
    assert selected not in rep.anime_to_urls

    assert _ensure_anime_sources_in_repo(
        selected,
        "Koko wa Ore ni Makasete Saki",
    )
    assert rep.anime_to_urls.get(selected)

    rep.search_episodes(selected)
    assert rep.get_episode_list(selected)
