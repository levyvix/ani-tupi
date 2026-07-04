"""Tests for Goyabu scraper."""

import pytest
from unittest.mock import MagicMock, patch

from scrapers.plugins.goyabu import Goyabu


SEARCH_HTML = """
<html><body>
  <article class="boxAN">
    <a href="https://goyabu.io/anime/mao/">link</a>
    <div class="title">Mao</div>
  </article>
</body></html>
"""

EPISODES_JS = """
<html><body>
<script>
var allEpisodes = [
  {"episodio": "1", "episode_name": "Piloto", "link": "/ep/mao-1/"},
  {"episodio": "2", "episode_name": "", "link": "/ep/mao-2/"}
];
</script>
</body></html>
"""

PLAYER_HTML = """
<html><body>
<script>
var playersData = [{"url": "https://www.blogger.com/video.g?token=XYZ789"}];
</script>
</body></html>
"""


def _html_response(html: str) -> MagicMock:
    response = MagicMock()
    response.text = html
    response.raise_for_status = MagicMock()
    return response


def _event(is_set: bool = False) -> MagicMock:
    event = MagicMock()
    event.is_set.return_value = is_set
    return event


class TestGoyabuScraper:
    def setup_method(self):
        self.scraper = Goyabu()

    @patch("scrapers.plugins.goyabu.httpx.get")
    def test_search_anime_returns_results(self, mock_get):
        mock_get.return_value = _html_response(SEARCH_HTML)

        results = self.scraper.search_anime("mao")

        assert len(results) == 1
        assert results[0].title == "Mao"
        assert results[0].url == "https://goyabu.io/anime/mao/"

    @patch("scrapers.plugins.goyabu.httpx.get")
    def test_search_anime_empty_returns_empty_list(self, mock_get):
        mock_get.return_value = _html_response("<html></html>")

        results = self.scraper.search_anime("nothing")

        assert results == []

    @patch("scrapers.plugins.goyabu.rep")
    @patch("scrapers.plugins.goyabu.httpx.get")
    def test_search_episodes_adds_episode_list(self, mock_get, mock_rep):
        mock_get.return_value = _html_response(EPISODES_JS)

        self.scraper.search_episodes("Mao", "https://goyabu.io/anime/mao/", None)

        mock_rep.add_episode_list.assert_called_once()
        anime, _, urls, source = mock_rep.add_episode_list.call_args[0]
        assert anime == "Mao"
        assert source == "goyabu"
        assert len(urls) == 2

    @patch("scrapers.plugins.goyabu.rep")
    @patch("scrapers.plugins.goyabu.httpx.get")
    def test_search_episodes_no_episodes_does_not_call_rep(self, mock_get, mock_rep):
        mock_get.return_value = _html_response("<html></html>")

        self.scraper.search_episodes("Mao", "https://goyabu.io/anime/mao/", None)

        mock_rep.add_episode_list.assert_not_called()

    @patch("scrapers.plugins.goyabu.resolve_blogger_token")
    @patch("scrapers.plugins.goyabu.httpx.get")
    def test_search_player_src_extracts_video_url(self, mock_get, mock_resolve):
        mock_get.return_value = _html_response(PLAYER_HTML)
        mock_resolve.return_value = "https://video.example.com/mao.mp4"
        container = []
        event = _event()

        self.scraper.search_player_src("https://goyabu.io/ep/mao-1/", container, event)

        assert container == ["https://video.example.com/mao.mp4"]
        mock_resolve.assert_called_once_with("XYZ789")

    @patch("scrapers.plugins.goyabu.httpx.get")
    def test_search_player_src_no_source_raises(self, mock_get):
        mock_get.return_value = _html_response("<html></html>")
        container = []
        event = _event()

        with pytest.raises(Exception):
            self.scraper.search_player_src("https://goyabu.io/ep/mao-1/", container, event)
