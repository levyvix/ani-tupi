"""
Tests for models.py

Coverage:
- AnimeMetadata creation and validation
- EpisodeData with mismatched title/URL lists
- VideoUrl with optional headers
- Invalid data raises validation errors
"""

import pytest
from pydantic import ValidationError

from models.models import AnimeMetadata, EpisodeData, VideoUrl


class TestAnimeMetadata:
    """Test AnimeMetadata model."""

    def test_create_valid_anime(self):
        """Should create valid AnimeMetadata."""
        anime = AnimeMetadata(
            title="Dandadan",
            url="https://animefire.plus/animes/dandadan",
            source="animefire",
        )
        assert anime.title == "Dandadan"
        assert anime.source == "animefire"
        assert anime.params is None

    def test_create_anime_with_params(self):
        """Should create AnimeMetadata with params."""
        anime = AnimeMetadata(
            title="Dandadan",
            url="https://animefire.plus/animes/dandadan",
            source="animefire",
            params={"key": "value"},
        )
        assert anime.params == {"key": "value"}

    def test_anime_title_required(self):
        """Should require title field."""
        with pytest.raises(ValidationError):
            AnimeMetadata(
                url="https://example.com",
                source="animefire",
            )

    def test_anime_url_required(self):
        """Should require url field."""
        with pytest.raises(ValidationError):
            AnimeMetadata(
                title="Dandadan",
                source="animefire",
            )

    def test_anime_source_required(self):
        """Should require source field."""
        with pytest.raises(ValidationError):
            AnimeMetadata(
                title="Dandadan",
                url="https://example.com",
            )

    def test_anime_title_empty_string_invalid(self):
        """Should reject empty title."""
        with pytest.raises(ValidationError):
            AnimeMetadata(
                title="",
                url="https://example.com",
                source="animefire",
            )

    def test_anime_url_empty_string_invalid(self):
        """Should reject empty URL."""
        with pytest.raises(ValidationError):
            AnimeMetadata(
                title="Dandadan",
                url="",
                source="animefire",
            )

    @pytest.mark.parametrize(
        "title",
        [
            "Dandadan",
            "Attack on Titan",
            "Solo Leveling",
            "Jujutsu Kaisen",
        ],
    )
    def test_anime_various_titles(self, title):
        """Should accept various valid titles."""
        anime = AnimeMetadata(
            title=title,
            url="https://example.com",
            source="animefire",
        )
        assert anime.title == title


class TestEpisodeData:
    """Test EpisodeData model."""

    def test_create_valid_episodes(self):
        """Should create valid EpisodeData."""
        episodes = EpisodeData(
            anime_title="Dandadan",
            episode_titles=["Ep 1", "Ep 2"],
            episode_urls=["https://example.com/ep1", "https://example.com/ep2"],
            source="animefire",
        )
        assert episodes.anime_title == "Dandadan"
        assert len(episodes.episode_titles) == 2
        assert len(episodes.episode_urls) == 2

    def test_episode_title_url_mismatch_invalid(self):
        """Should reject mismatched title/URL lists."""
        with pytest.raises(ValidationError):
            EpisodeData(
                anime_title="Dandadan",
                episode_titles=["Ep 1", "Ep 2"],
                episode_urls=["https://example.com/ep1"],  # Only 1 URL for 2 titles
                source="animefire",
            )

    def test_episode_empty_lists_valid(self):
        """Should allow empty episode lists."""
        episodes = EpisodeData(
            anime_title="Dandadan",
            episode_titles=[],
            episode_urls=[],
            source="animefire",
        )
        assert len(episodes.episode_titles) == 0
        assert len(episodes.episode_urls) == 0

    def test_episode_anime_title_required(self):
        """Should require anime_title field."""
        with pytest.raises(ValidationError):
            EpisodeData(
                episode_titles=["Ep 1"],
                episode_urls=["https://example.com/ep1"],
                source="animefire",
            )

    def test_episode_source_required(self):
        """Should require source field."""
        with pytest.raises(ValidationError):
            EpisodeData(
                anime_title="Dandadan",
                episode_titles=["Ep 1"],
                episode_urls=["https://example.com/ep1"],
            )

    def test_episode_single_episode(self):
        """Should handle single episode."""
        episodes = EpisodeData(
            anime_title="Short Anime",
            episode_titles=["Only Episode"],
            episode_urls=["https://example.com/ep1"],
            source="animefire",
        )
        assert len(episodes.episode_titles) == 1
        assert len(episodes.episode_urls) == 1

    @pytest.mark.parametrize(
        "count",
        [1, 12, 26, 50],
    )
    def test_episode_various_counts(self, count):
        """Should handle various episode counts."""
        episodes = EpisodeData(
            anime_title="Test Anime",
            episode_titles=[f"Ep {i}" for i in range(1, count + 1)],
            episode_urls=[f"https://example.com/ep{i}" for i in range(count)],
            source="animefire",
        )
        assert len(episodes.episode_titles) == count
        assert len(episodes.episode_urls) == count


class TestVideoUrl:
    """Test VideoUrl model."""

    def test_create_video_url_minimal(self):
        """Should create VideoUrl with just URL."""
        video = VideoUrl(url="https://example.com/video.m3u8")
        assert video.url == "https://example.com/video.m3u8"
        assert video.headers is None

    def test_create_video_url_with_headers(self):
        """Should create VideoUrl with headers."""
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://example.com"}
        video = VideoUrl(url="https://example.com/video.m3u8", headers=headers)
        assert video.headers == headers
        assert len(video.headers) == 2

    def test_video_url_required(self):
        """Should require URL field."""
        with pytest.raises(ValidationError):
            VideoUrl(headers={"User-Agent": "Mozilla/5.0"})

    def test_video_url_empty_invalid(self):
        """Should reject empty URL."""
        with pytest.raises(ValidationError):
            VideoUrl(url="")

    def test_video_url_various_formats(self):
        """Should accept various URL formats."""
        valid_urls = [
            "https://example.com/video.m3u8",
            "https://example.com/video.mp4",
            "https://cdn.example.com/stream",
            "http://example.com:8080/video",
        ]
        for url in valid_urls:
            video = VideoUrl(url=url)
            assert video.url == url

    def test_video_headers_dict_structure(self):
        """Should validate headers as dict."""
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://example.com",
            "Accept": "application/json",
        }
        video = VideoUrl(url="https://example.com/video.m3u8", headers=headers)
        assert video.headers is not None
        assert "User-Agent" in video.headers

    def test_video_headers_empty_dict(self):
        """Should accept empty headers dict."""
        video = VideoUrl(url="https://example.com/video.m3u8", headers={})
        assert video.headers == {}

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/video.m3u8",
            "https://cdn.example.com/s5/mp4_temp/anime/1/720p.mp4",
            "http://localhost:8080/stream.m3u8",
        ],
    )
    def test_video_url_formats(self, url):
        """Should accept various valid URL formats."""
        video = VideoUrl(url=url)
        assert video.url == url


class TestModelSerialization:
    """Test model serialization and deserialization."""

    def test_anime_to_dict(self):
        """Should serialize AnimeMetadata to dict."""
        anime = AnimeMetadata(
            title="Dandadan",
            url="https://example.com",
            source="animefire",
        )
        anime_dict = anime.model_dump()
        assert anime_dict["title"] == "Dandadan"
        assert "url" in anime_dict

    def test_episodes_to_dict(self):
        """Should serialize EpisodeData to dict."""
        episodes = EpisodeData(
            anime_title="Dandadan",
            episode_titles=["Ep 1"],
            episode_urls=["https://example.com/ep1"],
            source="animefire",
        )
        episodes_dict = episodes.model_dump()
        assert episodes_dict["anime_title"] == "Dandadan"
        assert "episode_titles" in episodes_dict

    def test_video_to_dict(self):
        """Should serialize VideoUrl to dict."""
        video = VideoUrl(url="https://example.com/video.m3u8")
        video_dict = video.model_dump()
        assert video_dict["url"] == "https://example.com/video.m3u8"
        assert "headers" in video_dict

    def test_anime_from_dict(self):
        """Should deserialize AnimeMetadata from dict."""
        data = {
            "title": "Dandadan",
            "url": "https://example.com",
            "source": "animefire",
        }
        anime = AnimeMetadata(**data)
        assert anime.title == "Dandadan"

    def test_episodes_from_dict(self):
        """Should deserialize EpisodeData from dict."""
        data = {
            "anime_title": "Dandadan",
            "episode_titles": ["Ep 1"],
            "episode_urls": ["https://example.com/ep1"],
            "source": "animefire",
        }
        episodes = EpisodeData(**data)
        assert episodes.anime_title == "Dandadan"

    def test_video_from_dict(self):
        """Should deserialize VideoUrl from dict."""
        data = {
            "url": "https://example.com/video.m3u8",
            "headers": {"User-Agent": "Mozilla/5.0"},
        }
        video = VideoUrl(**data)
        assert video.url == "https://example.com/video.m3u8"
        assert video.headers["User-Agent"] == "Mozilla/5.0"
