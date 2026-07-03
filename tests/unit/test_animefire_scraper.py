"""Tests for AnimeFire scraper player source extraction."""

import json
from unittest.mock import MagicMock, call, patch

from scrapers.plugins.animefire import AnimeFire


EPISODE_PAGE_HTML = """
<html><body>
  <video id="my-video" data-video-src="https://animefire.io/video/mao/9?tempsubs=0&1780178669"></video>
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
