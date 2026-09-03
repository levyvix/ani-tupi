"""Tests for the http_*_with_retry helpers in scrapers.plugins.utils."""

import httpx
import pytest

from scrapers.plugins import utils
from scrapers.plugins.utils import (
    CloudflareChallengeError,
    http_get_with_retry,
    http_request_with_retry,
    http_head_with_fallback,
)


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


def _patch_request(monkeypatch, responses):
    """Patch httpx.request to yield the given sequence of responses/exceptions."""
    calls = {"count": 0, "args": []}
    it = iter(responses)

    def fake_request(method, url, **kwargs):
        calls["count"] += 1
        calls["args"].append(
            {
                "method": method,
                "url": url,
                "headers": kwargs.get("headers"),
                "timeout": kwargs.get("timeout"),
                "follow_redirects": kwargs.get("follow_redirects"),
            }
        )
        item = next(it)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(utils.httpx, "request", fake_request)
    return calls


def test_success_first_try_no_retry(monkeypatch, no_sleep):
    calls = _patch_request(monkeypatch, [_Resp(200)])

    resp = http_get_with_retry("https://example.test", headers={"X": "1"}, timeout=15)

    assert resp.status_code == 200
    assert calls["count"] == 1
    assert no_sleep == []
    assert calls["args"][0]["headers"] == {"X": "1"}
    assert calls["args"][0]["timeout"] == 15
    assert calls["args"][0]["follow_redirects"] is True


def test_429_with_retry_after_then_success(monkeypatch, no_sleep):
    calls = _patch_request(
        monkeypatch,
        [_Resp(429, headers={"Retry-After": "2"}), _Resp(200)],
    )

    resp = http_get_with_retry("https://example.test")

    assert resp.status_code == 200
    assert calls["count"] == 2
    assert no_sleep == [2.0]


def test_429_without_retry_after_uses_backoff(monkeypatch, no_sleep):
    calls = _patch_request(monkeypatch, [_Resp(429), _Resp(200)])

    resp = http_get_with_retry("https://example.test", backoff_base=0.5)

    assert resp.status_code == 200
    assert calls["count"] == 2
    assert no_sleep == [0.5]


def test_repeated_429_raises_after_max_retries(monkeypatch, no_sleep):
    calls = _patch_request(monkeypatch, [_Resp(429)] * 4)

    with pytest.raises(httpx.HTTPStatusError):
        http_get_with_retry("https://example.test", max_retries=3)

    assert calls["count"] == 4
    assert len(no_sleep) == 3


def test_repeated_timeout_raises_after_max_retries(monkeypatch, no_sleep):
    calls = _patch_request(
        monkeypatch,
        [httpx.TimeoutException("timeout")] * 4,
    )

    with pytest.raises(httpx.TimeoutException):
        http_get_with_retry("https://example.test", max_retries=3)

    assert calls["count"] == 4
    assert len(no_sleep) == 3


def test_timeout_then_success(monkeypatch, no_sleep):
    calls = _patch_request(
        monkeypatch,
        [httpx.ConnectError("boom"), _Resp(200)],
    )

    resp = http_get_with_retry("https://example.test", backoff_base=0.5)

    assert resp.status_code == 200
    assert calls["count"] == 2
    assert no_sleep == [0.5]


def test_5xx_then_success(monkeypatch, no_sleep):
    calls = _patch_request(monkeypatch, [_Resp(503), _Resp(200)])

    resp = http_get_with_retry("https://example.test", backoff_base=0.5)

    assert resp.status_code == 200
    assert calls["count"] == 2
    assert no_sleep == [0.5]


def test_404_raises_immediately_no_retry(monkeypatch, no_sleep):
    calls = _patch_request(monkeypatch, [_Resp(404)])

    with pytest.raises(httpx.HTTPStatusError):
        http_get_with_retry("https://example.test")

    assert calls["count"] == 1
    assert no_sleep == []


def test_cloudflare_challenge_raises_clear_error_without_retry(monkeypatch, no_sleep):
    request = httpx.Request("GET", "https://protected.example")
    response = httpx.Response(
        403,
        request=request,
        headers={"cf-mitigated": "challenge", "server": "cloudflare"},
    )
    calls = _patch_request(monkeypatch, [response])

    with pytest.raises(CloudflareChallengeError, match="requires a browser challenge"):
        http_get_with_retry("https://protected.example")

    assert calls["count"] == 1
    assert no_sleep == []


# Tests for http_request_with_retry (POST support)


def test_post_request_success(monkeypatch):
    """Test POST request via http_request_with_retry."""
    calls = _patch_request(monkeypatch, [_Resp(200)])

    resp = http_request_with_retry(
        "POST",
        "https://example.test/api",
        json={"query": "test"},
        timeout=15,
    )

    assert resp.status_code == 200
    assert calls["count"] == 1
    assert calls["args"][0]["method"] == "POST"
    assert calls["args"][0]["timeout"] == 15


def test_post_request_429_retry(monkeypatch, no_sleep):
    """Test POST request retries on 429."""
    calls = _patch_request(
        monkeypatch,
        [_Resp(429), _Resp(200)],
    )

    resp = http_request_with_retry(
        "POST",
        "https://example.test/api",
        json={"query": "test"},
        backoff_base=0.5,
    )

    assert resp.status_code == 200
    assert calls["count"] == 2
    assert len(no_sleep) == 1


def test_get_is_wrapper_around_request(monkeypatch):
    """Verify http_get_with_retry uses http_request_with_retry internally."""
    calls = _patch_request(monkeypatch, [_Resp(200)])

    resp = http_get_with_retry("https://example.test", headers={"X": "1"})

    assert resp.status_code == 200
    assert calls["count"] == 1
    assert calls["args"][0]["method"] == "GET"
    assert calls["args"][0]["headers"] == {"X": "1"}


# Tests for http_head_with_fallback


def _patch_request_for_head(monkeypatch, head_response, fallback_response=None):
    """Patch httpx.request to handle HEAD attempts and fallback GET."""
    calls = {"count": 0, "methods": []}
    it = iter([head_response] + ([fallback_response] if fallback_response else []))

    def fake_request(method, *args, **kwargs):
        _ = (args, kwargs)
        calls["count"] += 1
        calls["methods"].append(method)
        item = next(it)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(utils.httpx, "request", fake_request)
    return calls


def test_head_success_no_fallback(monkeypatch):
    """Test HEAD succeeds without needing fallback."""
    calls = _patch_request_for_head(monkeypatch, _Resp(200))

    resp = http_head_with_fallback("https://example.test")

    assert resp.status_code == 200
    assert calls["count"] == 1
    assert calls["methods"] == ["HEAD"]


def test_head_403_falls_back_to_get(monkeypatch):
    """Test HEAD 403 falls back to GET with Range header."""
    calls = _patch_request_for_head(monkeypatch, _Resp(403), _Resp(200))

    resp = http_head_with_fallback("https://example.test")

    assert resp.status_code == 200
    assert calls["count"] == 2
    assert calls["methods"] == ["HEAD", "GET"]


def test_head_cloudflare_challenge_does_not_try_plain_get(monkeypatch):
    request = httpx.Request("HEAD", "https://protected.example")
    response = httpx.Response(
        403,
        request=request,
        headers={"cf-mitigated": "challenge", "server": "cloudflare"},
    )
    calls = _patch_request_for_head(monkeypatch, response)

    with pytest.raises(CloudflareChallengeError):
        http_head_with_fallback("https://protected.example")

    assert calls["methods"] == ["HEAD"]


def test_head_405_falls_back_to_get(monkeypatch):
    """Test HEAD 405 (Method Not Allowed) falls back to GET."""
    calls = _patch_request_for_head(monkeypatch, _Resp(405), _Resp(200))

    resp = http_head_with_fallback("https://example.test")

    assert resp.status_code == 200
    assert calls["count"] == 2
    assert calls["methods"] == ["HEAD", "GET"]


def test_head_404_raises_no_fallback(monkeypatch):
    """Test HEAD 404 raises immediately without fallback."""
    calls = _patch_request_for_head(monkeypatch, _Resp(404))

    with pytest.raises(httpx.HTTPStatusError):
        http_head_with_fallback("https://example.test")

    assert calls["count"] == 1
    assert calls["methods"] == ["HEAD"]


def test_head_500_retries_then_raises(monkeypatch):
    """Test HEAD 500 retries and eventually raises."""
    calls = _patch_request_for_head(monkeypatch, _Resp(500), _Resp(500))

    with pytest.raises(httpx.HTTPStatusError):
        http_head_with_fallback("https://example.test", max_retries=1)

    assert all(m == "HEAD" for m in calls["methods"])
