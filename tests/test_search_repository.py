"""Tests for SearchRepository."""

from unittest.mock import Mock, patch
from services.search_repository import SearchRepository
from models.models import AnimeMetadata


class MockPlugin:
    """Mock scraper plugin for testing."""

    def __init__(self, name: str, results: list[AnimeMetadata] | None = None):
        self.name = name
        self.results = results or []

    def search_anime(self, query: str) -> None:
        """Mock search that adds results to SearchRepository."""
        repo = SearchRepository()
        for anime in self.results:
            repo.add_anime(anime.title, anime.url, self.name, {})


class TestSearchRepository:
    """Test SearchRepository functionality."""

    def setup_method(self):
        """Reset singleton before each test."""
        SearchRepository.reset_singleton()

    def teardown_method(self):
        """Clean up after each test."""
        SearchRepository.reset_singleton()

    def test_singleton_pattern(self):
        """SearchRepository should be a singleton."""
        repo1 = SearchRepository()
        repo2 = SearchRepository()
        assert repo1 is repo2

    def test_register_plugin(self):
        """Register plugin."""
        repo = SearchRepository()
        plugin = Mock()
        plugin.name = "animefire"
        repo.register(plugin)

        assert "animefire" in repo.get_active_sources()

    def test_get_active_sources_sorted(self):
        """Active sources should be sorted."""
        repo = SearchRepository()
        for name in ["zeta", "anime", "beta"]:
            plugin = Mock()
            plugin.name = name
            repo.register(plugin)

        sources = repo.get_active_sources()
        assert sources == ["anime", "beta", "zeta"]

    def test_add_anime_basic(self):
        """Add single anime."""
        repo = SearchRepository()
        repo.add_anime("Jujutsu Kaisen", "http://example.com", "animefire", {})

        assert "Jujutsu Kaisen" in repo.anime_to_urls
        assert len(repo.anime_to_urls["Jujutsu Kaisen"]) == 1

    def test_add_anime_params_default_dict(self):
        """add_anime should default params to empty dict."""
        repo = SearchRepository()
        repo.add_anime("Anime Title", "http://url.com", "source", None)

        _, _, params = repo.anime_to_urls["Anime Title"][0]
        assert params == {}

    def test_add_anime_deduplication_by_normalized_title(self):
        """Same anime with different title formats should be deduplicated."""
        repo = SearchRepository()

        # Add same anime with different separators
        repo.add_anime("Jujutsu Kaisen: Season 2", "http://url1.com", "source1", {})
        repo.add_anime("Jujutsu Kaisen - Season 2", "http://url2.com", "source2", {})

        # Should have only 1 title (first one added)
        assert len(repo.anime_to_urls) == 1

        # Should have both sources
        title = list(repo.anime_to_urls.keys())[0]
        assert len(repo.anime_to_urls[title]) == 2

    def test_add_anime_compact_key_fallback_merges_split_join_variation(self):
        """Compact fallback should merge split/join token variants safely."""
        repo = SearchRepository()

        repo.add_anime("aaa b b cc", "http://url1.com", "source1", {})
        repo.add_anime("aaa bb cc", "http://url2.com", "source2", {})

        assert len(repo.anime_to_urls) == 1
        title = list(repo.anime_to_urls.keys())[0]
        assert len(repo.anime_to_urls[title]) == 2

    def test_add_anime_compact_key_does_not_merge_incompatible_language(self):
        """Compact fallback should not merge dubbed and subtitled variants."""
        repo = SearchRepository()

        repo.add_anime("aaa b b cc dublado", "http://url1.com", "source1", {})
        repo.add_anime("aaa bb cc legendado", "http://url2.com", "source2", {})

        assert len(repo.anime_to_urls) == 2

    def test_add_anime_compact_key_does_not_merge_different_season_markers(self):
        """Compact fallback should not merge when detected season markers differ."""
        repo = SearchRepository()

        repo.add_anime("aaa b b cc season 2", "http://url1.com", "source1", {})
        repo.add_anime("aaa bb cc season 3", "http://url2.com", "source2", {})

        assert len(repo.anime_to_urls) == 2

    def test_add_anime_exact_match_behavior_unchanged(self):
        """Exact normalized equality should still merge without fallback."""
        repo = SearchRepository()

        repo.add_anime("Anime A: Title", "http://url1.com", "source1", {})
        repo.add_anime("Anime A - Title", "http://url2.com", "source2", {})

        assert len(repo.anime_to_urls) == 1
        title = list(repo.anime_to_urls.keys())[0]
        assert len(repo.anime_to_urls[title]) == 2

    def test_add_anime_multi_source_aggregation_unchanged(self):
        """Deduped title should still aggregate all source entries."""
        repo = SearchRepository()

        repo.add_anime("Anime A: Title", "http://url1.com", "source1", {})
        repo.add_anime("Anime A - Title", "http://url2.com", "source2", {})
        repo.add_anime("Anime A | Title", "http://url3.com", "source3", {})

        assert len(repo.anime_to_urls) == 1
        title = list(repo.anime_to_urls.keys())[0]
        aggregated_sources = {source for _, source, _ in repo.anime_to_urls[title]}
        assert aggregated_sources == {"source1", "source2", "source3"}

    def test_clear_search_results(self):
        """clear_search_results should clear data but keep sources."""
        repo = SearchRepository()
        plugin = Mock()
        plugin.name = "animefire"
        repo.register(plugin)

        repo.add_anime("Anime 1", "http://url.com", "animefire", {})
        repo.clear_search_results()

        assert len(repo.anime_to_urls) == 0
        assert "animefire" in repo.get_active_sources()

    def test_get_anime_titles(self):
        """Get all anime titles."""
        repo = SearchRepository()
        repo.add_anime("Anime A", "http://url1.com", "source1", {})
        repo.add_anime("Anime B", "http://url2.com", "source2", {})
        repo.add_anime("Anime C", "http://url3.com", "source3", {})

        titles = repo.get_anime_titles()
        assert sorted(titles) == ["Anime A", "Anime B", "Anime C"]

    def test_get_anime_titles_filtered(self):
        """Get anime titles filtered by query."""
        repo = SearchRepository()
        repo.add_anime("Jujutsu Kaisen", "http://url1.com", "source1", {})
        repo.add_anime("Jujutsu Kaisen 2", "http://url2.com", "source2", {})
        repo.add_anime("Dan Da Dan", "http://url3.com", "source3", {})

        filtered = repo.get_anime_titles(filter_by_query="Jujutsu")
        assert "Jujutsu Kaisen" in filtered
        assert "Jujutsu Kaisen 2" in filtered
        assert "Dan Da Dan" not in filtered

    def test_get_anime_titles_with_sources(self):
        """Get anime titles with source indicators."""
        repo = SearchRepository()
        repo.add_anime("Jujutsu Kaisen", "http://url1.com", "animefire", {})
        repo.add_anime("Jujutsu Kaisen", "http://url2.com", "dattebayo", {})

        titles = repo.get_anime_titles_with_sources()
        # Should contain one entry with both sources
        assert len(titles) == 1
        assert "[animefire, dattebayo]" in titles[0] or "[dattebayo, animefire]" in titles[0]

    def test_normalize_for_filter(self):
        """Normalize text for filtering."""
        repo = SearchRepository()

        # Should remove punctuation and normalize case
        result = repo._normalize_for_filter("Jujutsu--Kaisen: Season 2!")
        assert result == "jujutsu kaisen season 2"

    def test_build_search_results(self):
        """Build immutable SearchResults."""
        repo = SearchRepository()
        repo.add_anime("Anime A", "http://url1.com", "source1", {"key": "value"})

        results = repo._build_search_results("query")

        assert results.query == "query"
        assert len(results.results) == 1
        assert results.results[0].title == "Anime A"

    @patch("services.search_repository.logger")
    def test_search_anime_no_plugins(self, mock_logger):
        """search_anime should log error when no plugins registered."""
        repo = SearchRepository()
        results = repo.search_anime("test", verbose=False)

        assert len(results.results) == 0

    @patch("services.search_repository.logger")
    def test_search_anime_with_word_limit(self, mock_logger):
        """search_anime_with_word_limit should limit words in search."""
        repo = SearchRepository()

        # Add mock plugin
        plugin = Mock()
        plugin.name = "test_source"
        plugin.search_anime = Mock()
        repo.register(plugin)

        # Test with 2 word limit on 3 word query
        results = repo.search_anime_with_word_limit("One Two Three", word_limit=2, verbose=False)

        assert results.query == "One Two Three"
        metadata = repo.get_search_metadata()
        assert metadata.used_query == "One Two"
        assert metadata.used_words == 2

    def test_get_search_metadata_empty(self):
        """get_search_metadata returns empty when no search performed."""
        repo = SearchRepository()
        metadata = repo.get_search_metadata()

        assert metadata.original_query is None
        assert metadata.used_query is None

    def test_reset_singleton(self):
        """reset_singleton should clear instance."""
        repo1 = SearchRepository()
        repo1.add_anime("Test", "http://url.com", "source", {})

        SearchRepository.reset_singleton()
        repo2 = SearchRepository()

        assert len(repo2.anime_to_urls) == 0
        assert repo1 is not repo2
