"""Tests for Dattebayo scraper plugin."""

from unittest.mock import MagicMock, patch

import pytest

from scrapers.plugins.dattebayo import (
    Dattebayo,
    _extract_episode_number,
    extract_video_id,
    resolve_signed_video_url,
    sign_video_url,
    unsigned_video_url,
)

SEARCH_HTML = """
<html><body>
<div class="aniContainer">
  <div class="ultimosAnimesHomeItem">
    <a href="/animes/naruto">
      <div class="ultimosAnimesHomeItemInfos">
        <div class="ultimosAnimesHomeItemInfosNome">Naruto</div>
      </div>
    </a>
  </div>
  <div class="ultimosAnimesHomeItem">
    <a href="https://www.dattebayo-br.com/animes/bleach">
      <div class="ultimosAnimesHomeItemInfos">
        <div class="ultimosAnimesHomeItemInfosNome">Bleach</div>
      </div>
    </a>
  </div>
</div>
</body></html>
"""

EPISODES_HTML = """
<html><body>
<div class="aniContainer">
  <div class="ultimosEpisodiosHomeItem">
    <a href="/videos/100" title="Naruto ep 1">
      <div class="ultimosEpisodiosHomeItemInfos">
        <div class="ultimosEpisodiosHomeItemInfosNome">Naruto ep 1</div>
      </div>
    </a>
  </div>
</div>
</body></html>
"""


def _html_response(html: str) -> MagicMock:
    response = MagicMock()
    response.text = html
    response.raise_for_status = MagicMock()
    return response


def _json_response(payload) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    return response


def _event(is_set: bool = False) -> MagicMock:
    event = MagicMock()
    event.is_set.return_value = is_set
    return event


class TestExtractEpisodeNumber:
    def test_extracts_episodio_pattern(self):
        assert _extract_episode_number("Naruto Episódio 5") == 5

    def test_extracts_ep_pattern(self):
        assert _extract_episode_number("Naruto ep 12") == 12

    def test_returns_zero_for_no_number(self):
        assert _extract_episode_number("Naruto") == 0


class TestDattebayoSearch:
    def setup_method(self):
        self.scraper = Dattebayo()

    @patch("scrapers.plugins.dattebayo.httpx.get")
    def test_search_returns_results(self, mock_get):
        mock_get.return_value = _html_response(SEARCH_HTML)

        results = self.scraper.search_anime("naruto")

        assert len(results) == 2
        titles = [item.title for item in results]
        assert "Naruto" in titles
        assert "Bleach" in titles

    @patch("scrapers.plugins.dattebayo.httpx.get")
    def test_search_resolves_relative_urls(self, mock_get):
        mock_get.return_value = _html_response(SEARCH_HTML)

        results = self.scraper.search_anime("naruto")

        assert all(item.url.startswith("https://") for item in results)

    @patch("scrapers.plugins.dattebayo.httpx.get")
    def test_list_animes_returns_catalog(self, mock_get):
        mock_get.return_value = _html_response(SEARCH_HTML)

        results = self.scraper.list_animes(page=2)

        assert len(results) == 2
        mock_get.assert_called_once()
        assert mock_get.call_args.args[0] == "https://www.dattebayo-br.com/animes/page/2"


class TestDattebayoEpisodes:
    def setup_method(self):
        self.scraper = Dattebayo()

    @patch("scrapers.plugins.dattebayo.rep")
    @patch("scrapers.plugins.dattebayo.httpx.get")
    def test_episodes_paginate_until_empty_page(self, mock_get, mock_rep):
        mock_get.side_effect = [
            _html_response(EPISODES_HTML),
            _html_response("<html><body></body></html>"),
        ]

        self.scraper.search_episodes("Naruto", "https://www.dattebayo-br.com/animes/naruto", None)

        assert mock_get.call_count == 2


class TestDattebayoSigning:
    def test_extract_video_id(self):
        assert extract_video_id("https://www.dattebayo-br.com/videos/560174") == "560174"

    def test_unsigned_video_url_fullhd(self):
        url = unsigned_video_url("560174", quality="fullhd")
        assert url.endswith("/fful/560174.mp4")

    @patch("scrapers.plugins.dattebayo.httpx.Client")
    def test_sign_video_url(self, mock_client_cls):
        client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = client
        client.get.return_value = _json_response([{"ads": "OK", "publicidade": "?sig=abc"}])

        signed = sign_video_url(
            client,
            "https://842e802996826993acdd6d2f7385b287.r2.cloudflarestorage.com/fful/560174.mp4",
            referer="https://www.dattebayo-br.com/videos/560174",
        )

        assert signed.endswith("?sig=abc")

    def test_resolve_signed_video_url_fallback(self):
        episode_url = "https://www.dattebayo-br.com/videos/560174"
        fullhd = unsigned_video_url("560174", quality="fullhd")
        hd = unsigned_video_url("560174", quality="hd")

        client = MagicMock()

        def get_side_effect(url, **kwargs):
            if "ads.animeyabu.net" in url and "fful" in url:
                return _json_response([{"ads": "OK", "publicidade": "?sig=full"}])
            if "ads.animeyabu.net" in url and "f333" in url:
                return _json_response([{"ads": "OK", "publicidade": "?sig=hd"}])
            response = MagicMock()
            if url.startswith(fullhd):
                response.status_code = 404
            elif url.startswith(hd):
                response.status_code = 206
            else:
                response.status_code = 404
            return response

        client.get.side_effect = get_side_effect

        resolved = resolve_signed_video_url(client, episode_url)

        assert resolved.startswith(hd)
        assert "sig=hd" in resolved


class TestDattebayoPlayerSrc:
    def setup_method(self):
        self.scraper = Dattebayo()

    @patch("scrapers.plugins.dattebayo.resolve_signed_video_url")
    @patch("scrapers.plugins.dattebayo.httpx.Client")
    def test_search_player_src_stores_signed_url(self, mock_client_cls, mock_resolve):
        mock_resolve.return_value = "https://r2.example.com/fful/560174.mp4?sig=abc"
        container = []
        event = _event()

        self.scraper.search_player_src(
            "https://www.dattebayo-br.com/videos/560174", container, event
        )

        assert container == ["https://r2.example.com/fful/560174.mp4?sig=abc"]

    @patch("scrapers.plugins.dattebayo.resolve_signed_video_url")
    @patch("scrapers.plugins.dattebayo.httpx.Client")
    def test_search_player_src_raises_when_unresolved(self, mock_client_cls, mock_resolve):
        mock_resolve.side_effect = ValueError("no source")
        container = []
        event = _event()

        with pytest.raises(ValueError, match="Dattebayo: no source"):
            self.scraper.search_player_src(
                "https://www.dattebayo-br.com/videos/560174", container, event
            )
