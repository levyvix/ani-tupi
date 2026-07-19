"""Tests for run_dual_contextual_search resource handling (H8).

Ensures a failure in one worker propagates without hanging and without
leaving the sibling future's result silently unretrieved. The
ProcessPoolExecutor is replaced with an inline fake so the test is fast and
launches no real subprocesses.
"""

from concurrent.futures import Future

import pytest

import services.anime.search.core as search_mod


class _InlineExecutor:
    """Minimal ProcessPoolExecutor stand-in that runs submitted callables inline."""

    def __init__(self, *args, **kwargs):
        self.shutdown_called = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        # Mirror ProcessPoolExecutor: shutdown(wait=True) on block exit.
        self.shutdown_called = True
        return False

    def submit(self, fn, *args, **kwargs):
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001 - forward into future
            future.set_exception(exc)
        return future


def test_dual_search_happy_path(monkeypatch):
    """Both workers succeed: results are combined and returned."""
    monkeypatch.setattr(search_mod, "ProcessPoolExecutor", _InlineExecutor)
    monkeypatch.setattr(
        search_mod,
        "_parallel_contextual_search_worker",
        lambda used, orig: {"titles_with_sources": [f"{used}!"]},
    )
    monkeypatch.setattr(
        search_mod,
        "_search_results_from_serialized",
        lambda query, payload: (query, payload),
    )

    result = search_mod.run_dual_contextual_search("user", "official")

    assert result.user_query == "user"
    assert result.official_query == "official"
    assert result.user_results == ("user", {"titles_with_sources": ["user!"]})
    assert result.official_results == (
        "official",
        {"titles_with_sources": ["official!"]},
    )


def test_dual_search_propagates_worker_error(monkeypatch):
    """If one worker raises, the error propagates and the call returns promptly."""
    monkeypatch.setattr(search_mod, "ProcessPoolExecutor", _InlineExecutor)

    def flaky_worker(used, orig):
        if used == "user":
            raise RuntimeError("boom")
        return {"titles_with_sources": []}

    monkeypatch.setattr(search_mod, "_parallel_contextual_search_worker", flaky_worker)

    with pytest.raises(RuntimeError, match="boom"):
        search_mod.run_dual_contextual_search("user", "official")
