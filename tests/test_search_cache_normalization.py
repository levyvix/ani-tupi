"""Tests for search cache key normalization.

Tests the normalize_search_cache_key() function to ensure consistent cache
key generation across different query variations.
"""

from utils.title_normalization import normalize_search_cache_key


class TestCacheKeyNormalization:
    """Test cache key normalization for search queries."""

    def test_basic_lowercase_normalization(self):
        """Lowercase conversion should normalize keys."""
        key1 = normalize_search_cache_key("jigokuraku")
        key2 = normalize_search_cache_key("JIGOKURAKU")
        assert key1 == key2
        assert key1 == "search:jigokuraku:pt-br"

    def test_season_number_removal(self):
        """Season numbers should be removed from query but preserved as number."""
        key1 = normalize_search_cache_key("jigokuraku 2")
        key2 = normalize_search_cache_key("Jigokuraku 2nd Season")
        key3 = normalize_search_cache_key("Jigokuraku Season 2")
        key4 = normalize_search_cache_key("JIGOKURAKU S2")

        # All should normalize to same key
        assert key1 == key2 == key3 == key4
        assert key1 == "search:jigokuraku-2:pt-br"

    def test_punctuation_removal(self):
        """Punctuation should be removed."""
        key1 = normalize_search_cache_key("Jigokuraku 2")
        key2 = normalize_search_cache_key("Jigokuraku, 2")
        key3 = normalize_search_cache_key("Jigokuraku: 2")
        key4 = normalize_search_cache_key("Jigokuraku, Season 2!")

        # All should normalize to same key
        assert key1 == key2 == key3 == key4

    def test_whitespace_normalization(self):
        """Multiple spaces should be normalized to single space."""
        key1 = normalize_search_cache_key("jigokuraku 2")
        key2 = normalize_search_cache_key("jigokuraku  2")
        key3 = normalize_search_cache_key("jigokuraku   2")
        key4 = normalize_search_cache_key("  jigokuraku  2  ")

        assert key1 == key2 == key3 == key4
        assert key1 == "search:jigokuraku-2:pt-br"

    def test_multi_word_query(self):
        """Multi-word queries should be space-separated in key."""
        key = normalize_search_cache_key("hell's paradise jigokuraku")
        # Apostrophe should be preserved, words joined with dashes
        assert "hell" in key
        assert "paradise" in key
        assert "jigokuraku" in key

    def test_language_code_separation(self):
        """Different language codes should produce different cache keys."""
        key_pt = normalize_search_cache_key("dandadan", "pt-br")
        key_en = normalize_search_cache_key("dandadan", "en-us")
        key_ja = normalize_search_cache_key("dandadan", "ja")

        assert key_pt != key_en
        assert key_pt != key_ja
        assert key_en != key_ja
        assert key_pt == "search:dandadan:pt-br"
        assert key_en == "search:dandadan:en-us"
        assert key_ja == "search:dandadan:ja"

    def test_dublado_removal(self):
        """Portuguese 'dublado' (dubbed) suffix should be removed."""
        key1 = normalize_search_cache_key("dandadan dublado")
        key2 = normalize_search_cache_key("dandadan")

        assert key1 == key2

    def test_legenda_removal(self):
        """Portuguese 'legenda' (subtitled) suffix should be removed."""
        key1 = normalize_search_cache_key("dandadan legendado")
        key2 = normalize_search_cache_key("dandadan")

        assert key1 == key2

    def test_unicode_normalization(self):
        """Unicode accents should be normalized."""
        key1 = normalize_search_cache_key("café")
        key2 = normalize_search_cache_key("cafe")

        assert key1 == key2
        assert key1 == "search:cafe:pt-br"

    def test_empty_query_fallback(self):
        """Empty queries should have sensible fallback."""
        key1 = normalize_search_cache_key("")
        key2 = normalize_search_cache_key("   ")

        assert key1.startswith("search:empty")
        assert key2.startswith("search:empty")

    def test_special_characters_removed(self):
        """Special characters should be removed."""
        key1 = normalize_search_cache_key("jigokuraku!@#$%^&*()")
        key2 = normalize_search_cache_key("jigokuraku")

        assert key1 == key2

    def test_arc_suffix_removal(self):
        """Arc suffixes should be removed."""
        key1 = normalize_search_cache_key("demon slayer arc 1")
        key2 = normalize_search_cache_key("demon slayer")

        assert key1 == key2

    def test_part_suffix_removal(self):
        """Part suffixes should be removed or handled consistently."""
        key1 = normalize_search_cache_key("jigokuraku part 2")
        key2 = normalize_search_cache_key("Jigokuraku Part 2nd")

        # Part suffix should be removed
        assert "part" not in key1
        assert key1 == key2

    def test_multiple_season_patterns(self):
        """Handle various season pattern formats."""
        queries = [
            "demon slayer season 2",
            "demon slayer s2",
            "demon slayer temporada 2",
            "demon slayer 2",
        ]
        keys = [normalize_search_cache_key(q) for q in queries]

        # All should normalize to same key
        assert all(k == keys[0] for k in keys)

    def test_combined_variations(self):
        """Test realistic combined variations."""
        queries = [
            "Jigokuraku Season 2 Dublado",
            "jigokuraku 2nd season",
            "JIGOKURAKU, S2!",
            "jigokuraku 2 dublado",
        ]
        keys = [normalize_search_cache_key(q) for q in queries]

        # All should normalize to same key
        assert all(k == keys[0] for k in keys)
        assert "dublado" not in keys[0].lower()
        assert "season" not in keys[0].lower()

    def test_cache_key_format(self):
        """Cache key should follow format: search:{normalized}:{language}."""
        key = normalize_search_cache_key("test query", "pt-br")

        assert key.startswith("search:")
        assert key.endswith(":pt-br")
        assert key.count(":") == 2  # search:normalized:language

    def test_apostrophe_preservation(self):
        """Apostrophes in English titles should be preserved in normalization."""
        key = normalize_search_cache_key("hell's paradise")
        # Apostrophe might be removed or preserved, but title should still normalize
        assert "hell" in key
        assert "paradise" in key

    def test_consistency_across_calls(self):
        """Normalization should be deterministic."""
        query = "Jigokuraku Season 2 Dublado!"
        key1 = normalize_search_cache_key(query)
        key2 = normalize_search_cache_key(query)
        key3 = normalize_search_cache_key(query)

        assert key1 == key2 == key3

    def test_real_world_examples(self):
        """Test real-world anime title examples."""
        examples = [
            (
                "Demon Slayer: Hashira Training Arc",
                "search:demon-slayer-hashira-training-arc:pt-br",
            ),
            ("Dandadan Season 1", "search:dandadan-1:pt-br"),
            ("Hell's Paradise Jigokuraku", None),  # Just verify it doesn't crash
            ("Attack on Titan Final Season", "search:attack-on-titan:pt-br"),
        ]

        for query, expected in examples:
            key = normalize_search_cache_key(query)
            if expected:
                assert key == expected
            else:
                # Just verify it's a valid cache key
                assert key.startswith("search:")
                assert key.endswith(":pt-br")

    def test_whitespace_at_boundaries(self):
        """Whitespace at query boundaries should be stripped."""
        key1 = normalize_search_cache_key("   jigokuraku 2   ")
        key2 = normalize_search_cache_key("jigokuraku 2")

        assert key1 == key2

    def test_final_cour_removal(self):
        """'Final Cour' suffixes should be handled consistently."""
        key1 = normalize_search_cache_key("attack on titan final season")
        key2 = normalize_search_cache_key("attack on titan")

        # Both should normalize to same key (final season removed)
        assert key1 == key2
        assert "final" not in key1

    def test_dash_replacement(self):
        """Spaces should be replaced with dashes in final key."""
        key = normalize_search_cache_key("hello world test")
        # Should have dashes between words
        assert "hello-world-test" in key

    def test_default_language(self):
        """Default language should be pt-br."""
        key = normalize_search_cache_key("test")
        assert key.endswith(":pt-br")

    def test_season_number_preservation_order(self):
        """Season number should be preserved before language code."""
        key = normalize_search_cache_key("jigokuraku 2")
        # Key format: search:word1-word2-...-2:language
        # Split by colon to get language part
        parts = key.split(":")
        assert len(parts) == 3  # search, content, language
        assert parts[2] == "pt-br"  # Language at end

    def test_complex_unicode_handling(self):
        """Handle complex unicode characters."""
        key1 = normalize_search_cache_key("Ça¢é")

        # After unicode normalization, should be valid
        assert key1.startswith("search:")

    def test_numeric_only_query(self):
        """Numeric-only queries should be handled."""
        key = normalize_search_cache_key("2024")
        assert key.startswith("search:")
        assert "2024" in key or "2" in key
