"""Tests for AnRoll scraper episode list extraction."""

from unittest.mock import MagicMock, patch


from scrapers.plugins.anroll import AnRoll

ANIME_PAGE_HTML = """
<html><body>
  <a href="https://anroll.io/53289/">Primeiro Episódio</a>
  <a href="https://anroll.io/60098/">Último Episódio</a>
</body></html>
"""

SIDEBAR_HTML = """
<html><body>
  <div class="ep-list-box">
    <a href="https://anroll.io/53289/">01 Ep</a>
    <a href="https://anroll.io/53633/">02 Ep</a>
    <a href="https://anroll.io/60098/">12 Ep</a>
  </div>
</body></html>
"""


def _html_response(html: str) -> MagicMock:
    response = MagicMock()
    response.text = html
    response.raise_for_status = MagicMock()
    return response


class TestAnRollEpisodes:
    def setup_method(self):
        self.scraper = AnRoll()

    @patch("scrapers.plugins.anroll.rep")
    @patch("scrapers.plugins.anroll.httpx.get")
    def test_search_episodes_uses_sidebar_not_id_range(self, mock_get, mock_rep):
        mock_get.side_effect = [
            _html_response(ANIME_PAGE_HTML),
            _html_response(SIDEBAR_HTML),
        ]

        self.scraper.search_episodes(
            "Aishiteru Game wo Owarasetai",
            "https://anroll.io/anime/aishiteru-game-wo-owarasetai/",
            None,
        )

        assert mock_get.call_count == 2
        mock_rep.add_episode_list.assert_called_once()
        anime, titles, urls, source = mock_rep.add_episode_list.call_args[0]
        assert anime == "Aishiteru Game wo Owarasetai"
        assert source == "anroll"
        assert len(urls) == 3
        assert urls[0] == "https://anroll.io/53289/"
        assert urls[-1] == "https://anroll.io/60098/"

    @patch("scrapers.plugins.anroll.httpx.get")
    def test_episodes_from_sidebar_parses_ep_list_box(self, mock_get):
        mock_get.return_value = _html_response(SIDEBAR_HTML)

        titles, urls = self.scraper._episodes_from_sidebar("https://anroll.io/53289/")

        assert len(titles) == 3
        assert titles[0] == "Ep.001"
        assert urls[1] == "https://anroll.io/53633/"

    @patch("scrapers.plugins.anroll.httpx.get")
    def test_episodes_from_sidebar_returns_empty_without_box(self, mock_get):
        mock_get.return_value = _html_response("<html></html>")

        titles, urls = self.scraper._episodes_from_sidebar("https://anroll.io/53289/")

        assert titles == []
        assert urls == []
