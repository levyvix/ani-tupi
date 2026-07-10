"""Tests for the http_get_with_retry helper in scrapers.plugins.utils."""

import httpx
import pytest

from scrapers.plugins import utils
from scrapers.plugins.utils import http_get_with_retry


class _Resp:
    """Minimal fake httpx.Response for retry tests."""

    def __init__(self, status_code=200, headers=None):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = "ok"

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=request, response=response
            )


@pytest.fixture
def no_sleep(monkeypatch):
    """Patch time.sleep so tests are fast, recording the delays requested."""
    slept: list[float] = []
    monkeypatch.setattr(utils.time, "sleep", lambda d: slept.append(d))
    return slept


def _patch_get(monkeypatch, responses):
    """Patch httpx.get to yield the given sequence of responses/exceptions."""
    calls = {"count": 0, "args": []}
    it = iter(responses)

    def fake_get(url, headers=None, timeout=None, follow_redirects=None):
        calls["count"] += 1
        calls["args"].append(
            {"url": url, "headers": headers, "timeout": timeout, "redirects": follow_redirects}
        )
        item = next(it)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(utils.httpx, "get", fake_get)
    return calls


def test_success_first_try_no_retry(monkeypatch, no_sleep):
    calls = _patch_get(monkeypatch, [_Resp(200)])

    resp = http_get_with_retry("https://example.test", headers={"X": "1"}, timeout=15)

    assert resp.status_code == 200
    assert calls["count"] == 1
    assert no_sleep == []
    # Headers / timeout forwarded identically.
    assert calls["args"][0]["headers"] == {"X": "1"}
    assert calls["args"][0]["timeout"] == 15
    assert calls["args"][0]["redirects"] is True


def test_429_with_retry_after_then_success(monkeypatch, no_sleep):
    calls = _patch_get(
        monkeypatch,
        [_Resp(429, headers={"Retry-After": "2"}), _Resp(200)],
    )

    resp = http_get_with_retry("https://example.test")

    assert resp.status_code == 200
    assert calls["count"] == 2
    # Honored the Retry-After header (2 seconds), not exponential backoff.
    assert no_sleep == [2.0]


def test_429_without_retry_after_uses_backoff(monkeypatch, no_sleep):
    calls = _patch_get(monkeypatch, [_Resp(429), _Resp(200)])

    resp = http_get_with_retry("https://example.test", backoff_base=0.5)

    assert resp.status_code == 200
    assert calls["count"] == 2
    assert no_sleep == [0.5]  # backoff_base * 2**0


def test_repeated_429_raises_after_max_retries(monkeypatch, no_sleep):
    calls = _patch_get(monkeypatch, [_Resp(429)] * 4)

    with pytest.raises(httpx.HTTPStatusError):
        http_get_with_retry("https://example.test", max_retries=3)

    # 1 initial + 3 retries = 4 attempts.
    assert calls["count"] == 4
    assert len(no_sleep) == 3


def test_repeated_timeout_raises_after_max_retries(monkeypatch, no_sleep):
    calls = _patch_get(
        monkeypatch,
        [httpx.TimeoutException("timeout")] * 4,
    )

    with pytest.raises(httpx.TimeoutException):
        http_get_with_retry("https://example.test", max_retries=3)

    assert calls["count"] == 4
    assert len(no_sleep) == 3


def test_timeout_then_success(monkeypatch, no_sleep):
    calls = _patch_get(
        monkeypatch,
        [httpx.ConnectError("boom"), _Resp(200)],
    )

    resp = http_get_with_retry("https://example.test", backoff_base=0.5)

    assert resp.status_code == 200
    assert calls["count"] == 2
    assert no_sleep == [0.5]


def test_5xx_then_success(monkeypatch, no_sleep):
    calls = _patch_get(monkeypatch, [_Resp(503), _Resp(200)])

    resp = http_get_with_retry("https://example.test", backoff_base=0.5)

    assert resp.status_code == 200
    assert calls["count"] == 2
    assert no_sleep == [0.5]


def test_404_raises_immediately_no_retry(monkeypatch, no_sleep):
    calls = _patch_get(monkeypatch, [_Resp(404)])

    with pytest.raises(httpx.HTTPStatusError):
        http_get_with_retry("https://example.test")

    assert calls["count"] == 1
    assert no_sleep == []
