"""Unit tests for range_parser utility.

Tests all input patterns and edge cases for chapter range selection.
"""

import pytest

from utils.range_parser import RangeParseError, parse_episode_range, parse_range_input


class TestRangeParserEmpty:
    """Test empty input and defaults."""

    def test_empty_input_no_history(self):
        """Empty input with no history should return first N chapters."""
        available = ["1", "2", "3", "4", "5"]
        result = parse_range_input("", None, available, default_count=5)
        assert result == ["1", "2", "3", "4", "5"]

    def test_empty_input_with_history(self):
        """Empty input with history should return next N chapters after last."""
        available = ["40", "41", "42", "43", "44", "45"]
        result = parse_range_input("", "41", available, default_count=3)
        assert result == ["42", "43", "44"]


class TestRangeParserCount:
    """Test count format: "5" means next 5 chapters."""

    def test_count_no_history(self):
        """Count with no history should return first N chapters."""
        available = ["1", "2", "3", "4", "5", "6"]
        result = parse_range_input("3", None, available)
        assert result == ["1", "2", "3"]

    def test_count_with_history(self):
        """Count with history should return next N after last."""
        available = ["40", "41", "42", "43", "44", "45"]
        result = parse_range_input("5", "41", available)
        assert result == ["42", "43", "44", "45"]  # Only 4 available after 41

    def test_count_exceeds_available(self):
        """Count greater than available should raise error."""
        available = ["1", "2", "3"]
        with pytest.raises(ValueError, match="Requested 5 chapters but only 3 available"):
            parse_range_input("5", None, available)


class TestRangeParserRange:
    """Test range format: "3-10" means chapters 3 through 10."""

    def test_range_exact(self):
        """Range that exactly matches available chapters."""
        available = ["1", "2", "3", "4", "5"]
        result = parse_range_input("2-4", None, available)
        assert result == ["2", "3", "4"]

    def test_range_with_decimals(self):
        """Range with decimal chapter numbers."""
        available = ["42", "42.5", "43", "43.5", "44"]
        result = parse_range_input("42.5-43.5", None, available)
        assert result == ["42.5", "43", "43.5"]

    def test_range_invalid_order(self):
        """Range with start > end should raise error."""
        available = ["1", "2", "3"]
        with pytest.raises(ValueError, match="start.*cannot be greater than end"):
            parse_range_input("5-2", None, available)


class TestRangeParserKeyword:
    """Test keyword "all" for all available chapters."""

    def test_all_with_history(self):
        """'all' with history should return chapters after last."""
        available = ["1", "2", "3", "4", "5"]
        result = parse_range_input("all", "3", available)
        assert result == ["4", "5"]


class TestRangeParserErrors:
    """Test error handling and validation."""

    def test_invalid_format(self):
        """Invalid format should raise error."""
        available = ["1", "2", "3"]
        with pytest.raises(ValueError, match="Invalid range format"):
            parse_range_input("abc", None, available)

    def test_multiple_dashes(self):
        """Range with multiple dashes should raise error."""
        available = ["1", "2", "3"]
        with pytest.raises(ValueError, match="Invalid range format"):
            parse_range_input("1-2-3", None, available)


class TestRangeParserEdgeCases:
    """Test edge cases and special scenarios."""

    def test_range_spanning_gaps(self):
        """Range that spans missing chapters (gaps in available)."""
        available = ["1", "5", "10"]  # Gaps: 2-4, 6-9
        result = parse_range_input("1-10", None, available)
        assert result == ["1", "5", "10"]  # Only return available


class TestRangeParserIntegration:
    """Integration tests combining multiple features."""

    def test_realistic_manga_scenario_continue_reading(self):
        """User has read up to chapter 41, wants next 5."""
        available = [str(i) for i in range(1, 51)]  # Chapters 1-50
        result = parse_range_input("", "41", available, default_count=5)
        assert result == ["42", "43", "44", "45", "46"]

    def test_realistic_manga_scenario_jump_to_range(self):
        """User wants specific range from chapter 10 to 15."""
        available = [str(i) for i in range(1, 51)]
        result = parse_range_input("10-15", None, available)
        assert result == ["10", "11", "12", "13", "14", "15"]

    def test_realistic_manga_with_decimals(self):
        """Realistic scenario with decimal chapters."""
        available = ["40", "40.5", "41", "41.5", "42"]
        result = parse_range_input("40.5-41.5", None, available)
        assert result == ["40.5", "41", "41.5"]


class TestParseEpisodeRange:
    """The generic parser reproduces the int-based episode behavior exactly."""

    def test_full_range(self):
        assert parse_episode_range("1-12", 12) == list(range(1, 13))

    def test_single_episode(self):
        assert parse_episode_range("5", 24) == [5]

    def test_open_end_range(self):
        """'5-' means episode 5 through the last available episode."""
        assert parse_episode_range("5-", 12) == [5, 6, 7, 8, 9, 10, 11, 12]

    def test_open_start_range(self):
        """'-12' means episode 1 through 12."""
        assert parse_episode_range("-12", 24) == list(range(1, 13))

    def test_partial_range(self):
        assert parse_episode_range("5-15", 24) == list(range(5, 16))

    def test_range_clamped_to_total(self):
        """End beyond total is clamped down to total."""
        assert parse_episode_range("10-999", 12) == [10, 11, 12]

    def test_invalid_non_numeric_single(self):
        with pytest.raises(RangeParseError, match="não é número"):
            parse_episode_range("abc", 12)

    def test_invalid_non_numeric_start(self):
        with pytest.raises(RangeParseError, match="Início do intervalo não é número"):
            parse_episode_range("abc-5", 12)

    def test_invalid_non_numeric_end(self):
        with pytest.raises(RangeParseError, match="Fim do intervalo não é número"):
            parse_episode_range("5-abc", 12)

    def test_reversed_range(self):
        with pytest.raises(RangeParseError, match="invertido"):
            parse_episode_range("10-5", 12)

    def test_multiple_dashes(self):
        with pytest.raises(RangeParseError, match="múltiplos '-'"):
            parse_episode_range("1-5-10", 12)

    def test_dash_only(self):
        with pytest.raises(RangeParseError, match="'-' sozinho"):
            parse_episode_range("-", 12)

    def test_episode_below_one(self):
        with pytest.raises(RangeParseError, match="deve ser >= 1"):
            parse_episode_range("0", 12)

    def test_single_out_of_bounds(self):
        with pytest.raises(RangeParseError, match="fora do intervalo"):
            parse_episode_range("99", 12)

    def test_empty_input(self):
        with pytest.raises(RangeParseError, match="entrada vazia"):
            parse_episode_range("", 12)

    def test_zero_total_episodes(self):
        with pytest.raises(RangeParseError, match="maior que 0"):
            parse_episode_range("1", 0)
