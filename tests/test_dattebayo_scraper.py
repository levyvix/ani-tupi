"""Tests for DattebayoBR scraper plugin."""

from unittest.mock import MagicMock, patch


from scrapers.plugins.dattebayo import DattebayoBR, _extract_episode_number


SEARCH_HTML = """
<html><body>
<div class="aniContainer">
  <div class="ultimosAnimesHomeItem">
    <a href="/animes/naruto">
      <div class="ultimosAnimesHomeItemImg"><img src="https://cdn.example.com/naruto.webp"></div>
      <div class="ultimosAnimesHomeItemInfos">
        <div class="ultimosAnimesHomeItemInfosNome">Naruto</div>
      </div>
    </a>
  </div>
  <div class="ultimosAnimesHomeItem">
    <a href="https://www.dattebayo-br.com/animes/bleach">
      <div class="ultimosAnimesHomeItemImg"><img src="https://cdn.example.com/bleach.webp"></div>
      <div class="ultimosAnimesHomeItemInfos">
        <div class="ultimosAnimesHomeItemInfosNome">Bleach</div>
      </div>
    </a>
  </div>
</div>
</body></html>
"""

SEARCH_EMPTY_HTML = """
<html><body><div class="aniContainer"></div></body></html>
"""

EPISODES_HTML = """
<html><body>
<div class="aniContainer">
  <div class="ultimosEpisodiosHomeItem">
    <a href="/videos/100" title="Naruto ep 1">
      <div class="ultimosEpisodiosHomeItemInfos">
        <div class="ultimosEpisodiosHomeItemInfosNome">Naruto ep 1</div>
        <div class="ultimosEpisodiosHomeItemInfosNum">Episódio 1</div>
      </div>
    </a>
  </div>
  <div class="ultimosEpisodiosHomeItem">
    <a href="/videos/101" title="Naruto ep 2">
      <div class="ultimosEpisodiosHomeItemInfos">
        <div class="ultimosEpisodiosHomeItemInfosNome">Naruto ep 2</div>
        <div class="ultimosEpisodiosHomeItemInfosNum">Episódio 2</div>
      </div>
    </a>
  </div>
  <div class="ultimosEpisodiosHomeItem">
    <a href="/videos/99" title="Naruto ep 3">
      <div class="ultimosEpisodiosHomeItemInfos">
        <div class="ultimosEpisodiosHomeItemInfosNome">Naruto ep 3</div>
        <div class="ultimosEpisodiosHomeItemInfosNum">Episódio 3</div>
      </div>
    </a>
  </div>
</div>
</body></html>
"""

# Episodes returned in reverse order to test sorting
EPISODES_REVERSED_HTML = """
<html><body>
<div class="aniContainer">
  <div class="ultimosEpisodiosHomeItem">
    <a href="/videos/103" title="Naruto ep 3">
      <div class="ultimosEpisodiosHomeItemInfos">
        <div class="ultimosEpisodiosHomeItemInfosNome">Naruto ep 3</div>
      </div>
    </a>
  </div>
  <div class="ultimosEpisodiosHomeItem">
    <a href="/videos/101" title="Naruto ep 1">
      <div class="ultimosEpisodiosHomeItemInfos">
        <div class="ultimosEpisodiosHomeItemInfosNome">Naruto ep 1</div>
      </div>
    </a>
  </div>
  <div class="ultimosEpisodiosHomeItem">
    <a href="/videos/102" title="Naruto ep 2">
      <div class="ultimosEpisodiosHomeItemInfos">
        <div class="ultimosEpisodiosHomeItemInfosNome">Naruto ep 2</div>
      </div>
    </a>
  </div>
</div>
</body></html>
"""

VIDEO_PAGE_META_HTML = """
<html><head>
<meta itemprop="contentURL" content="https://arft.casa2.online/appsd2/544709.mp4" />
</head><body></body></html>
"""

VIDEO_PAGE_JS_HTML = """
<html><body>
<script>
var vid = 'https://r2.example.com/fiphonec/12345.mp4';
</script>
</body></html>
"""

VIDEO_PAGE_NO_URL_HTML = """
<html><body><p>Nothing here</p></body></html>
"""


def _make_response(html: str) -> MagicMock:
    mock = MagicMock()
    mock.text = html
    mock.raise_for_status = MagicMock()
    return mock


class TestExtractEpisodeNumber:
    def test_extracts_episodio_pattern(self):
        assert _extract_episode_number("Naruto Episódio 5") == 5

    def test_extracts_ep_pattern(self):
        assert _extract_episode_number("Naruto ep 12") == 12

    def test_extracts_plain_number(self):
        assert _extract_episode_number("Naruto 7") == 7

    def test_returns_zero_for_no_number(self):
        assert _extract_episode_number("Naruto") == 0


class TestDattebayoSearch:
    def setup_method(self):
        self.scraper = DattebayoBR()

    @patch("scrapers.plugins.dattebayo.rep")
    @patch("scrapers.plugins.dattebayo.requests.get")
    def test_search_returns_results(self, mock_get, mock_rep):
        mock_get.return_value = _make_response(SEARCH_HTML)

        self.scraper.search_anime("naruto")

        assert mock_rep.add_anime.call_count == 2
        calls = [call.args for call in mock_rep.add_anime.call_args_list]
        titles = [c[0] for c in calls]
        assert "Naruto" in titles
        assert "Bleach" in titles

    @patch("scrapers.plugins.dattebayo.rep")
    @patch("scrapers.plugins.dattebayo.requests.get")
    def test_search_relative_urls_are_resolved(self, mock_get, mock_rep):
        mock_get.return_value = _make_response(SEARCH_HTML)

        self.scraper.search_anime("naruto")

        calls = [call.args for call in mock_rep.add_anime.call_args_list]
        urls = [c[1] for c in calls]
        assert all(u.startswith("https://") for u in urls)

    @patch("scrapers.plugins.dattebayo.rep")
    @patch("scrapers.plugins.dattebayo.requests.get")
    def test_search_empty_results(self, mock_get, mock_rep):
        mock_get.return_value = _make_response(SEARCH_EMPTY_HTML)

        self.scraper.search_anime("xyznotexist")

        mock_rep.add_anime.assert_not_called()


class TestDattebayoEpisodes:
    def setup_method(self):
        self.scraper = DattebayoBR()

    @patch("scrapers.plugins.dattebayo.rep")
    @patch("scrapers.plugins.dattebayo.requests.get")
    def test_episodes_listed_correctly(self, mock_get, mock_rep):
        mock_get.return_value = _make_response(EPISODES_HTML)

        self.scraper.search_episodes("Naruto", "https://www.dattebayo-br.com/animes/naruto", None)

        mock_rep.add_episode_list.assert_called_once()
        _, titles, urls, _ = mock_rep.add_episode_list.call_args.args
        assert len(titles) == 3

    @patch("scrapers.plugins.dattebayo.rep")
    @patch("scrapers.plugins.dattebayo.requests.get")
    def test_episodes_sorted_ascending(self, mock_get, mock_rep):
        mock_get.return_value = _make_response(EPISODES_REVERSED_HTML)

        self.scraper.search_episodes("Naruto", "https://www.dattebayo-br.com/animes/naruto", None)

        _, titles, urls, _ = mock_rep.add_episode_list.call_args.args
        numbers = [_extract_episode_number(t) for t in titles]
        assert numbers == sorted(numbers)

    @patch("scrapers.plugins.dattebayo.rep")
    @patch("scrapers.plugins.dattebayo.requests.get")
    def test_episode_urls_resolved(self, mock_get, mock_rep):
        mock_get.return_value = _make_response(EPISODES_HTML)

        self.scraper.search_episodes("Naruto", "https://www.dattebayo-br.com/animes/naruto", None)

        _, _, urls, _ = mock_rep.add_episode_list.call_args.args
        assert all(u.startswith("https://") for u in urls)


def _make_selenium_mock(js_candidates: list[str]) -> MagicMock:
    """Create a mock SeleniumWebDriver context manager returning given JS candidates."""
    mock_driver = MagicMock()
    mock_driver.fetch.return_value = MagicMock()
    mock_driver.driver.execute_script.return_value = js_candidates
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_driver)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    return mock_ctx


def _make_requests_get_mock(status_code: int) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    return mock_resp


class TestDattebayoPlayerSrc:
    def setup_method(self):
        self.scraper = DattebayoBR()

    @patch("scrapers.plugins.dattebayo.requests.get")
    @patch("scrapers.plugins.dattebayo.SeleniumWebDriver")
    def test_extracts_url_via_meta_tag(self, mock_selenium_cls, mock_get):
        video_url = "https://r2.example.com/fful/544709.mp4?sig=abc"
        mock_selenium_cls.return_value = _make_selenium_mock([video_url])
        mock_get.return_value = _make_requests_get_mock(206)
        container = []
        event = MagicMock()
        event.is_set.return_value = False

        self.scraper.search_player_src("https://www.dattebayo-br.com/videos/1", container, event)

        assert len(container) == 1
        assert "544709.mp4" in container[0]
        event.set.assert_called_once()

    @patch("scrapers.plugins.dattebayo.requests.get")
    @patch("scrapers.plugins.dattebayo.SeleniumWebDriver")
    def test_fallback_hd_when_fullhd_404(self, mock_selenium_cls, mock_get):
        fullhd_url = "https://r2.example.com/fful/12345.mp4?sig=abc"
        hd_url = "https://r2.example.com/f222/12345.mp4?sig=abc"
        mock_selenium_cls.return_value = _make_selenium_mock([fullhd_url, hd_url])

        def side_effect(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200 if "f222" in url else 404
            return resp

        mock_get.side_effect = side_effect
        container = []
        event = MagicMock()
        event.is_set.return_value = False

        self.scraper.search_player_src("https://www.dattebayo-br.com/videos/1", container, event)

        assert len(container) == 1
        assert "f222" in container[0]
        event.set.assert_called_once()

    @patch("scrapers.plugins.dattebayo.requests.get")
    @patch("scrapers.plugins.dattebayo.SeleniumWebDriver")
    def test_no_url_found_does_not_crash(self, mock_selenium_cls, mock_get):
        mock_selenium_cls.return_value = _make_selenium_mock([])
        container = []
        event = MagicMock()
        event.is_set.return_value = False

        self.scraper.search_player_src("https://www.dattebayo-br.com/videos/1", container, event)

        assert len(container) == 0
        event.set.assert_not_called()
