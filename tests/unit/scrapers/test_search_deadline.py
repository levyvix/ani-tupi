"""Tests for cooperative search deadline helpers."""

import pytest

from scrapers.core import search_deadline
from scrapers.core.search_deadline import (
    SearchDeadlineExceeded,
    bounded_timeout,
    remaining_search_time,
    sleep_with_search_deadline,
    use_search_deadline,
)


def test_operations_without_search_deadline_keep_their_configured_timeout():
    assert remaining_search_time() is None
    assert bounded_timeout(12) == 12


def test_remaining_time_bounds_operation_timeout(monkeypatch):
    monkeypatch.setattr(search_deadline, "monotonic", lambda: 10.0)

    with use_search_deadline(14.0):
        assert remaining_search_time() == 4.0
        assert bounded_timeout(2.0) == 2.0
        assert bounded_timeout(8.0) == 4.0


def test_expired_search_deadline_raises(monkeypatch):
    monkeypatch.setattr(search_deadline, "monotonic", lambda: 14.0)

    with use_search_deadline(14.0), pytest.raises(SearchDeadlineExceeded):
        remaining_search_time()


def test_retry_sleep_stops_at_search_deadline(monkeypatch):
    now = [10.0]
    slept = []
    monkeypatch.setattr(search_deadline, "monotonic", lambda: now[0])

    def record_sleep(delay):
        slept.append(delay)
        now[0] += delay

    monkeypatch.setattr(search_deadline, "sleep", record_sleep)

    with use_search_deadline(12.0), pytest.raises(SearchDeadlineExceeded):
        sleep_with_search_deadline(5.0)

    assert slept == [2.0]
