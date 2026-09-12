"""Tests for MPV playback hint resolution."""

from unittest.mock import MagicMock, patch

from utils import playback_hints
from utils.playback_hints import (
    extract_anidrive_token,
    is_anidrive_hls,
    is_imagesskill_hls,
    resolve_mpv_stream_options,
)


def test_is_imagesskill_hls_detects_playlist():
    url = "https://cdn.imagesskill.com/stream/h/hell-mode-2/01.mp4/index.m3u8"
    assert is_imagesskill_hls(url)


def test_resolve_mpv_stream_options_for_imagesskill():
    url = "https://cdn.imagesskill.com/stream/h/hell-mode-2/01.mp4/index.m3u8"
    referrer, lavf = resolve_mpv_stream_options(url, "https://www.anitube.zip/ep")

    assert referrer == "https://api.anivideo.net/"
    assert lavf is not None
    assert "extension_picky=0" in lavf
    assert "Referer: https://api.anivideo.net/" in lavf


def test_resolve_mpv_stream_options_passthrough_for_other_urls():
    url = "https://googlevideo.com/videoplayback?itag=22"
    referrer, lavf = resolve_mpv_stream_options(url, "https://example.com/")

    assert referrer == "https://example.com/"
    assert lavf is None


def test_is_anidrive_hls_detects_playlist():
    url = "https://static.anidrive.click/hls/some-anime/11/abc-master.m3u8"
    assert is_anidrive_hls(url)
    assert not is_anidrive_hls("https://googlevideo.com/videoplayback?itag=22")


def test_extract_anidrive_token_finds_prime_embed():
    html = '<iframe src="https://anidrive.click/token/bnsc7eixkipiavr?prime"></iframe>'
    assert extract_anidrive_token(html) == "https://anidrive.click/token/bnsc7eixkipiavr?prime"
    assert extract_anidrive_token("<html></html>") is None


def test_resolve_mpv_stream_options_for_anidrive_uses_token_referrer():
    url = "https://static.anidrive.click/hls/some-anime/11/abc-master.m3u8"
    episode_page = "https://anroll.io/66875/"
    token = "https://anidrive.click/token/bnsc7eixkipiavr?prime"

    response = MagicMock()
    response.text = f'<iframe src="{token}"></iframe>'
    response.raise_for_status = MagicMock()
    with patch("httpx.get", return_value=response) as mock_get:
        playback_hints._anidrive_referrer_cache.clear()
        referrer, lavf = resolve_mpv_stream_options(url, episode_page)

    assert referrer == token
    assert lavf is not None
    assert f"Referer: {token}" in lavf
    mock_get.assert_called_once()

    # Second call hits the cache: no extra fetch.
    with patch("httpx.get", side_effect=AssertionError("must use cache")):
        referrer, _ = resolve_mpv_stream_options(url, episode_page)
    assert referrer == token
    playback_hints._anidrive_referrer_cache.clear()


def test_resolve_mpv_stream_options_for_anidrive_fails_open():
    url = "https://static.anidrive.click/hls/some-anime/11/abc-master.m3u8"
    with patch("httpx.get", side_effect=Exception("offline")):
        playback_hints._anidrive_referrer_cache.clear()
        referrer, lavf = resolve_mpv_stream_options(url, "https://anroll.io/1/")

    assert referrer == "https://anroll.io/1/"
    assert lavf is None
    playback_hints._anidrive_referrer_cache.clear()
