"""Tests for AnimesDigital scraper fallback logging behavior."""

import logging
from unittest.mock import MagicMock, patch

import httpx

from scrapers.plugins.animesdigital import AnimesDigital


def _http_error_response() -> MagicMock:
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.HTTPError(
        "500 Server Error: Internal Server Error for url: https://animesdigital.org/home"
    )
    return response


def _html_response(html: str) -> MagicMock:
    response = MagicMock()
    response.text = html
    response.raise_for_status = MagicMock()
    return response


SERIES_PAGE_HTML = """
<html><body>
  <div class="itens_ep">
    <div class="item_ep b_flex">
      <a href="https://animesdigital.org/video/a/135463/" class="b_flex">
        <div class="dados b_flex b_align_center b_space_between">
          <div class="left">
            <div class="title_anime">Tadaima Ojamasaremasu! Episódio 01</div>
          </div>
        </div>
      </a>
    </div>
    <div class="item_ep b_flex">
      <a href="https://animesdigital.org/video/a/135726/" class="b_flex">
        <div class="dados b_flex b_align_center b_space_between">
          <div class="left">
            <div class="title_anime">Tadaima Ojamasaremasu! Episódio 02</div>
          </div>
        </div>
      </a>
    </div>
    <div class="item_ep b_flex">
      <a href="https://animesdigital.org/video/a/999999/" class="b_flex">
        <div class="dados b_flex b_align_center b_space_between">
          <div class="left">
            <div class="title_anime">Tadaima Ojamasaremasu! Episódio 13.5</div>
          </div>
        </div>
      </a>
    </div>
  </div>
</body></html>
"""


class TestAnimesDigitalFallbackLogging:
    def setup_method(self):
        self.scraper = AnimesDigital()

    @patch("scrapers.plugins.animesdigital.httpx.get")
    def test_homepage_http_error_returns_empty_without_warning(self, mock_get, caplog):
        mock_get.return_value = _http_error_response()

        with caplog.at_level(logging.WARNING):
            result = self.scraper.search_homepage_incremental("Liar Game")

        assert result == []
        assert "Error searching AnimesDigital homepage" not in caplog.text

    @patch.object(AnimesDigital, "search_homepage_incremental", return_value=[])
    @patch.object(AnimesDigital, "_scrape_series_page")
    @patch("scrapers.plugins.animesdigital.rep")
    def test_search_episodes_uses_silent_fallback_logs(
        self, mock_rep, mock_scrape_series_page, mock_homepage_search, caplog
    ):
        mock_rep.anime_episodes_urls.get.return_value = []

        with caplog.at_level(logging.WARNING):
            self.scraper.search_episodes(
                "Liar Game", "https://animesdigital.org/anime/a/liar-game", None
            )

        assert "No episodes found for 'Liar Game' in series page scraping" not in caplog.text
        assert (
            "No episodes found for 'Liar Game' even with DynamicFetcher scraping" not in caplog.text
        )
        mock_scrape_series_page.assert_called_once()
        mock_homepage_search.assert_called_once_with("Liar Game", audio_type="legendado")

    @patch("scrapers.plugins.animesdigital.rep")
    @patch("scrapers.plugins.animesdigital.httpx.get")
    def test_scrape_series_page_uses_static_html_and_appends_odr(self, mock_get, mock_rep):
        mock_get.return_value = _html_response(SERIES_PAGE_HTML)

        self.scraper._scrape_series_page(
            "Tadaima Ojamasaremasu!",
            "https://animesdigital.org/anime/a/tadaima-ojamasaremasu-todos-episodios",
        )

        assert mock_get.call_count == 1
        assert (
            mock_get.call_args.args[0]
            == "https://animesdigital.org/anime/a/tadaima-ojamasaremasu-todos-episodios?odr=1"
        )
        mock_rep.add_episode_list.assert_called_once_with(
            "Tadaima Ojamasaremasu!",
            [
                "Tadaima Ojamasaremasu! Episódio 01",
                "Tadaima Ojamasaremasu! Episódio 02",
            ],
            [
                "https://animesdigital.org/video/a/135463/",
                "https://animesdigital.org/video/a/135726/",
            ],
            "animesdigital",
        )

    @patch("scrapers.plugins.animesdigital.rep")
    @patch("scrapers.plugins.animesdigital.httpx.get")
    def test_scrape_series_page_preserves_existing_query_string(self, mock_get, mock_rep):
        mock_get.return_value = _html_response("<html></html>")

        self.scraper._scrape_series_page(
            "Tadaima Ojamasaremasu!",
            "https://animesdigital.org/anime/a/tadaima-ojamasaremasu-todos-episodios?foo=bar",
        )

        assert (
            mock_get.call_args.args[0]
            == "https://animesdigital.org/anime/a/tadaima-ojamasaremasu-todos-episodios?foo=bar&odr=1"
        )
        mock_rep.add_episode_list.assert_not_called()


IFRAME_PLAYER_HTML = """
<html><body>
  <iframe src="https://api.anivideo.net/player/embed/abc123"></iframe>
</body></html>
"""


class TestAnimesDigitalPlayerSrc:
    def setup_method(self):
        self.scraper = AnimesDigital()

    @patch("scrapers.plugins.animesdigital.httpx.get")
    def test_search_player_src_extracts_iframe_url(self, mock_get):
        mock_get.return_value = _html_response(IFRAME_PLAYER_HTML)
        container = []
        event = MagicMock()
        event.is_set.return_value = False

        self.scraper.search_player_src(
            "https://animesdigital.org/video/a/135463/", container, event
        )

        assert container == ["https://api.anivideo.net/player/embed/abc123"]
