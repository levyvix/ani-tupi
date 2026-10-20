"""Tests for AnimeFire scraper."""

import json
from unittest.mock import MagicMock, call, patch

from scrapers.plugins.animefire import AnimeFire


SEARCH_PAYLOAD = {
    "data": [
        {
            "id": "mao-id",
            "titles": {"BR": "Mao"},
            "audio": "Legendado",
        }
    ]
}

ANIME_PAYLOAD = {
    "data": {
        "seasons": [{"number": 1}, {"number": 2}],
        "episodes": [],
    }
}

ANIME_WITH_EPISODES_PAYLOAD = {
    "data": {
        "seasons": [{"number": 1}, {"number": 2}],
        "episodes": [
            {"id": "mao-1", "number": 1, "season": 1, "title": "First"},
            {"id": "mao-2", "number": 1, "season": 2, "title": "Second"},
        ],
    }
}

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

    @patch("scrapers.plugins.animefire.http_get_with_retry")
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

    @patch("scrapers.plugins.animefire.http_get_with_retry")
    def test_search_anime_returns_results(self, mock_get):
        mock_get.side_effect = [
            _Response(json.dumps(SEARCH_PAYLOAD)),
            _Response(json.dumps(ANIME_PAYLOAD)),
        ]

        results = self.scraper.search_anime("mao")

        assert [result.title for result in results] == ["Mao", "Mao 2"]
        assert all(result.url == "https://animefire.one/anime/mao-id" for result in results)
        assert [result.params["season"] for result in results] == [1, 2]
        assert mock_get.call_count == 2

    @patch("scrapers.plugins.animefire.http_get_with_retry")
    def test_search_anime_returns_empty_without_cards(self, mock_get):
        mock_get.return_value = _Response(json.dumps({"data": []}))

        results = self.scraper.search_anime("nothing")

        assert results == []

    @patch("scrapers.plugins.animefire.http_get_with_retry")
    def test_search_episodes_returns_only_requested_season(self, mock_get):
        mock_get.return_value = _Response(json.dumps(ANIME_WITH_EPISODES_PAYLOAD))

        result = self.scraper.search_episodes(
            "Mao 2",
            "https://animefire.one/anime/mao-id",
            {"anime_id": "mao-id", "season": 2},
        )

        assert len(result) == 1
        assert result[0].season == 2
        assert result[0].titles == ["Episódio 1 - Second"]
        assert result[0].urls == ["https://api.animefire.one/episode/mao-2"]

    @patch("scrapers.plugins.animefire.http_get_with_retry")
    def test_search_episodes_returns_episode_list(self, mock_get):
        mock_get.return_value = _Response(EPISODES_HTML)

        result = self.scraper.search_episodes("Mao", "https://animefire.plus/animes/mao", None)

        assert len(result) == 1
        assert result[0].source == "animefire"
        assert result[0].urls == [
            "https://animefire.plus/animes/mao/1",
            "https://animefire.plus/animes/mao/2",
        ]

    @patch("scrapers.plugins.animefire.http_get_with_retry")
    def test_search_episodes_empty_page_returns_empty(self, mock_get):
        mock_get.return_value = _Response("<html></html>")

        result = self.scraper.search_episodes("Mao", "https://animefire.plus/animes/mao", None)

        assert result == []

    @patch("scrapers.plugins.animefire.http_get_with_retry")
    def test_search_player_src_fallbacks_to_video_src(self, mock_get):
        mock_get.return_value = _Response(VIDEO_SRC_HTML)
        container = []
        event = _event()

        self.scraper.search_player_src("https://animefire.plus/animes/mao/9", container, event)

        assert container == ["https://cdn.example.com/mao/9.mp4"]

    @patch("scrapers.plugins.animefire.http_get_with_retry")
    def test_search_player_src_fallbacks_to_iframe(self, mock_get):
        mock_get.return_value = _Response(IFRAME_HTML)
        container = []
        event = _event()

        self.scraper.search_player_src("https://animefire.plus/animes/mao/9", container, event)

        assert container == ["https://embed.example.com/mao/9"]
