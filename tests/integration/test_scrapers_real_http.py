"""Integration tests — real HTTP calls to scraper sites.

Each test verifies the scraper still works against the live site.
Run manually: uv run pytest tests/integration/test_scrapers_real_http.py -v -s

These tests hit real sites so they are slow and can fail if a site is down.

MPV playback test (test_plays_in_mpv) only exists for AnimeFire — other scrapers
use Blogger/session-bound CDN URLs that are not directly playable by mpv.
"""

import subprocess
import threading
from unittest.mock import patch

import pytest

from scrapers.plugins.animefire import AnimeFire
from scrapers.plugins.animesonlinecc import AnimesOnlineCC
from scrapers.plugins.anitube import AniTube
from scrapers.plugins.animesdigital import AnimesDigital
from scrapers.plugins.goyabu import Goyabu

QUERY = "naruto"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_player_src(scraper, episode_url: str) -> list:
    container: list = []
    event = threading.Event()
    try:
        scraper.search_player_src(episode_url, container, event)
    except Exception as e:
        pytest.fail(f"{scraper.__class__.__name__}.search_player_src raised: {e}")
    return container


def _assert_mpv_plays(video_url: str, referrer: str | None = None) -> None:
    """Assert mpv exits 0 within 5 seconds — confirms the URL is directly playable."""
    cmd = ["mpv", "--no-video", "--length=5", "--really-quiet"]
    if referrer:
        cmd.append(f"--referrer={referrer}")
    cmd.append(video_url)
    result = subprocess.run(cmd, timeout=30, capture_output=True)
    assert result.returncode == 0, (
        f"mpv failed (exit {result.returncode}) for URL: {video_url}\n"
        f"stderr: {result.stderr.decode(errors='replace')}"
    )


_SCRAPER_MODULE = {
    "AnimeFire": "animefire",
    "AnimesOnlineCC": "animesonlinecc",
    "AniTube": "anitube",
    "Goyabu": "goyabu",
    "AnimesDigital": "animesdigital",
}


def _capture_episodes(scraper, anime_url: str, anime_name: str) -> list[str]:
    captured_urls: list[str] = []
    module = _SCRAPER_MODULE[scraper.__class__.__name__]

    def _fake_add(*args):
        captured_urls.extend(args[2])

    with patch(f"scrapers.plugins.{module}.rep") as mock_rep:
        mock_rep.add_episode_list.side_effect = _fake_add
        scraper.search_episodes(anime_name, anime_url, None)

    return captured_urls


# ---------------------------------------------------------------------------
# AnimeFire
# ---------------------------------------------------------------------------


class TestAnimeFireRealHTTP:
    def setup_method(self):
        self.scraper = AnimeFire()

    def test_search_anime_returns_results(self):
        results = self.scraper.search_anime(QUERY)
        assert results, "search_anime returned empty list"
        for r in results:
            assert r.title, "result has no title"
            assert r.url.startswith("http"), f"invalid url: {r.url}"

    def test_search_episodes_returns_urls(self):
        results = self.scraper.search_anime(QUERY)
        assert results, "no anime results to test episodes"
        anime = results[0]
        urls = _capture_episodes(self.scraper, anime.url, anime.title)
        assert urls, f"no episode URLs found for {anime.url}"
        assert all(u.startswith("http") for u in urls)

    def test_search_player_src_returns_video_url(self):
        results = self.scraper.search_anime(QUERY)
        assert results
        anime = results[0]
        urls = _capture_episodes(self.scraper, anime.url, anime.title)
        assert urls
        container = _run_player_src(self.scraper, urls[0])
        assert container, f"search_player_src returned empty container for {urls[0]}"
        assert container[0].startswith("http"), f"invalid video url: {container[0]}"

    def test_plays_in_mpv(self):
        results = self.scraper.search_anime(QUERY)
        assert results
        anime = results[0]
        episode_urls = _capture_episodes(self.scraper, anime.url, anime.title)
        assert episode_urls
        container = _run_player_src(self.scraper, episode_urls[0])
        assert container
        _assert_mpv_plays(container[0], referrer=episode_urls[0])


# ---------------------------------------------------------------------------
# AnimesOnlineCC
# ---------------------------------------------------------------------------


class TestAnimesOnlineCCRealHTTP:
    def setup_method(self):
        self.scraper = AnimesOnlineCC()

    def test_search_anime_returns_results(self):
        results = self.scraper.search_anime(QUERY)
        assert results, "search_anime returned empty list"
        for r in results:
            assert r.title
            assert r.url.startswith("http")

    def test_search_episodes_returns_urls(self):
        results = self.scraper.search_anime(QUERY)
        assert results
        anime = results[0]
        urls = _capture_episodes(self.scraper, anime.url, anime.title)
        assert urls, f"no episode URLs for {anime.url}"

    def test_search_player_src_returns_video_url(self):
        results = self.scraper.search_anime(QUERY)
        assert results
        anime = results[0]
        urls = _capture_episodes(self.scraper, anime.url, anime.title)
        assert urls
        container = _run_player_src(self.scraper, urls[0])
        assert container, f"empty container for {urls[0]}"
        assert container[0].startswith("http")


# ---------------------------------------------------------------------------
# AniTube
# ---------------------------------------------------------------------------


class TestAniTubeRealHTTP:
    def setup_method(self):
        self.scraper = AniTube()

    def test_search_anime_returns_results(self):
        results = self.scraper.search_anime(QUERY)
        assert results, "search_anime returned empty list"
        for r in results:
            assert r.title
            assert r.url.startswith("http")

    def test_search_episodes_returns_urls(self):
        results = self.scraper.search_anime(QUERY)
        assert results
        anime = results[0]
        urls = _capture_episodes(self.scraper, anime.url, anime.title)
        assert urls, f"no episode URLs for {anime.url}"

    def test_search_player_src_returns_video_url(self):
        results = self.scraper.search_anime(QUERY)
        assert results
        for anime in results[:3]:
            urls = _capture_episodes(self.scraper, anime.url, anime.title)
            if not urls:
                continue
            container: list = []
            event = threading.Event()
            try:
                self.scraper.search_player_src(urls[0], container, event)
            except Exception as e:
                if "Blogger" in str(e):
                    continue
                pytest.fail(f"AniTube.search_player_src raised: {e}")
            if container:
                assert container[0].startswith("http")
                return
        pytest.skip("All AniTube results use Blogger backend (not externally playable)")


# ---------------------------------------------------------------------------
# Goyabu
# ---------------------------------------------------------------------------


class TestGoyabuRealHTTP:
    def setup_method(self):
        self.scraper = Goyabu()

    def test_search_anime_returns_results(self):
        results = self.scraper.search_anime(QUERY)
        assert results, "search_anime returned empty list"
        for r in results:
            assert r.title
            assert r.url.startswith("http")

    def test_search_episodes_returns_urls(self):
        results = self.scraper.search_anime(QUERY)
        assert results
        anime = results[0]
        urls = _capture_episodes(self.scraper, anime.url, anime.title)
        assert urls, f"no episode URLs for {anime.url}"

    def test_search_player_src_returns_video_url(self):
        results = self.scraper.search_anime(QUERY)
        assert results
        anime = results[0]
        urls = _capture_episodes(self.scraper, anime.url, anime.title)
        assert urls
        container = _run_player_src(self.scraper, urls[0])
        assert container, f"empty container for {urls[0]}"
        assert container[0].startswith("http")


# ---------------------------------------------------------------------------
# AnimesDigital
# ---------------------------------------------------------------------------


class TestAnimesDigitalRealHTTP:
    def setup_method(self):
        self.scraper = AnimesDigital()

    def test_search_anime_returns_results(self):
        results = self.scraper.search_anime(QUERY)
        assert results, "search_anime returned empty list"
        for r in results:
            assert r.title
            assert r.url.startswith("http")

    def _get_episode_urls(self) -> tuple[str, list[str]]:
        results = self.scraper.search_anime(QUERY)
        assert results
        anime = results[0]
        captured_urls: list[str] = []

        def _fake_add(*args):
            captured_urls.extend(args[2])

        with patch("scrapers.plugins.animesdigital.rep") as mock_rep:
            mock_rep.add_episode_list.side_effect = _fake_add
            mock_rep.anime_episodes_urls.get.return_value = []
            self.scraper.search_episodes(anime.title, anime.url, None)

        return anime.url, captured_urls

    def test_search_episodes_returns_urls(self):
        _, urls = self._get_episode_urls()
        assert urls, "no episode URLs found"

    def test_search_player_src_returns_video_url(self):
        _, episode_urls = self._get_episode_urls()
        assert episode_urls
        container = _run_player_src(self.scraper, episode_urls[0])
        assert container, f"empty container for {episode_urls[0]}"
        assert container[0].startswith("http")
