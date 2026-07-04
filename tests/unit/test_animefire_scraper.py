"""Tests for AnimeFire scraper."""

import json
from unittest.mock import MagicMock, call, patch
from bs4 import BeautifulSoup

from scrapers.plugins.animefire import AnimeFire


SEARCH_HTML = """
<html><body>
  <div class="col-6.col-sm-4.col-md-3.col-lg-2.mb-1.minWDanime.divCardUltimosEps">
    <div class="col-6 col-sm-4 col-md-3 col-lg-2 mb-1 minWDanime divCardUltimosEps">
      <article><a href="https://animefire.plus/animes/mao">link</a></article>
    </div>
  </div>
  <h3 class="animeTitle">Mao</h3>
</body></html>
"""

EPISODES_HTML = """
<html><body>
  <a class="lEp" href="https://animefire.plus/animes/mao/1">ep1</a>
  <a class="lEp" href="https://animefire.plus/animes/mao/2">ep2</a>
</body></html>
"""

EPISODE_PAGE_HTML = """
<html><body>
  <video id="my-video" data-video-src="https://animefire.io/video/mao/9?tempsubs=0&1780178669"></video>
</body></html>
"""

VIDEO_SRC_HTML = """
<html><body>
  <video src="https://cdn.example.com/mao/9.mp4"></video>
</body></html>
"""

IFRAME_HTML = """
<html><body>
  <iframe src="https://embed.example.com/mao/9"></iframe>
</body></html>
"""


VIDEO_JSON = {
    "data": [
        {
            "src": "https://lightspeedst.net/s8/mp4/mao/sd/9.mp4?token=sd&expires=1&ip=1",
            "label": "360p",
        },
        {
            "src": "https://lightspeedst.net/s8/mp4/mao/hd/9.mp4?token=hd&expires=1&ip=1",
            "label": "720p",
        },
    ],
    "response": {"status": "200", "text": "OK"},
}


class _Response:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        return json.loads(self.text)


def _event():
    event = MagicMock()
    event.is_set.return_value = False
    return event


class TestAnimeFireScraper:
    def setup_method(self):
        self.scraper = AnimeFire()

    @patch("scrapers.plugins.animefire.httpx.get")
    def test_search_player_src_uses_json_endpoint(self, mock_get):
        # First call: episode page HTML; second call: video JSON API
        mock_get.side_effect = [
            _Response(EPISODE_PAGE_HTML),
            _Response(json.dumps(VIDEO_JSON)),
        ]

        container = []
        event = _event()

        self.scraper.search_player_src("https://animefire.io/animes/mao/9", container, event)

        assert container == ["https://lightspeedst.net/s8/mp4/mao/hd/9.mp4?token=hd&expires=1"]
        assert mock_get.call_args_list == [
            call("https://animefire.io/animes/mao/9", timeout=20, follow_redirects=True),
            call(
                "https://animefire.io/video/mao/9?tempsubs=0&1780178669",
                timeout=20,
                follow_redirects=True,
            ),
        ]

    @patch("scrapers.plugins.animefire.SeleniumWebDriver")
    def test_search_anime_returns_results(self, mock_selenium):
        soup = BeautifulSoup(SEARCH_HTML, "html.parser")
        mock_driver = MagicMock()
        mock_driver.__enter__ = MagicMock(return_value=mock_driver)
        mock_driver.__exit__ = MagicMock(return_value=False)
        mock_driver.fetch.return_value = soup
        mock_selenium.return_value = mock_driver

        results = self.scraper.search_anime("mao")

        assert len(results) == 1
        assert results[0].title == "Mao"
        assert results[0].url == "https://animefire.plus/animes/mao"

    @patch("scrapers.plugins.animefire.SeleniumWebDriver")
    def test_search_anime_returns_empty_without_cards(self, mock_selenium):
        soup = BeautifulSoup("<html></html>", "html.parser")
        mock_driver = MagicMock()
        mock_driver.__enter__ = MagicMock(return_value=mock_driver)
        mock_driver.__exit__ = MagicMock(return_value=False)
        mock_driver.fetch.return_value = soup
        mock_selenium.return_value = mock_driver

        results = self.scraper.search_anime("nothing")

        assert results == []

    @patch("scrapers.plugins.animefire.rep")
    @patch("scrapers.plugins.animefire.httpx.get")
    def test_search_episodes_adds_episode_list(self, mock_get, mock_rep):
        mock_get.return_value = _Response(EPISODES_HTML)

        self.scraper.search_episodes("Mao", "https://animefire.plus/animes/mao", None)

        mock_rep.add_episode_list.assert_called_once()
        anime, _, urls, source = mock_rep.add_episode_list.call_args[0]
        assert anime == "Mao"
        assert source == "animefire"
        assert urls == [
            "https://animefire.plus/animes/mao/1",
            "https://animefire.plus/animes/mao/2",
        ]

    @patch("scrapers.plugins.animefire.rep")
    @patch("scrapers.plugins.animefire.httpx.get")
    def test_search_episodes_empty_page_does_not_call_rep(self, mock_get, mock_rep):
        mock_get.return_value = _Response("<html></html>")

        self.scraper.search_episodes("Mao", "https://animefire.plus/animes/mao", None)

        mock_rep.add_episode_list.assert_not_called()

    @patch("scrapers.plugins.animefire.httpx.get")
    def test_search_player_src_fallbacks_to_video_src(self, mock_get):
        mock_get.return_value = _Response(VIDEO_SRC_HTML)
        container = []
        event = _event()

        self.scraper.search_player_src("https://animefire.plus/animes/mao/9", container, event)

        assert container == ["https://cdn.example.com/mao/9.mp4"]

    @patch("scrapers.plugins.animefire.httpx.get")
    def test_search_player_src_fallbacks_to_iframe(self, mock_get):
        mock_get.return_value = _Response(IFRAME_HTML)
        container = []
        event = _event()

        self.scraper.search_player_src("https://animefire.plus/animes/mao/9", container, event)

        assert container == ["https://embed.example.com/mao/9"]
