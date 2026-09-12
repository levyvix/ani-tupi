"""Tests for AnimesOnlineIO AniDrive extraction (token Referer + new payload)."""

import base64
import json
from unittest.mock import MagicMock, patch

from scrapers.plugins.animesonlineio import AnimesOnlineIO


def _response(html: str) -> MagicMock:
    mock = MagicMock()
    mock.text = html
    mock.raise_for_status = MagicMock()
    return mock


def _encode_juicy_block(payload: str, key: bytes = b"testkey12") -> tuple[str, str, str]:
    """Build one obfuscated loader block for *payload* (mirrors the site)."""
    raw = payload.encode()
    xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
    # The page splits the base64 *text* into pieces; decoding joins them back.
    blob = base64.b64encode(xored).decode()
    pieces = [blob[i : i + 8] for i in range(0, len(blob), 8)]
    indices = list(range(len(pieces)))
    call = f'}}fn({json.dumps(pieces)},{json.dumps(indices)},"{base64.b64encode(key).decode()}")'
    return call, payload, key.decode()


class TestJuicyDecoding:
    def setup_method(self):
        self.scraper = AnimesOnlineIO()

    def test_decode_all_blocks_skips_service_worker(self):
        worker = "(function registerAniDriveSegmentWorker() {})"
        config = 'window.X={"sources":[{"file":"https://example.com/a.m3u8"}],"tracks":[]}'
        worker_call, _, _ = _encode_juicy_block(worker)
        config_call, _, _ = _encode_juicy_block(config)
        html = f"<html>{worker_call} ... {config_call}</html>"

        payloads = self.scraper._decode_all_juicy_payloads(html)

        assert payloads == [worker, config]
        # Singular helper returns the block holding sources.
        assert "sources" in self.scraper._decode_juicy_payload(html)

    def test_extract_sources_supports_anidrive_config(self):
        payload = (
            'window.AniDrivePlayerConfig={"title":"ep",'
            '"sources":[{"file":"https://static.anidrive.click/x-master.m3u8",'
            '"label":"HLS"}],"tracks":[]}'
        )
        sources = self.scraper._extract_sources_from_payload(payload)

        assert [s["file"] for s in sources] == ["https://static.anidrive.click/x-master.m3u8"]

    def test_extract_sources_supports_legacy_format(self):
        payload = 'setup({\nsources: [{"file":"https://example.com/v.mp4"}],\n});'
        sources = self.scraper._extract_sources_from_payload(payload)

        assert [s["file"] for s in sources] == ["https://example.com/v.mp4"]


class TestEmbedResolve:
    def setup_method(self):
        self.scraper = AnimesOnlineIO()

    @patch("scrapers.plugins.animesonlineio.http_get_with_retry")
    def test_resolve_uses_episode_page_referer(self, mock_get):
        config = '{"sources":[{"file":"https://static.anidrive.click/x.m3u8"}],"tracks":[]}'
        call, _, _ = _encode_juicy_block(config)
        mock_get.return_value = _response(f"<html>{call}</html>")

        streams = self.scraper._resolve_embed_streams(
            "https://anidrive.click/token/abc",
            referer="https://animesonline.io/66875/",
        )

        assert streams == ["https://static.anidrive.click/x.m3u8"]
        assert mock_get.call_args.kwargs["headers"]["Referer"] == ("https://animesonline.io/66875/")

    @patch("scrapers.plugins.animesonlineio.http_get_with_retry")
    def test_search_player_src_forwards_episode_url(self, mock_get):
        episode_html = (
            '<ul class="tabs_videos">'
            '<li value="aHR0cHM6Ly9hbmlkcml2ZS5jbGljay90b2tlbi9hYmM="></li>'
            "</ul>"
        )
        config = '{"sources":[{"file":"https://static.anidrive.click/x.m3u8"}],"tracks":[]}'
        call, _, _ = _encode_juicy_block(config)
        mock_get.side_effect = [_response(episode_html), _response(f"<x>{call}</x>")]

        container: list = []
        event = MagicMock()
        self.scraper.search_player_src("https://animesonline.io/66875/", container, event)

        assert container == ["https://static.anidrive.click/x.m3u8"]
        embed_headers = mock_get.call_args_list[1].kwargs["headers"]
        assert embed_headers["Referer"] == "https://animesonline.io/66875/"
