"""Tests for AiringEpisodesService awaiting filter.

Tests cover:
- Filtering only awaiting episodes (within 90 days, not yet aired)
- Excluding already-aired episodes
- Excluding no-next-episode entries
- Excluding hiatus anime (90+ days in future)
- Sorting preserved on filtered results
- Empty result when no awaiting anime
"""

import time
from unittest.mock import patch

from services.anime.airing_episodes_service import AiringEpisodesService


class TestAwaitingEpisodeFilter:
    """Tests for _is_awaiting_episode helper method."""

    def test_none_airing_at_returns_false(self):
        """Test that None airing_at returns False."""
        assert AiringEpisodesService._is_awaiting_episode(None) is False

    def test_already_aired_returns_false(self):
        """Test that already-aired episode (past airing_at) returns False."""
        now = int(time.time())
        past_time = now - 86400  # 1 day ago

        assert AiringEpisodesService._is_awaiting_episode(past_time) is False

    def test_just_aired_returns_false(self):
        """Test that just-aired episode (airing_at == now) returns False."""
        now = int(time.time())

        assert AiringEpisodesService._is_awaiting_episode(now) is False

    def test_within_90_days_returns_true(self):
        """Test that episode within 90 days returns True."""
        now = int(time.time())
        in_30_days = now + (30 * 24 * 60 * 60)

        assert AiringEpisodesService._is_awaiting_episode(in_30_days) is True

    def test_exactly_90_days_in_future_returns_false(self):
        """Test that episode exactly 90 days away returns False (boundary)."""
        now = int(time.time())
        exactly_90_days = now + (90 * 24 * 60 * 60)

        assert AiringEpisodesService._is_awaiting_episode(exactly_90_days) is False

    def test_just_under_90_days_returns_true(self):
        """Test that episode just under 90 days returns True."""
        now = int(time.time())
        almost_90_days = now + (90 * 24 * 60 * 60) - 1

        assert AiringEpisodesService._is_awaiting_episode(almost_90_days) is True

    def test_far_future_returns_false(self):
        """Test that episode far in future (hiatus) returns False."""
        now = int(time.time())
        in_200_days = now + (200 * 24 * 60 * 60)

        assert AiringEpisodesService._is_awaiting_episode(in_200_days) is False


class TestGetWatchingWithAwaitingEpisodes:
    """Tests for get_watching_with_airing_episodes filter logic."""

    def setup_method(self):
        """Set up test service and mocks."""
        self.service = AiringEpisodesService()

    def _create_entry(
        self,
        anilist_id: int,
        title: str,
        progress: int,
        next_episode: int,
        airing_at: int | None,
    ) -> dict:
        """Helper to create a raw API entry."""
        return {
            "progress": progress,
            "media": {
                "id": anilist_id,
                "title": {"romaji": title, "english": None, "native": None},
                "averageScore": 80,
                "nextAiringEpisode": {"episode": next_episode, "airingAt": airing_at},
            },
        }

    def test_empty_responses_and_no_matching_entries(self):
        """Test empty result with empty API response or no matching entries."""
        # Empty API response
        with patch.object(self.service.client, "get_airing_episodes_for_watching", return_value=[]):
            result = self.service.get_watching_with_airing_episodes()
            assert result == []

        # No entries match filter (all aired or hiatus)
        now = int(time.time())
        with patch.object(
            self.service.client,
            "get_airing_episodes_for_watching",
            return_value=[
                self._create_entry(1001, "Already Aired", 10, 11, now - 86400),
                self._create_entry(1002, "On Hiatus", 5, 6, now + (200 * 24 * 60 * 60)),
            ],
        ):
            result = self.service.get_watching_with_airing_episodes()
            assert len(result) == 0

    def test_filter_comprehensive_scenario(self):
        """Test filtering with mix of awaiting, aired, hiatus, and no-airing entries."""
        now = int(time.time())
        in_30_days = now + (30 * 24 * 60 * 60)
        past_time = now - 86400
        in_200_days = now + (200 * 24 * 60 * 60)

        with patch.object(
            self.service.client,
            "get_airing_episodes_for_watching",
            return_value=[
                self._create_entry(1001, "Awaiting 1", 5, 6, in_30_days),
                self._create_entry(1002, "Already Aired", 10, 11, past_time),
                self._create_entry(1003, "Awaiting 2", 15, 17, in_30_days),
                self._create_entry(1004, "On Hiatus", 3, 4, in_200_days),
                {
                    "progress": 10,
                    "media": {
                        "id": 1005,
                        "title": {"romaji": "Completed", "english": None, "native": None},
                        "averageScore": 85,
                        "nextAiringEpisode": None,
                    },
                },
            ],
        ):
            result = self.service.get_watching_with_airing_episodes()

        # Should only include awaiting anime (1001, 1003)
        assert len(result) == 2
        assert all(r.anilist_id in (1001, 1003) for r in result)

    def test_sorting_and_episodes_behind_calculation(self):
        """Test sorting by episodes_behind and correct calculation."""
        now = int(time.time())
        in_30_days = now + (30 * 24 * 60 * 60)

        with patch.object(
            self.service.client,
            "get_airing_episodes_for_watching",
            return_value=[
                self._create_entry(1001, "Behind 3", 6, 10, in_30_days),  # 3 behind
                self._create_entry(1002, "Behind 1", 8, 10, in_30_days),  # 1 behind
                self._create_entry(1003, "Behind 5", 4, 10, in_30_days),  # 5 behind
                self._create_entry(1004, "Behind 4", 10, 15, in_30_days),  # 4 behind
            ],
        ):
            result = self.service.get_watching_with_airing_episodes()

        assert len(result) == 4
        # Should be sorted by episodes_behind descending
        assert [r.episodes_behind for r in result] == [5, 4, 3, 1]

    def test_malformed_entry_skipped(self):
        """Test that malformed entries are skipped gracefully."""
        now = int(time.time())
        in_30_days = now + (30 * 24 * 60 * 60)

        with patch.object(
            self.service.client,
            "get_airing_episodes_for_watching",
            return_value=[
                {"progress": 5, "media": None},  # Malformed
                self._create_entry(1001, "Valid", 5, 6, in_30_days),
            ],
        ):
            result = self.service.get_watching_with_airing_episodes()

        assert len(result) == 1
        assert result[0].anilist_id == 1001


class TestParseEndDate:
    """Tests for _parse_end_date helper method."""

    def test_complete_date(self):
        """Full date returns correct datetime."""
        from datetime import datetime, timezone

        result = AiringEpisodesService._parse_end_date({"year": 2025, "month": 3, "day": 15})
        assert result == datetime(2025, 3, 15, tzinfo=timezone.utc)

    def test_missing_day_uses_first(self):
        """Missing day falls back to day 1."""
        from datetime import datetime, timezone

        result = AiringEpisodesService._parse_end_date({"year": 2025, "month": 3, "day": None})
        assert result == datetime(2025, 3, 1, tzinfo=timezone.utc)

    def test_missing_month_and_day_uses_january_first(self):
        """Missing month and day falls back to Jan 1."""
        from datetime import datetime, timezone

        result = AiringEpisodesService._parse_end_date({"year": 2025, "month": None, "day": None})
        assert result == datetime(2025, 1, 1, tzinfo=timezone.utc)

    def test_none_returns_none(self):
        """None input returns None."""
        assert AiringEpisodesService._parse_end_date(None) is None

    def test_missing_year_returns_none(self):
        """Missing year returns None (not enough data)."""
        assert AiringEpisodesService._parse_end_date({"year": None, "month": 3, "day": 15}) is None


class TestIsWithinGracePeriod:
    """Tests for _is_within_grace_period helper method."""

    def test_ended_recently_returns_true(self):
        """Anime that ended 10 days ago is within grace period."""
        from datetime import datetime, timedelta, timezone

        recent = datetime.now(tz=timezone.utc) - timedelta(days=10)
        end_date = {"year": recent.year, "month": recent.month, "day": recent.day}
        assert AiringEpisodesService._is_within_grace_period(end_date) is True

    def test_ended_beyond_grace_period_returns_false(self):
        """Anime that ended 90 days ago is outside grace period."""
        from datetime import datetime, timedelta, timezone

        old = datetime.now(tz=timezone.utc) - timedelta(days=90)
        end_date = {"year": old.year, "month": old.month, "day": old.day}
        assert AiringEpisodesService._is_within_grace_period(end_date) is False

    def test_none_returns_false(self):
        """None end_date returns False."""
        assert AiringEpisodesService._is_within_grace_period(None) is False
