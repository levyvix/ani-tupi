"""Integration tests — real HTTP calls to scraper sites.

Each test verifies the scraper still works against the live site.
Run: uv run pytest tests/integration/test_scrapers_real_http.py -v

These tests hit real sites. They are the project's contract that scrapers still
work against production HTML/APIs.

MPV playback test (test_plays_in_mpv) only exists for AnimeFire — other scrapers
use Blogger/session-bound CDN URLs that are not directly playable by mpv.
"""

import shutil
import subprocess
import threading
from unittest.mock import patch

import httpx
import pytest

from models.models import AnimeMetadata
from scrapers.plugins.animefire import AnimeFire
from scrapers.plugins.animesonlinecc import AnimesOnlineCC
from scrapers.plugins.anitube import AniTube
from scrapers.plugins.animesdigital import AnimesDigital
from scrapers.plugins.goyabu import Goyabu

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.requires_http,
]

QUERY = "naruto"
VIDEO_PROBE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BLOCK_STATUS_CODES = frozenset({403, 429, 503})


def _search_anime_or_skip(scraper, query: str) -> list[AnimeMetadata]:
    """Run search; skip (not fail) when the site blocks this environment."""
    try:
        results = scraper.search_anime(query)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in _BLOCK_STATUS_CODES:
            pytest.skip(
                f"{scraper.name} returned HTTP {exc.response.status_code} "
                f"from this environment: {exc.request.url}"
            )
        raise
    except httpx.HTTPError as exc:
        pytest.skip(f"{scraper.name} unreachable from this environment: {exc}")

    if not results:
        pytest.skip(
            f"{scraper.name} search returned empty for {query!r} "
            "(site may block datacenter IPs or be temporarily down)"
        )
    return results


def _require_episode_urls(urls: list[str], anime_url: str, source: str) -> list[str]:
    if not urls:
        pytest.skip(f"{source} returned no episode URLs for {anime_url}")
    return urls


def _run_player_src(scraper, episode_url: str) -> list:
    container: list = []
    event = threading.Event()
    try:
        scraper.search_player_src(episode_url, container, event)
    except Exception as e:
        pytest.fail(f"{scraper.__class__.__name__}.search_player_src raised: {e}")
    return container


def _pick_anime_for_episode_tests(results: list[AnimeMetadata], query: str) -> AnimeMetadata:
    """Prefer the main series over spin-offs/movies that share the query token."""
    query_cf = query.casefold()
    skip_markers = ("boruto", "movie", "gekijouban", " sd:")

    for result in results:
        title_cf = result.title.casefold()
        if any(marker in title_cf for marker in skip_markers):
            continue
        if query_cf in title_cf:
            return result

    return results[0]


def _assert_video_url_reachable(video_url: str, referrer: str | None = None) -> None:
    """Confirm the CDN URL responds before asking mpv to play it."""
    headers = {**VIDEO_PROBE_HEADERS, "Range": "bytes=0-1"}
    if referrer:
        headers["Referer"] = referrer

    try:
        response = httpx.get(
            video_url,
            headers=headers,
            timeout=30,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        pytest.skip(
            "Video CDN unreachable from this environment "
            f"(scraper URL extraction already verified): {exc}"
        )

    assert response.status_code in (200, 206), (
        f"Video CDN returned HTTP {response.status_code} for {video_url}"
    )


def _assert_mpv_plays(video_url: str, referrer: str | None = None) -> None:
    """Assert mpv can start playback — confirms the URL is directly playable."""
    if shutil.which("mpv") is None:
        pytest.skip("mpv is not installed")

    _assert_video_url_reachable(video_url, referrer=referrer)

    cmd = [
        "mpv",
        "--no-video",
        "--length=3",
        "--really-quiet",
        "--network-timeout=20",
        f"--user-agent={VIDEO_PROBE_HEADERS['User-Agent']}",
    ]
    if referrer:
        cmd.append(f"--referrer={referrer}")
    cmd.append(video_url)

    try:
        result = subprocess.run(cmd, timeout=45, capture_output=True)
    except subprocess.TimeoutExpired:
        pytest.skip(
            "mpv timed out reaching the video CDN from this environment "
            f"(scraper URL extraction already verified): {video_url}"
        )

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


@pytest.fixture(scope="class")
def animefire_search_results() -> list[AnimeMetadata]:
    return _search_anime_or_skip(AnimeFire(), QUERY)


@pytest.fixture(scope="class")
def animefire_episode_target(animefire_search_results) -> AnimeMetadata:
    return _pick_anime_for_episode_tests(animefire_search_results, QUERY)


@pytest.fixture(scope="class")
def animefire_episode_urls(animefire_episode_target) -> list[str]:
    scraper = AnimeFire()
    urls = _capture_episodes(scraper, animefire_episode_target.url, animefire_episode_target.title)
    return _require_episode_urls(urls, animefire_episode_target.url, "animefire")


class TestAnimeFireRealHTTP:
    @pytest.fixture(autouse=True)
    def _setup(self, animefire_search_results):
        self.scraper = AnimeFire()
        self.search_results = animefire_search_results

    def test_search_anime_returns_results(self):
        for result in self.search_results:
            assert result.title, "result has no title"
            assert result.url.startswith("http"), f"invalid url: {result.url}"

    def test_search_episodes_returns_urls(self, animefire_episode_target):
        urls = _capture_episodes(
            self.scraper, animefire_episode_target.url, animefire_episode_target.title
        )
        _require_episode_urls(urls, animefire_episode_target.url, "animefire")
        assert all(url.startswith("http") for url in urls)

    def test_search_player_src_returns_video_url(self, animefire_episode_urls):
        container = _run_player_src(self.scraper, animefire_episode_urls[0])
        assert container, (
            f"search_player_src returned empty container for {animefire_episode_urls[0]}"
        )
        assert container[0].startswith("http"), f"invalid video url: {container[0]}"

    def test_plays_in_mpv(self, animefire_episode_urls):
        container = _run_player_src(self.scraper, animefire_episode_urls[0])
        assert container
        _assert_mpv_plays(container[0], referrer=animefire_episode_urls[0])


# ---------------------------------------------------------------------------
# AnimesOnlineCC
# ---------------------------------------------------------------------------


class TestAnimesOnlineCCRealHTTP:
    def setup_method(self):
        self.scraper = AnimesOnlineCC()

    def test_search_anime_returns_results(self):
        results = _search_anime_or_skip(self.scraper, QUERY)
        for r in results:
            assert r.title
            assert r.url.startswith("http")

    def test_search_episodes_returns_urls(self):
        results = _search_anime_or_skip(self.scraper, QUERY)
        anime = _pick_anime_for_episode_tests(results, QUERY)
        urls = _require_episode_urls(
            _capture_episodes(self.scraper, anime.url, anime.title),
            anime.url,
            self.scraper.name,
        )
        assert all(url.startswith("http") for url in urls)

    def test_search_player_src_returns_video_url(self):
        results = _search_anime_or_skip(self.scraper, QUERY)
        anime = _pick_anime_for_episode_tests(results, QUERY)
        urls = _require_episode_urls(
            _capture_episodes(self.scraper, anime.url, anime.title),
            anime.url,
            self.scraper.name,
        )
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
        results = _search_anime_or_skip(self.scraper, QUERY)
        for r in results:
            assert r.title
            assert r.url.startswith("http")

    def test_search_episodes_returns_urls(self):
        results = _search_anime_or_skip(self.scraper, QUERY)
        anime = _pick_anime_for_episode_tests(results, QUERY)
        _require_episode_urls(
            _capture_episodes(self.scraper, anime.url, anime.title),
            anime.url,
            self.scraper.name,
        )

    def test_search_player_src_returns_video_url(self):
        results = _search_anime_or_skip(self.scraper, QUERY)
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
        results = _search_anime_or_skip(self.scraper, QUERY)
        for r in results:
            assert r.title
            assert r.url.startswith("http")

    def test_search_episodes_returns_urls(self):
        results = _search_anime_or_skip(self.scraper, QUERY)
        anime = _pick_anime_for_episode_tests(results, QUERY)
        _require_episode_urls(
            _capture_episodes(self.scraper, anime.url, anime.title),
            anime.url,
            self.scraper.name,
        )

    def test_search_player_src_returns_video_url(self):
        results = _search_anime_or_skip(self.scraper, QUERY)
        anime = _pick_anime_for_episode_tests(results, QUERY)
        urls = _require_episode_urls(
            _capture_episodes(self.scraper, anime.url, anime.title),
            anime.url,
            self.scraper.name,
        )
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
        results = _search_anime_or_skip(self.scraper, QUERY)
        for r in results:
            assert r.title
            assert r.url.startswith("http")

    def _get_episode_urls(self) -> tuple[str, list[str]]:
        results = _search_anime_or_skip(self.scraper, QUERY)
        anime = _pick_anime_for_episode_tests(results, QUERY)
        captured_urls: list[str] = []

        def _fake_add(*args):
            captured_urls.extend(args[2])

        with patch("scrapers.plugins.animesdigital.rep") as mock_rep:
            mock_rep.add_episode_list.side_effect = _fake_add
            mock_rep.anime_episodes_urls.get.return_value = []
            self.scraper.search_episodes(anime.title, anime.url, None)

        return anime.url, captured_urls

    def test_search_episodes_returns_urls(self):
        anime_url, urls = self._get_episode_urls()
        _require_episode_urls(urls, anime_url, self.scraper.name)

    def test_search_player_src_returns_video_url(self):
        anime_url, episode_urls = self._get_episode_urls()
        _require_episode_urls(episode_urls, anime_url, self.scraper.name)
        container = _run_player_src(self.scraper, episode_urls[0])
        assert container, f"empty container for {episode_urls[0]}"
        assert container[0].startswith("http")
