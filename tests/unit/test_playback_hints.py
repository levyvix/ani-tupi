"""Tests for MPV playback hint resolution."""

from utils.playback_hints import is_imagesskill_hls, resolve_mpv_stream_options


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
