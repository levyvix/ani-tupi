"""Tests for episode range parser."""

import pytest

from utils.episode_range_parser import (
    RangeParseError,
    parse_episode_range,
    validate_episode_range,
)


class TestParseEpisodeRangeSingleEpisode:
    """Test parsing single episode numbers."""

    def test_single_episode_valid(self):
        """Parse single valid episode."""
        assert parse_episode_range("5", 24) == [5]

    def test_single_episode_first(self):
        """Parse first episode."""
        assert parse_episode_range("1", 12) == [1]

    def test_single_episode_last(self):
        """Parse last episode."""
        assert parse_episode_range("12", 12) == [12]

    def test_single_episode_out_of_bounds(self):
        """Single episode beyond total."""
        with pytest.raises(RangeParseError):
            parse_episode_range("13", 12)

    def test_single_episode_negative_as_range(self):
        """Negative sign in range context means 1 to N."""
        # "-5" is interpreted as "1-5" (start to 5)
        assert parse_episode_range("-5", 12) == [1, 2, 3, 4, 5]

    def test_single_episode_zero(self):
        """Zero episode number."""
        with pytest.raises(RangeParseError):
            parse_episode_range("0", 12)


class TestParseEpisodeRangeInclusiveRange:
    """Test parsing inclusive ranges like 5-15."""

    def test_range_standard(self):
        """Parse standard range."""
        assert parse_episode_range("1-12", 12) == list(range(1, 13))

    def test_range_middle(self):
        """Parse range in middle."""
        assert parse_episode_range("5-15", 24) == list(range(5, 16))

    def test_range_single_span(self):
        """Range of single episode."""
        assert parse_episode_range("5-5", 12) == [5]

    def test_range_first_to_last(self):
        """Full range."""
        assert parse_episode_range("1-24", 24) == list(range(1, 25))

    def test_range_clamped_end(self):
        """Range end beyond total gets clamped."""
        result = parse_episode_range("20-999", 24)
        assert result == list(range(20, 25))

    def test_range_clamped_start(self):
        """Range start before 1 gets clamped."""
        result = parse_episode_range("-5", 24)
        assert result == list(range(1, 6))

    def test_range_reversed(self):
        """Reversed range raises error."""
        with pytest.raises(RangeParseError):
            parse_episode_range("15-5", 24)


class TestParseEpisodeRangeOpenEnded:
    """Test parsing open-ended ranges like 5- or -12."""

    def test_range_open_end(self):
        """Parse from episode to end."""
        assert parse_episode_range("5-", 12) == list(range(5, 13))

    def test_range_open_end_first_episode(self):
        """Parse from first to end."""
        assert parse_episode_range("1-", 12) == list(range(1, 13))

    def test_range_open_start(self):
        """Parse from start to episode."""
        assert parse_episode_range("-12", 24) == list(range(1, 13))

    def test_range_open_start_last_episode(self):
        """Parse from start to last."""
        assert parse_episode_range("-24", 24) == list(range(1, 25))

    def test_range_both_open(self):
        """Only dash is invalid."""
        with pytest.raises(RangeParseError):
            parse_episode_range("-", 12)


class TestParseEpisodeRangeEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_string(self):
        """Empty string raises error."""
        with pytest.raises(RangeParseError):
            parse_episode_range("", 12)

    def test_whitespace_only(self):
        """Whitespace-only string raises error."""
        with pytest.raises(RangeParseError):
            parse_episode_range("   ", 12)

    def test_with_spaces(self):
        """String with spaces gets stripped."""
        assert parse_episode_range("  5  ", 12) == [5]

    def test_non_numeric_single(self):
        """Non-numeric single episode."""
        with pytest.raises(RangeParseError):
            parse_episode_range("abc", 12)

    def test_non_numeric_range_start(self):
        """Non-numeric range start."""
        with pytest.raises(RangeParseError):
            parse_episode_range("abc-5", 12)

    def test_non_numeric_range_end(self):
        """Non-numeric range end."""
        with pytest.raises(RangeParseError):
            parse_episode_range("5-xyz", 12)

    def test_multiple_dashes(self):
        """Multiple dashes in range."""
        with pytest.raises(RangeParseError):
            parse_episode_range("1-5-10", 24)

    def test_zero_total_episodes(self):
        """Zero total episodes is invalid."""
        with pytest.raises(RangeParseError):
            parse_episode_range("5", 0)

    def test_negative_total_episodes(self):
        """Negative total episodes is invalid."""
        with pytest.raises(RangeParseError):
            parse_episode_range("5", -12)


class TestParseEpisodeRangeRealistic:
    """Test realistic user inputs."""

    def test_first_12_of_many(self):
        """Common: download first 12 of longer series."""
        result = parse_episode_range("1-12", 52)
        assert result == list(range(1, 13))
        assert len(result) == 12

    def test_specific_range_of_long_series(self):
        """Download specific range of long series."""
        result = parse_episode_range("24-48", 96)
        assert result == list(range(24, 49))
        assert len(result) == 25

    def test_resume_from_middle(self):
        """Download from watched point to end."""
        result = parse_episode_range("25-", 50)
        assert result == list(range(25, 51))
        assert len(result) == 26

    def test_catch_up_to_current(self):
        """Download from start to current point."""
        result = parse_episode_range("-24", 48)
        assert result == list(range(1, 25))
        assert len(result) == 24


class TestValidateEpisodeRange:
    """Test range validation function."""

    def test_validate_valid_range(self):
        """Valid range passes validation."""
        assert validate_episode_range([1, 2, 3, 4, 5], 12)

    def test_validate_single_valid(self):
        """Single valid episode passes."""
        assert validate_episode_range([5], 12)

    def test_validate_episode_out_of_bounds_high(self):
        """Episode beyond total fails."""
        with pytest.raises(RangeParseError):
            validate_episode_range([1, 2, 13], 12)

    def test_validate_episode_out_of_bounds_low(self):
        """Episode below 1 fails."""
        with pytest.raises(RangeParseError):
            validate_episode_range([0, 1, 2], 12)

    def test_validate_empty_list(self):
        """Empty list fails."""
        with pytest.raises(RangeParseError):
            validate_episode_range([], 12)

    def test_validate_all_valid_complex(self):
        """Complex valid range."""
        episodes = list(range(5, 26))
        assert validate_episode_range(episodes, 50)
