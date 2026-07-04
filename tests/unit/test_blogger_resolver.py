"""Tests for blogger token resolution quality selection."""

from scrapers.core.blogger_resolver import _parse_batchexecute_streams, resolve_blogger_token


def test_parse_batchexecute_streams_prefers_hd_itag():
    inner = [
        1,
        None,
        [
            ["https://googlevideo.com/low?itag=18", [18]],
            ["https://googlevideo.com/hd?itag=22", [22]],
        ],
    ]

    urls = _parse_batchexecute_streams(inner)

    assert urls == [
        "https://googlevideo.com/hd?itag=22",
        "https://googlevideo.com/low?itag=18",
    ]


def test_resolve_blogger_token_returns_best_stream(monkeypatch):
    def fake_fetch(_token: str):
        return [
            1,
            None,
            [
                ["https://googlevideo.com/low?itag=18", [18]],
                ["https://googlevideo.com/hd?itag=22", [22]],
            ],
        ]

    monkeypatch.setattr(
        "scrapers.core.blogger_resolver._fetch_batchexecute_inner",
        fake_fetch,
    )

    assert resolve_blogger_token("token") == "https://googlevideo.com/hd?itag=22"
