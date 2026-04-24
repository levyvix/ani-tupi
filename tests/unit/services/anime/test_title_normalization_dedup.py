"""Unit tests for normalize_title_for_dedup() function.

Tests the display normalization algorithm designed to normalize separators
and formatting while PRESERVING all meaningful content (language markers, seasons, etc).

Purpose: Normalize anime display by:
1. Converting to lowercase
2. Normalizing separators (: - | / \\ → space)
3. Removing accents
4. Keeping only letters, numbers, spaces, apostrophes

PRESERVES (does NOT remove):
- Language markers: Dublado, Legendado, Sub, Dub
- Season information: Season 2, 2nd Season, Temporada 2
- All meaningful content words
"""

from services.anime.title_normalization import (
    are_language_version_markers_compatible,
    are_season_markers_compatible,
    get_compact_normalized_title_key,
    normalize_title_for_dedup,
)


class TestSeparatorNormalization:
    """Test that all separator types are normalized to spaces."""

    def test_colon_separator(self):
        """Colon is normalized to space."""
        assert normalize_title_for_dedup("Anime A: Title") == "anime a title"

    def test_dash_separator(self):
        """Hyphen dash is normalized to space."""
        assert normalize_title_for_dedup("Anime A - Title") == "anime a title"

    def test_en_dash_separator(self):
        """En-dash is normalized to space."""
        assert normalize_title_for_dedup("Anime A – Title") == "anime a title"

    def test_em_dash_separator(self):
        """Em-dash is normalized to space."""
        assert normalize_title_for_dedup("Anime A — Title") == "anime a title"

    def test_pipe_separator(self):
        """Pipe is normalized to space."""
        assert normalize_title_for_dedup("Anime A | Title") == "anime a title"

    def test_forward_slash_separator(self):
        """Forward slash is normalized to space."""
        assert normalize_title_for_dedup("Anime A / Title") == "anime a title"

    def test_backslash_separator(self):
        """Backslash is normalized to space."""
        assert normalize_title_for_dedup("Anime A \\ Title") == "anime a title"

    def test_multiple_different_separators(self):
        """Multiple different separators all normalize to the same result."""
        result1 = normalize_title_for_dedup("Anime A: Title")
        result2 = normalize_title_for_dedup("Anime A - Title")
        result3 = normalize_title_for_dedup("Anime A | Title")
        result4 = normalize_title_for_dedup("Anime A / Title")

        assert result1 == result2 == result3 == result4
        assert result1 == "anime a title"

    def test_mixed_separators(self):
        """Mixed separators normalize to same result."""
        result1 = normalize_title_for_dedup("Anime A: Title - Dublado")
        result2 = normalize_title_for_dedup("Anime A | Title / Dublado")
        assert result1 == result2 == "anime a title dublado"


class TestLanguageMarkerPreservation:
    """Test that language markers (Dublado, Legendado, etc) are PRESERVED."""

    def test_preserve_dublado(self):
        """Dublado is preserved (not removed)."""
        result = normalize_title_for_dedup("Anime A Dublado")
        assert "dublado" in result
        assert result == "anime a dublado"

    def test_preserve_legendado(self):
        """Legendado is preserved (not removed)."""
        result = normalize_title_for_dedup("Anime A Legendado")
        assert "legendado" in result
        assert result == "anime a legendado"

    def test_preserve_legendadas(self):
        """Legendadas is preserved (not removed)."""
        result = normalize_title_for_dedup("Anime A Legendadas")
        assert "legendadas" in result
        assert result == "anime a legendadas"

    def test_preserve_longas(self):
        """Longas is preserved (not removed)."""
        result = normalize_title_for_dedup("Anime A Longas")
        assert "longas" in result
        assert result == "anime a longas"

    def test_preserve_sub(self):
        """Sub is preserved (not removed)."""
        result = normalize_title_for_dedup("Anime A Sub")
        assert "sub" in result
        assert result == "anime a sub"

    def test_preserve_subtitles(self):
        """Subtitles is preserved (not removed)."""
        result = normalize_title_for_dedup("Anime A Subtitles")
        assert "subtitles" in result
        assert result == "anime a subtitles"

    def test_preserve_dub(self):
        """Dub is preserved (not removed)."""
        result = normalize_title_for_dedup("Anime A Dub")
        assert "dub" in result
        assert result == "anime a dub"

    def test_preserve_dubbed(self):
        """Dubbed is preserved (not removed)."""
        result = normalize_title_for_dedup("Anime A Dubbed")
        assert "dubbed" in result
        assert result == "anime a dubbed"

    def test_language_marker_case_insensitive(self):
        """Language markers normalized to lowercase."""
        result1 = normalize_title_for_dedup("Anime A DUBLADO")
        result2 = normalize_title_for_dedup("Anime A dublado")
        result3 = normalize_title_for_dedup("Anime A Dublado")
        assert result1 == result2 == result3 == "anime a dublado"

    def test_language_markers_with_separators(self):
        """Language markers preserved even with separators."""
        result1 = normalize_title_for_dedup("Anime A: Dublado")
        result2 = normalize_title_for_dedup("Anime A - Dublado")
        assert result1 == result2 == "anime a dublado"


class TestSeasonPreservation:
    """Test that season information is PRESERVED."""

    def test_season_keyword_with_number(self):
        """Season keyword and number are preserved."""
        result = normalize_title_for_dedup("Anime Season 2")
        assert "season" in result
        assert "2" in result
        assert result == "anime season 2"

    def test_season_ordinal_format(self):
        """Season ordinal format preserved."""
        result = normalize_title_for_dedup("Anime 2nd Season")
        assert "2nd" in result
        assert "season" in result
        assert result == "anime 2nd season"

    def test_season_temporal_format(self):
        """Temporada format preserved."""
        result = normalize_title_for_dedup("Anime Temporada 2")
        assert "temporada" in result
        assert "2" in result
        assert result == "anime temporada 2"

    def test_season_short_format(self):
        """Season short format preserved."""
        result = normalize_title_for_dedup("Anime S2")
        assert result == "anime s2"

    def test_season_variations_all_preserved(self):
        """All season format variations are kept (not normalized to same)."""
        result1 = normalize_title_for_dedup("Anime Season 2")
        result2 = normalize_title_for_dedup("Anime 2nd Season")
        result3 = normalize_title_for_dedup("Anime Temporada 2")
        # They're all different formats, all should be preserved as-is
        assert "season" in result1
        assert "2nd" in result2
        assert "temporada" in result3

    def test_season_with_language_marker(self):
        """Season and language markers both preserved."""
        result = normalize_title_for_dedup("Anime Season 2 Dublado")
        assert "season" in result
        assert "2" in result
        assert "dublado" in result
        assert result == "anime season 2 dublado"

    def test_part_format_preserved(self):
        """Part format is preserved (not removed)."""
        result = normalize_title_for_dedup("Anime Part 2")
        assert "part" in result
        assert result == "anime part 2"

    def test_part_ordinal_preserved(self):
        """Part ordinal format preserved."""
        result = normalize_title_for_dedup("Anime Part 2nd")
        assert "part" in result
        assert result == "anime part 2nd"

    def test_cour_format_preserved(self):
        """Cour format preserved."""
        result = normalize_title_for_dedup("Anime Cour 2")
        assert "cour" in result
        assert result == "anime cour 2"

    def test_arc_format_preserved(self):
        """Arc format preserved."""
        result = normalize_title_for_dedup("Anime Arc Name Here")
        assert "arc" in result
        assert result == "anime arc name here"


class TestUnicodeHandling:
    """Test that unicode characters (accents) are normalized."""

    def test_acute_accent_removed(self):
        """Acute accent normalized."""
        assert normalize_title_for_dedup("Café") == "cafe"

    def test_grave_accent_removed(self):
        """Grave accent normalized."""
        assert normalize_title_for_dedup("Grave") == "grave"

    def test_circumflex_removed(self):
        """Circumflex normalized."""
        assert normalize_title_for_dedup("Têrça") == "terca"

    def test_tilde_removed(self):
        """Tilde normalized."""
        assert normalize_title_for_dedup("Ação") == "acao"

    def test_cedilla_removed(self):
        """Cedilla normalized."""
        assert normalize_title_for_dedup("Açúcar") == "acucar"

    def test_diaeresis_removed(self):
        """Diaeresis normalized."""
        assert normalize_title_for_dedup("Düsseldorf") == "dusseldorf"

    def test_full_title_with_accents(self):
        """Full title with accents normalized."""
        result = normalize_title_for_dedup("Café Terça Temporada 2")
        assert result == "cafe terca temporada 2"


class TestApostropheHandling:
    """Test that apostrophes in English titles are preserved."""

    def test_apostrophe_preserved(self):
        """Apostrophe in title is preserved."""
        result = normalize_title_for_dedup("Hell's Paradise")
        assert "'" in result
        assert result == "hell's paradise"

    def test_apostrophe_in_middle(self):
        """Apostrophe in middle of words preserved."""
        result = normalize_title_for_dedup("Don't Look Up")
        assert "'" in result
        assert result == "don't look up"

    def test_apostrophe_with_separators(self):
        """Apostrophe preserved even with separators."""
        result = normalize_title_for_dedup("Hell's Paradise: Jigokuraku")
        assert "'" in result
        assert result == "hell's paradise jigokuraku"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_string(self):
        """Empty string returns empty."""
        assert normalize_title_for_dedup("") == ""

    def test_whitespace_only(self):
        """Whitespace-only string returns empty."""
        assert normalize_title_for_dedup("   ") == ""

    def test_only_symbols(self):
        """Only symbols returns original (symbols removed, nothing left)."""
        # When only symbols, they're removed but original title is returned as fallback
        result = normalize_title_for_dedup("!!!***@@@")
        # The symbols get removed, leaving empty string, so we get the original lowercased
        assert result == "!!!***@@@"

    def test_only_language_markers(self):
        """Only language markers preserved."""
        result = normalize_title_for_dedup("Dublado")
        assert result == "dublado"

    def test_single_word(self):
        """Single word normalized."""
        assert normalize_title_for_dedup("Anime") == "anime"

    def test_very_long_title(self):
        """Very long title handled correctly."""
        long_title = "A Very Long Anime Title With Many Words And Season 2 Dublado"
        result = normalize_title_for_dedup(long_title)
        assert "season" in result
        assert "2" in result
        assert "dublado" in result
        assert result == "a very long anime title with many words and season 2 dublado"

    def test_multiple_consecutive_spaces(self):
        """Multiple consecutive spaces collapsed."""
        assert normalize_title_for_dedup("Anime    A") == "anime a"

    def test_leading_trailing_spaces(self):
        """Leading and trailing spaces stripped."""
        assert normalize_title_for_dedup("   Anime A   ") == "anime a"

    def test_numeric_only_part(self):
        """Numbers preserved."""
        assert normalize_title_for_dedup("Anime 123") == "anime 123"

    def test_mixed_case_input(self):
        """Mixed case normalized to lowercase."""
        assert normalize_title_for_dedup("AnImE a TiTlE") == "anime a title"


class TestComplexScenarios:
    """Test real-world complex scenarios."""

    def test_anilist_bilingual_style_first_part(self):
        """AniList bilingual titles handled correctly."""
        result = normalize_title_for_dedup("Kimetsu no Yaiba")
        assert result == "kimetsu no yaiba"

    def test_multiple_season_indicators(self):
        """Multiple season-like indicators all preserved."""
        result = normalize_title_for_dedup("Anime Season 2 Part 3")
        assert "season" in result
        assert "2" in result
        assert "part" in result
        assert "3" in result

    def test_complex_dubbed_subtitle_example(self):
        """Complex title with Dublado preserved."""
        result = normalize_title_for_dedup("Anime A: Revolucao Dublado")
        assert "dublado" in result
        assert result == "anime a revolucao dublado"

    def test_my_hero_academia_example(self):
        """My Hero Academia seasons handled correctly."""
        result1 = normalize_title_for_dedup("My Hero Academia Season 5")
        result2 = normalize_title_for_dedup("My Hero Academia 5th Season")
        # Both preserve season info, but in different formats
        assert "season" in result1
        assert "5" in result1
        assert "5th" in result2
        assert "season" in result2

    def test_re_zero_example(self):
        """Re:Zero with separator and season handled."""
        result = normalize_title_for_dedup("Re:Zero Season 3")
        # Colon becomes space, so "Re:Zero" → "re zero"
        assert result == "re zero season 3"

    def test_hell_paradise_example(self):
        """Hell's Paradise with apostrophe and separator."""
        result = normalize_title_for_dedup("Hell's Paradise: Jigokuraku")
        assert "hell's" in result
        assert "paradise" in result
        assert "jigokuraku" in result
        assert result == "hell's paradise jigokuraku"


class TestDeterminism:
    """Test that normalization is deterministic."""

    def test_same_input_same_output(self):
        """Same input always produces same output."""
        input_title = "Anime: Title Dublado Season 2"
        results = [normalize_title_for_dedup(input_title) for _ in range(5)]
        assert all(r == results[0] for r in results)

    def test_multiple_calls_identical(self):
        """Multiple calls with same title are identical."""
        title = "Complex: Anime Title - With Everything Dublado Temporada 2"
        result1 = normalize_title_for_dedup(title)
        result2 = normalize_title_for_dedup(title)
        assert result1 == result2


class TestDubladoVsLegendado:
    """Test that Dublado and Legendado versions are kept separate."""

    def test_dubbed_and_subtitled_different(self):
        """Dublado and Legendado versions should NOT merge."""
        result_dub = normalize_title_for_dedup("Death Note Dublado")
        result_legend = normalize_title_for_dedup("Death Note Legendado")
        # Both preserve the language marker, so they're different
        assert result_dub != result_legend
        assert result_dub == "death note dublado"
        assert result_legend == "death note legendado"

    def test_multiple_versions_distinct(self):
        """Multiple language versions are all distinct."""
        base = "Anime Title"
        dubbed = normalize_title_for_dedup(f"{base} Dublado")
        subtitled = normalize_title_for_dedup(f"{base} Legendado")
        english_dub = normalize_title_for_dedup(f"{base} English Dub")

        # All three should be different
        assert dubbed != subtitled
        assert subtitled != english_dub
        assert dubbed != english_dub


class TestCompactFallbackHelpers:
    """Test helper functions used by compact fallback dedup logic."""

    def test_compact_key_removes_whitespace_only(self):
        """Compact key removes spaces while preserving remaining characters."""
        normalized = normalize_title_for_dedup("aaa b b cc")
        assert normalized == "aaa b b cc"
        assert get_compact_normalized_title_key(normalized) == "aaabbcc"

    def test_language_compatibility_equal_markers(self):
        """Same language markers are compatible."""
        left = normalize_title_for_dedup("Anime A Dublado")
        right = normalize_title_for_dedup("Anime A - Dublado")
        assert are_language_version_markers_compatible(left, right) is True

    def test_language_compatibility_incompatible_markers(self):
        """Different language markers are incompatible."""
        left = normalize_title_for_dedup("Anime A Dublado")
        right = normalize_title_for_dedup("Anime A Legendado")
        assert are_language_version_markers_compatible(left, right) is False

    def test_season_compatibility_equal_markers(self):
        """Equal season markers are compatible."""
        left = normalize_title_for_dedup("Anime A Season 2")
        right = normalize_title_for_dedup("Anime A - Season 2")
        assert are_season_markers_compatible(left, right) is True

    def test_season_compatibility_different_markers(self):
        """Different season markers are incompatible."""
        left = normalize_title_for_dedup("Anime A Season 2")
        right = normalize_title_for_dedup("Anime A Season 3")
        assert are_season_markers_compatible(left, right) is False
