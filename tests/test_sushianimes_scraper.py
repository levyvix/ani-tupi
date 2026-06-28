"""Tests for Sushi Animes scraper plugin."""

import httpx
from unittest.mock import MagicMock, patch

from scrapers.plugins.sushianimes import (
    HEADERS,
    SushiAnimes,
    _extract_player_url,
    _extract_season_number,
)


SEARCH_HTML = """
<html><body>
  <div id="animes">
    <div class="list-movie">
      <a href="https://sushianimes.com.br/anime/dorohedoro-dublado-963" class="list-title">
        Dorohedoro (Dublado)
      </a>
    </div>
  </div>
</body></html>
"""


ANIME_PAGE_HTML = """
<html><body>
  <div class="episodes tab-content">
    <div class="tab-pane" id="season-1">
      <a href="/anime/dorohedoro-dublado-963-1-season-1-episode" title="1º Episódio">
        <div class="episode">
          <div class="media media-episode"></div>
        </div>
        <div class="episode">
          1º Episódio
          <div class="name" data-max-length="30">CAIMAN</div>
        </div>
      </a>
    </div>
    <div class="tab-pane" id="season-2">
      <a href="/anime/dorohedoro-dublado-963-2-season-1-episode" title="1º Episódio">
        <div class="episode">
          <div class="media media-episode"></div>
        </div>
        <div class="episode">
          1º Episódio
          <div class="name" data-max-length="30">USEMOS NOSSOS RECURSOS COM CAUTELA</div>
        </div>
      </a>
      <a href="/anime/dorohedoro-dublado-963-2-season-2-episode" title="2º Episódio">
        <div class="episode">
          <div class="media media-episode"></div>
        </div>
        <div class="episode">
          2º Episódio
          <div class="name" data-max-length="30">RELAÇÕES MARITAIS</div>
        </div>
      </a>
    </div>
  </div>
</body></html>
"""


EPISODE_PAGE_HTML = """
<html><body>
  <a class="dropdown-toggle btn-service selected" data-embed="24139">
    Opções: <span>CAIMAN</span>
  </a>
</body></html>
"""


EPISODE_PAGE_HTML_DATA_ID = """
<html><body>
  <div class="embed-play">
    <div class="play-btn" data-id="24139"></div>
  </div>
</body></html>
"""


EMBED_RESPONSE = (
    'var playerEmbed = "https:\\/\\/cdn-s01.pixel-sus-4k-image.com\\/stream\\/d\\/dorohedoro-dublado\\/01.mp4";'
    'var playerName = "CAIMAN";'
)


def _response(html: str) -> MagicMock:
    mock = MagicMock()
    mock.text = html
    mock.raise_for_status = MagicMock()
    return mock


def _event() -> MagicMock:
    event = MagicMock()
    event.is_set.return_value = False
    return event


class TestSeasonParsing:
    def test_extract_season_number(self):
        assert _extract_season_number("season-2") == 2
        assert _extract_season_number("Temporada 3") == 3


class TestSushiAnimesScraper:
    def setup_method(self):
        self.scraper = SushiAnimes()

    @patch("scrapers.plugins.sushianimes.httpx.get")
    def test_search_anime_creates_season_results(self, mock_get):
        mock_get.side_effect = [_response(SEARCH_HTML), _response(ANIME_PAGE_HTML)]

        results = self.scraper.search_anime("dorohedoro")

        assert len(results) == 2
        assert results[0].title == "Dorohedoro - Dublado"
        assert results[0].source == "sushianimes"
        assert results[0].params == {"season": 1}
        assert results[1].title == "Dorohedoro 2 - Dublado"
        assert results[1].params == {"season": 2}

    @patch("scrapers.plugins.sushianimes.rep")
    @patch("scrapers.plugins.sushianimes.httpx.get")
    def test_search_episodes_uses_requested_season(self, mock_get, mock_rep):
        mock_get.return_value = _response(ANIME_PAGE_HTML)

        self.scraper.search_episodes(
            "Dorohedoro 2 - Dublado",
            "https://sushianimes.com.br/anime/dorohedoro-dublado-963",
            {"season": 2},
        )

        mock_rep.add_episode_list.assert_called_once()
        _, titles, urls, source = mock_rep.add_episode_list.call_args.args
        season = mock_rep.add_episode_list.call_args.kwargs["season"]
        assert source == "sushianimes"
        assert season == 2
        assert titles == [
            "1º Episódio USEMOS NOSSOS RECURSOS COM CAUTELA",
            "2º Episódio RELAÇÕES MARITAIS",
        ]
        assert urls[0].startswith("https://sushianimes.com.br/")
        assert mock_get.call_args.kwargs["headers"] == HEADERS

    @patch("scrapers.plugins.sushianimes.rep")
    @patch("scrapers.plugins.sushianimes.httpx.get")
    def test_search_episodes_swallows_http_errors(self, mock_get, mock_rep):
        response = MagicMock()
        response.raise_for_status.side_effect = httpx.HTTPError("403 Client Error")
        mock_get.return_value = response

        self.scraper.search_episodes(
            "Dorohedoro 2 - Dublado",
            "https://sushianimes.com.br/anime/dorohedoro-dublado-963",
            {"season": 2},
        )

        mock_rep.add_episode_list.assert_not_called()

    @patch("scrapers.plugins.sushianimes.httpx.post")
    @patch("scrapers.plugins.sushianimes.httpx.get")
    def test_search_player_src_extracts_player_url(self, mock_get, mock_post):
        mock_get.return_value = _response(EPISODE_PAGE_HTML)
        mock_post.return_value = _response(EMBED_RESPONSE)
        container = []
        event = _event()

        self.scraper.search_player_src(
            "https://sushianimes.com.br/anime/dorohedoro-dublado-963-1-season-1-episode",
            container,
            event,
        )

        assert container == [
            "https://cdn-s01.pixel-sus-4k-image.com/stream/d/dorohedoro-dublado/01.mp4"
        ]
        event.set.assert_called_once()

        post_headers = mock_post.call_args.kwargs["headers"]
        assert post_headers["X-Requested-With"] == "XMLHttpRequest"
        assert post_headers["Referer"].endswith("-1-season-1-episode")

    @patch("scrapers.plugins.sushianimes.httpx.post")
    @patch("scrapers.plugins.sushianimes.httpx.get")
    def test_search_player_src_fallbacks_to_data_id(self, mock_get, mock_post):
        mock_get.return_value = _response(EPISODE_PAGE_HTML_DATA_ID)
        mock_post.return_value = _response(EMBED_RESPONSE)
        container = []
        event = _event()

        self.scraper.search_player_src(
            "https://sushianimes.com.br/anime/dorohedoro-dublado-963-1-season-1-episode",
            container,
            event,
        )

        assert container == [
            "https://cdn-s01.pixel-sus-4k-image.com/stream/d/dorohedoro-dublado/01.mp4"
        ]


class TestPlayerUrlExtraction:
    def test_extract_player_url_from_player_embed_single_quote(self):
        embed_html = "var playerEmbed = 'https:\\/\\/cdn.example.com\\/stream\\/x\\/01.mp4';"
        assert _extract_player_url(embed_html) == "https://cdn.example.com/stream/x/01.mp4"

    def test_extract_player_url_from_plain_stream_url(self):
        embed_html = '<script>const p="https://cdn.example.com/stream/y/my-anime/07.mp4/index.m3u8";</script>'
        assert (
            _extract_player_url(embed_html)
            == "https://cdn.example.com/stream/y/my-anime/07.mp4/index.m3u8"
        )
