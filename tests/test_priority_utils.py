"""Tests for priority_utils.sort_by_priority function."""

from services.repository.priority_utils import sort_by_priority


class TestSortByPriority:
    """Test priority-based sorting."""

    def test_single_source(self):
        """Test sorting with single source."""
        items = [("url1", "dub")]
        priority = ["dub", "sub"]
        result = sort_by_priority(items, priority, source_index=1)
        assert result == [("url1", "dub")]

    def test_multiple_sources_respects_priority(self):
        """Test sorting respects priority order."""
        items = [("url1", "dub"), ("url2", "sub"), ("url3", "dub")]
        priority = ["sub", "dub"]
        result = sort_by_priority(items, priority, source_index=1)
        # Sub should come first (higher priority)
        assert result[0] == ("url2", "sub")
        assert result[1] in [("url1", "dub"), ("url3", "dub")]
        assert result[2] in [("url1", "dub"), ("url3", "dub")]

    def test_missing_source_fallback(self):
        """Test items with missing source are placed at end."""
        items = [("url1", "dub"), ("url2", "unknown"), ("url3", "sub")]
        priority = ["sub", "dub"]
        result = sort_by_priority(items, priority, source_index=1)
        # Unknown source should be last
        assert result[-1] == ("url2", "unknown")
        assert result[0] == ("url3", "sub")
        assert result[1] == ("url1", "dub")

    def test_empty_list(self):
        """Test with empty list."""
        result = sort_by_priority([], ["sub", "dub"])
        assert result == []

    def test_empty_priority_order(self):
        """Test with empty priority order - all items sorted equally."""
        items = [("url1", "dub"), ("url2", "sub"), ("url3", "unknown")]
        result = sort_by_priority(items, [])
        # All sources are equally "unknown" with index == len([]) = 0
        assert len(result) == 3
        assert set(result) == set(items)

    def test_none_values_in_items(self):
        """Test handling of None values."""
        items = [("url1", "dub"), ("url2", None), ("url3", "sub")]
        priority = ["sub", "dub"]
        result = sort_by_priority(items, priority, source_index=1)
        # None should be treated as unknown, placed at end
        assert result[-1] == ("url2", None)

    def test_custom_source_index(self):
        """Test with custom source index."""
        items = [("dub", "url1"), ("sub", "url2"), ("dub", "url3")]
        priority = ["sub", "dub"]
        result = sort_by_priority(items, priority, source_index=0)
        # Source is at index 0
        assert result[0] == ("sub", "url2")

    def test_preserves_order_for_equal_priority(self):
        """Test that stable sort preserves input order for equal priority."""
        items = [("url1", "dub"), ("url2", "dub"), ("url3", "dub")]
        priority = ["dub", "sub"]
        result = sort_by_priority(items, priority, source_index=1)
        # All have same priority, order should be preserved
        assert result == items

    def test_real_world_episode_selection(self):
        """Test real-world scenario: select from multiple sources."""
        available_sources = [
            ("episode1_dub_link", "animefire"),
            ("episode1_sub_link", "sushianimes"),
            ("episode1_unknown_link", "unknown_source"),
        ]
        priority_order = ["sushianimes", "animefire", "anitube"]

        sorted_sources = sort_by_priority(available_sources, priority_order, source_index=1)

        # sushianimes (sub) should be first (highest priority)
        assert sorted_sources[0] == ("episode1_sub_link", "sushianimes")
        assert sorted_sources[1] == ("episode1_dub_link", "animefire")
        assert sorted_sources[2] == ("episode1_unknown_link", "unknown_source")

    def test_all_sources_missing_from_priority(self):
        """Test when all sources are not in priority list."""
        items = [("url1", "unknown1"), ("url2", "unknown2")]
        priority = ["sub", "dub"]
        result = sort_by_priority(items, priority, source_index=1)
        # Order should be stable (input order)
        assert len(result) == 2
        assert set(result) == set(items)
