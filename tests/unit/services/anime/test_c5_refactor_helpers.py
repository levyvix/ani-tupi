"""Tests for the C5 decomposition helpers.

Covers:
- The explicit awaiting-episode registry that replaced the hidden
  function-attribute state formerly stored on ``anilist_anime_flow``, and its
  consumption by ``playback_service.get_episode_url_and_source``.
- The single cache-check helper (``_try_cache_hit``) used by ``search_anime_flow``.
- Decomposed incremental-search helpers (``_count_sources``, ``_perform_scraper_search``).
- The repository routing for ``search_homepage_incremental`` (no direct plugin import).

Only external boundaries (repository / cache / AniList discovery) are mocked;
the helpers themselves run for real.
"""

from unittest.mock import Mock, patch

from services.anime.awaiting_episodes import AwaitingEpisodeRegistry


# ---------------------------------------------------------------------------
# Awaiting-episode registry (replaces the former hidden function-attribute state)
# ---------------------------------------------------------------------------


class TestAwaitingEpisodeRegistry:
    def test_set_and_get_roundtrip(self):
        registry = AwaitingEpisodeRegistry()
        registry.set("Dandadan", 13, "https://ad.example/ep13")

        assert registry.get("Dandadan", 13) == "https://ad.example/ep13"

    def test_get_missing_returns_none(self):
        registry = AwaitingEpisodeRegistry()
        assert registry.get("Unknown", 1) is None
        registry.set("Dandadan", 13, "https://ad.example/ep13")
        assert registry.get("Dandadan", 99) is None

    def test_clear_drops_only_that_anime(self):
        registry = AwaitingEpisodeRegistry()
        registry.set("A", 2, "urlA")
        registry.set("B", 3, "urlB")

        registry.clear("A")

        assert registry.get("A", 2) is None
        assert registry.get("B", 3) == "urlB"

    def test_module_level_singleton_exists(self):
        from services.anime import awaiting_episodes

        assert isinstance(awaiting_episodes.registry, AwaitingEpisodeRegistry)


class TestGetEpisodeUrlUsesAwaitingRegistry:
    """The playback layer must read the explicit registry, not function state."""

    @patch("services.anime.playback_service.rep")
    def test_awaiting_url_extracts_via_repository(self, mock_rep):
        from services.anime.awaiting_episodes import registry
        from services.anime.playback_service import get_episode_url_and_source

        registry.clear("Dandadan")
        registry.set("Dandadan", 13, "https://ad.example/video/ep13")
        try:
            mock_rep.search_player_from_page.return_value = ["https://cdn.example/ep13.mp4"]

            result = get_episode_url_and_source("Dandadan", 13)

            assert result.success is True
            assert result.player_url == "https://cdn.example/ep13.mp4"
            assert result.source == "animesdigital"
            # Routed through the repository, not a direct plugin import.
            mock_rep.search_player_from_page.assert_called_once_with(
                "https://ad.example/video/ep13", "animesdigital"
            )
        finally:
            registry.clear("Dandadan")

    @patch("services.anime.playback_service.rep")
    def test_no_awaiting_url_falls_back_to_regular_search(self, mock_rep):
        from services.anime.awaiting_episodes import registry
        from services.anime.playback_service import get_episode_url_and_source

        registry.clear("Dandadan")
        mock_rep.search_player.return_value = "https://cdn.example/regular.mp4"
        mock_rep.get_episode_url_and_source.return_value = (
            "https://page.example/ep5",
            "animefire",
        )

        result = get_episode_url_and_source("Dandadan", 5)

        assert result.success is True
        assert result.source == "animefire"
        mock_rep.search_player_from_page.assert_not_called()


# ---------------------------------------------------------------------------
# search_anime_flow single cache-check helper (_try_cache_hit)
# ---------------------------------------------------------------------------


class TestTryCacheHit:
    def test_returns_true_and_populates_repo_on_cache_hit(self):
        from services.anime import search

        cache_data = Mock(episode_count=12)
        mock_rep = Mock()

        with (
            patch.object(search, "get_cache", return_value=cache_data),
            patch.object(search, "rep", mock_rep),
        ):
            hit = search._try_cache_hit("dandadan")

        assert hit is True
        mock_rep.load_from_cache.assert_called_once_with("dandadan", cache_data)
        mock_rep.search_anime.assert_called_once_with("dandadan", verbose=False)

    def test_returns_false_and_touches_nothing_on_miss(self):
        from services.anime import search

        mock_rep = Mock()

        with (
            patch.object(search, "get_cache", return_value=None),
            patch.object(search, "rep", mock_rep),
        ):
            hit = search._try_cache_hit("unknown anime")

        assert hit is False
        mock_rep.load_from_cache.assert_not_called()
        mock_rep.search_anime.assert_not_called()


# ---------------------------------------------------------------------------
# Decomposed incremental-search helpers
# ---------------------------------------------------------------------------


class TestCountSources:
    def test_counts_sources_from_display_format(self):
        from services.anime.search import _count_sources

        counts = _count_sources(
            [
                "Naruto [animefire]",
                "Naruto Shippuden [animefire]",
                "Naruto [animesdigital]",
            ]
        )

        assert counts == {"animefire": 2, "animesdigital": 1}

    def test_ignores_entries_without_source(self):
        from services.anime.search import _count_sources

        assert _count_sources(["Plain Title"]) == {}


class TestPerformScraperSearch:
    def test_clears_searches_and_ranks(self):
        from services.anime import search

        mock_rep = Mock()
        mock_rep.get_search_metadata.return_value = Mock(used_query="naruto")
        mock_rep.get_anime_titles_with_sources.return_value = ["Naruto [animefire]"]

        with (
            patch.object(search, "rep", mock_rep),
            patch(
                "utils.anilist_discovery.auto_discover_anilist_id",
                return_value=None,
            ),
        ):
            outcome = search._perform_scraper_search("naruto")

        mock_rep.clear_search_results.assert_called_once()
        mock_rep.search_anime.assert_called_once_with("naruto", verbose=True)
        assert outcome.used_query == "naruto"
        assert outcome.titles_with_sources == ["Naruto [animefire]"]
        assert outcome.anilist_reference_title is None

    def test_uses_anilist_title_as_reference(self):
        from services.anime import search

        mock_rep = Mock()
        mock_rep.get_search_metadata.return_value = Mock(used_query="naruto")
        mock_rep.get_anime_titles_with_sources.return_value = ["Naruto [animefire]"]

        anilist_match = Mock(title="Naruto Shippuuden")

        with (
            patch.object(search, "rep", mock_rep),
            patch(
                "utils.anilist_discovery.auto_discover_anilist_id",
                return_value=[anilist_match],
            ),
        ):
            outcome = search._perform_scraper_search("naruto")

        assert outcome.anilist_reference_title == "Naruto Shippuuden"


# ---------------------------------------------------------------------------
# Repository routing for homepage incremental search (no direct plugin import)
# ---------------------------------------------------------------------------


class TestRepositorySearchHomepageIncremental:
    def test_routes_to_registered_plugin(self, repository):
        plugin = Mock()
        plugin.name = "animesdigital"
        plugin.search_homepage_incremental.return_value = [
            {"episode_number": 13, "episode_url": "https://ad.example/ep13"}
        ]

        repository.register(plugin)

        results = repository.search_homepage_incremental("animesdigital", "Dandadan")

        assert results == [{"episode_number": 13, "episode_url": "https://ad.example/ep13"}]
        plugin.search_homepage_incremental.assert_called_once_with("Dandadan")

    def test_unknown_source_returns_empty(self, repository):
        assert repository.search_homepage_incremental("nope", "Dandadan") == []
