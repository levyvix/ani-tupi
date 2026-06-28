"""Tests for AnimeFire scraper player source extraction."""

import json
from unittest.mock import MagicMock, patch

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
    def __init__(self, payload):
        self.text = json.dumps(payload)

    def raise_for_status(self):
        return None


def _event():
    event = MagicMock()
    event.is_set.return_value = False
    return event


class TestAnimeFireScraper:
    def setup_method(self):
        self.scraper = AnimeFire()

    @patch("scrapers.plugins.animefire.httpx.get")
    @patch("scrapers.plugins.animefire.SeleniumWebDriver")
    def test_search_player_src_uses_json_endpoint(self, mock_driver, mock_get):
        driver = mock_driver.return_value.__enter__.return_value
        driver.fetch.return_value = MagicMock(
            select_one=lambda *_: MagicMock(
                get=lambda k: (
                    "https://animefire.io/video/mao/9?tempsubs=0&1780178669"
                    if k == "data-video-src"
                    else None
                )
            )
        )
        mock_get.return_value = _Response(VIDEO_JSON)

        container = []
        event = _event()

        self.scraper.search_player_src("https://animefire.io/animes/mao/9", container, event)

        assert container == ["https://lightspeedst.net/s8/mp4/mao/hd/9.mp4?token=hd&expires=1"]
        mock_get.assert_called_once_with(
            "https://animefire.io/video/mao/9?tempsubs=0&1780178669",
            timeout=20,
            follow_redirects=True,
        )
