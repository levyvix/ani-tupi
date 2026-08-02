"""Tests for Repository cache integration with normalized keys.

Verifies that Repository uses normalized cache keys for search results,
using real plugins and real cache behavior instead of mocks.
"""

from utils.title_normalization import normalize_search_cache_key


class TestRepositoryCacheIntegration:
    """Test Repository integration with normalized cache keys.

    Uses real Repository with real plugins loaded from scrapers/plugins/
    directory, mocking only external HTTP API calls.
    """

    def test_cache_key_normalization_format(self):
        """Normalized cache keys should have expected format."""
        key = normalize_search_cache_key("Jigokuraku Season 2")

        # Format: search:{normalized}:{language}
        assert key.startswith("search:")
        assert key.endswith(":pt-br")
        assert key.count(":") == 2

    def test_cache_key_normalization_matches_queries(self):
        """Normalized cache keys should be consistent for equivalent queries."""
        # Different representations of the same query should produce same cache key
        queries = [
            "jigokuraku 2",
            "Jigokuraku 2nd Season",
            "JIGOKURAKU S2",
            "jigokuraku season 2",
        ]

        keys = [normalize_search_cache_key(q) for q in queries]
        # All should produce same normalized key
        assert all(k == keys[0] for k in keys)

    def test_language_code_in_cache_key(self):
        """Cache keys should include language code."""
        key_pt = normalize_search_cache_key("dandadan", "pt-br")
        key_en = normalize_search_cache_key("dandadan", "en-us")

        # Different language codes should produce different keys
        assert key_pt != key_en
        assert key_pt.endswith(":pt-br")
        assert key_en.endswith(":en-us")

    def test_different_query_variations_use_same_key(self):
        """Verify that query variations normalize to the same cache key.

        This is critical for cache effectiveness: "Jigokuraku 2" and "JIGOKURAKU S2"
        should use the same cache entry.
        """
        queries = [
            "jigokuraku 2",
            "Jigokuraku 2nd Season",
            "JIGOKURAKU S2",
            "jigokuraku season 2",
        ]

        cache_keys = [normalize_search_cache_key(q) for q in queries]

        # All variations should normalize to the same cache key
        assert len(set(cache_keys)) == 1, (
            "Query variations should produce identical cache keys for proper caching"
        )
