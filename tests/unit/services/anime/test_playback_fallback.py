"""Tests for automatic source fallback during episode playback."""

from unittest.mock import Mock

from services.anime.playback_fallback import (
    MPV_USER_ABORT_CODE,
    PlaybackFallbackResult,
    play_episode_with_fallback,
)
from utils.video_player import VideoPlaybackResult


class TestPlaybackFallbackResult:
    """Test PlaybackFallbackResult NamedTuple."""

    def test_result_creation(self):
        """Test creating a result with all fields."""
        playback_result = VideoPlaybackResult(exit_code=0, action="quit", data=None)
        sources_tried = [("anitube", 2), ("animefire", 0)]

        result = PlaybackFallbackResult(
            playback_result=playback_result,
            source_used="animefire",
            sources_tried=sources_tried,
            all_failed=False,
        )

        assert result.playback_result == playback_result
        assert result.source_used == "animefire"
        assert result.sources_tried == sources_tried
        assert result.all_failed is False


class TestPlayEpisodeWithFallback:
    """Test fallback logic."""

    def create_mock_player(self, exit_codes: list[int]):
        """Create a mock VideoPlayer that returns specified exit codes in sequence."""
        player = Mock()
        results = [
            VideoPlaybackResult(exit_code=code, action="quit", data=None) for code in exit_codes
        ]
        player.play_episode.side_effect = results
        return player

    def test_empty_sources_list(self):
        """Test when no sources are available."""
        player = Mock()
        sources = []

        result = play_episode_with_fallback(
            player=player,
            sources=sources,
            anime_title="Test Anime",
            episode_number=1,
            total_episodes=12,
        )

        assert result.all_failed is True
        assert result.source_used is None
        assert result.sources_tried == []
        assert result.playback_result.exit_code == 2

    def test_first_source_succeeds(self):
        """Test when first source succeeds (exit code 0)."""
        player = self.create_mock_player([0])  # First source succeeds
        sources = [("https://url1.mp4", "anitube"), ("https://url2.mp4", "animefire")]

        result = play_episode_with_fallback(
            player=player,
            sources=sources,
            anime_title="Test Anime",
            episode_number=1,
            total_episodes=12,
        )

        assert result.all_failed is False
        assert result.source_used == "anitube"
        assert len(result.sources_tried) == 1
        assert result.sources_tried[0] == ("anitube", 0)
        assert player.play_episode.call_count == 1

    def test_first_source_fails_second_succeeds(self):
        """Test when first source fails but second succeeds."""
        player = self.create_mock_player([2, 0])  # First fails, second succeeds
        sources = [("https://url1.mp4", "anitube"), ("https://url2.mp4", "animefire")]

        result = play_episode_with_fallback(
            player=player,
            sources=sources,
            anime_title="Test Anime",
            episode_number=1,
            total_episodes=12,
        )

        assert result.all_failed is False
        assert result.source_used == "animefire"
        assert len(result.sources_tried) == 2
        assert result.sources_tried[0] == ("anitube", 2)
        assert result.sources_tried[1] == ("animefire", 0)
        assert player.play_episode.call_count == 2

    def test_all_sources_fail(self):
        """Test when all sources fail."""
        player = self.create_mock_player([2, 1, 4])  # All fail
        sources = [
            ("https://url1.mp4", "anitube"),
            ("https://url2.mp4", "animefire"),
            ("https://url3.mp4", "sushianimes"),
        ]

        result = play_episode_with_fallback(
            player=player,
            sources=sources,
            anime_title="Test Anime",
            episode_number=1,
            total_episodes=12,
        )

        assert result.all_failed is True
        assert result.source_used is None
        assert len(result.sources_tried) == 3
        assert result.sources_tried[0] == ("anitube", 2)
        assert result.sources_tried[1] == ("animefire", 1)
        assert result.sources_tried[2] == ("sushianimes", 4)

    def test_user_abort_stops_immediately(self):
        """Test that user abort (exit code 3) stops fallback immediately."""
        player = self.create_mock_player([MPV_USER_ABORT_CODE])  # User aborts
        sources = [("https://url1.mp4", "anitube"), ("https://url2.mp4", "animefire")]

        result = play_episode_with_fallback(
            player=player,
            sources=sources,
            anime_title="Test Anime",
            episode_number=1,
            total_episodes=12,
        )

        assert result.all_failed is False
        assert result.source_used == "anitube"
        assert len(result.sources_tried) == 1
        assert player.play_episode.call_count == 1

    def test_action_next_without_fallback(self):
        """Test that actions like 'next' (exit code 0) don't trigger fallback."""
        playback_result = VideoPlaybackResult(exit_code=0, action="next", data={"episode": 2})
        player = Mock()
        player.play_episode.return_value = playback_result
        sources = [("https://url1.mp4", "anitube"), ("https://url2.mp4", "animefire")]

        result = play_episode_with_fallback(
            player=player,
            sources=sources,
            anime_title="Test Anime",
            episode_number=1,
            total_episodes=12,
        )

        assert result.all_failed is False
        assert result.source_used == "anitube"
        assert player.play_episode.call_count == 1

    def test_single_source_no_retry_message(self):
        """Test that with single source, fallback progress messages are skipped."""
        player = self.create_mock_player([0])
        sources = [("https://url1.mp4", "anitube")]

        result = play_episode_with_fallback(
            player=player,
            sources=sources,
            anime_title="Test Anime",
            episode_number=1,
            total_episodes=12,
        )

        assert result.all_failed is False
        assert result.source_used == "anitube"
        call_args = player.play_episode.call_args
        assert call_args[1]["url"] == "https://url1.mp4"
        assert call_args[1]["source"] == "anitube"

    def test_anilist_params_passed_to_player(self):
        """Test that AniList parameters are properly passed."""
        player = self.create_mock_player([0])
        sources = [("https://url1.mp4", "anitube")]

        play_episode_with_fallback(
            player=player,
            sources=sources,
            anime_title="Test Anime",
            episode_number=5,
            total_episodes=12,
            anilist_id=12345,
            anilist_episodes=13,
        )

        call_args = player.play_episode.call_args
        assert call_args[1]["anilist_id"] == 12345
        assert call_args[1]["anilist_episodes"] == 13
        assert call_args[1]["episode_number"] == 5


class TestPlayEpisodeWithFallbackLazyExtraction:
    """Test lazy extraction path (extractor callback)."""

    def create_mock_player(self, exit_codes: list[int]):
        player = Mock()
        results = [
            VideoPlaybackResult(exit_code=code, action="quit", data=None) for code in exit_codes
        ]
        player.play_episode.side_effect = results
        return player

    def test_stops_extracting_after_first_success(self):
        """First source extracts + plays OK; lower sources never extracted."""
        player = self.create_mock_player([0])
        extractor = Mock(return_value=["https://video1.mp4"])
        sources = [
            ("https://page1", "anitube"),
            ("https://page2", "animesdigital"),
            ("https://page3", "animesonlinecc"),
        ]

        result = play_episode_with_fallback(
            player=player,
            sources=sources,
            anime_title="Test Anime",
            episode_number=1,
            total_episodes=12,
            extractor=extractor,
        )

        assert result.source_used == "anitube"
        assert extractor.call_count == 1  # only priority source touched
        assert extractor.call_args[0] == ("https://page1", "anitube")
        # video URL and page-as-referrer forwarded to player
        call_args = player.play_episode.call_args[1]
        assert call_args["url"] == "https://video1.mp4"
        assert call_args["referrer"] == "https://page1"

    def test_skips_sources_that_fail_extraction(self):
        """Sources returning None from extractor are skipped, not played."""
        player = self.create_mock_player([0])

        def extractor(page_url, source):
            return None if source in ("anroll", "animesonlinecc") else ["https://video.mp4"]

        sources = [
            ("https://anroll", "anroll"),
            ("https://onlinecc", "animesonlinecc"),
            ("https://anitube", "anitube"),
        ]

        result = play_episode_with_fallback(
            player=player,
            sources=sources,
            anime_title="Test Anime",
            episode_number=1,
            total_episodes=12,
            extractor=extractor,
        )

        assert result.source_used == "anitube"
        assert player.play_episode.call_count == 1
        assert result.sources_tried == [("anitube", 0)]

    def test_all_fail_extraction(self):
        """When nothing extracts, result is all_failed and player never called."""
        player = Mock()
        sources = [("https://p1", "anroll"), ("https://p2", "animesonlinecc")]

        result = play_episode_with_fallback(
            player=player,
            sources=sources,
            anime_title="Test Anime",
            episode_number=1,
            total_episodes=12,
            extractor=lambda page_url, source: None,
        )

        assert result.all_failed is True
        assert result.source_used is None
        assert player.play_episode.call_count == 0

    def test_tries_lower_rank_candidate_within_single_source(self):
        """With one source, MPV falls back to the next-quality candidate."""
        player = self.create_mock_player([2, 0])
        extractor = Mock(return_value=["https://blocked.m3u8", "https://works.mp4"])
        sources = [("https://page1", "anitube")]

        result = play_episode_with_fallback(
            player=player,
            sources=sources,
            anime_title="Test Anime",
            episode_number=1,
            total_episodes=12,
            extractor=extractor,
        )

        assert result.source_used == "anitube"
        assert result.sources_tried == [("anitube", 2), ("anitube", 0)]
        assert extractor.call_count == 1
        assert player.play_episode.call_count == 2
        assert player.play_episode.call_args_list[0][1]["url"] == "https://blocked.m3u8"
        assert player.play_episode.call_args_list[1][1]["url"] == "https://works.mp4"

    def test_rank_major_tries_best_quality_of_all_sources_first(self):
        """Rank 0 of every source is attempted before rank 1 of any source."""
        # anitube rank0 fail, animefire rank0 fail, anitube rank1 works.
        player = self.create_mock_player([2, 2, 0])
        sources = [
            ("https://page1", "anitube"),
            ("https://page2", "animefire"),
        ]

        def extractor(page_url, source):
            return ["https://hd-{0}.m3u8".format(source), "https://sd-{0}.mp4".format(source)]

        result = play_episode_with_fallback(
            player=player,
            sources=sources,
            anime_title="Test Anime",
            episode_number=1,
            total_episodes=12,
            extractor=extractor,
        )

        assert result.source_used == "anitube"
        urls = [c[1]["url"] for c in player.play_episode.call_args_list]
        assert urls == [
            "https://hd-anitube.m3u8",
            "https://hd-animefire.m3u8",
            "https://sd-anitube.mp4",
        ]


class TestPlayEpisodeWithFallbackIntegration:
    """Integration tests for fallback flow."""

    def test_fallback_with_three_sources_two_fail(self):
        """Test realistic scenario: 3 sources, first 2 fail, 3rd succeeds."""
        player = Mock()
        player.play_episode.side_effect = [
            VideoPlaybackResult(exit_code=2, action="quit", data=None),
            VideoPlaybackResult(exit_code=2, action="quit", data=None),
            VideoPlaybackResult(exit_code=0, action="quit", data=None),
        ]

        sources = [
            ("https://anitube.com/video", "anitube"),
            ("https://animefire.com/video", "animefire"),
            ("https://sushianimes.com/video", "sushianimes"),
        ]

        result = play_episode_with_fallback(
            player=player,
            sources=sources,
            anime_title="Test Anime",
            episode_number=11,
            total_episodes=12,
            anilist_id=9999,
        )

        assert result.all_failed is False
        assert result.source_used == "sushianimes"
        assert len(result.sources_tried) == 3
        assert player.play_episode.call_count == 3
