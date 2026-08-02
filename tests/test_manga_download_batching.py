"""Tests for the manga batch-download orchestration.

Exercises the real batching/ordering logic in
``services.manga.download_service.download_chapters_batch`` and the split/parallelism
helpers, mocking only the per-chapter download unit (which performs the actual
network + filesystem writes).
"""

from types import SimpleNamespace


import services.manga.download_service as dl
from services.manga.download_service import (
    BatchDownloadResult,
    download_chapters_batch,
    resolve_parallelism,
    split_new_and_downloaded,
)


def _ch(number: str):
    return SimpleNamespace(number=number, id=f"id-{number}", url="http://x")


class _FakeTracker:
    """In-memory stand-in for DownloadedChaptersTracker."""

    def __init__(self, downloaded: set[str] | None = None):
        self._downloaded = set(downloaded or set())

    def is_downloaded(self, manga_id: str, chapter_number: str) -> bool:
        return chapter_number in self._downloaded


class TestSplitNewAndDownloaded:
    def test_splits_correctly(self):
        chapters = [_ch("1"), _ch("2"), _ch("3")]
        tracker = _FakeTracker({"2"})
        new, done = split_new_and_downloaded(chapters, "manga-1", tracker)
        assert [c.number for c in new] == ["1", "3"]
        assert [c.number for c in done] == ["2"]

    def test_all_new(self):
        chapters = [_ch("1"), _ch("2")]
        new, done = split_new_and_downloaded(chapters, "m", _FakeTracker())
        assert len(new) == 2
        assert done == []


class TestResolveParallelism:
    def test_zero_uses_cpu_count(self):
        assert resolve_parallelism(0) >= 1

    def test_explicit_value_preserved(self):
        assert resolve_parallelism(3) == 3


class TestSequentialBatch:
    def test_all_succeed(self, monkeypatch):
        calls = []

        def fake_download(chapter, *args, **kwargs):
            calls.append(chapter.number)
            return True, ""

        monkeypatch.setattr(dl, "download_chapter", fake_download)

        result = download_chapters_batch(
            [_ch("1"), _ch("2"), _ch("3")],
            service=None,
            selected_manga=None,
            manga_url=None,
            selected_source="s",
            config=None,
            tracker=_FakeTracker(),
            max_parallel=1,
        )
        assert isinstance(result, BatchDownloadResult)
        assert result.successful == 3
        assert result.failed_chapters == []
        assert result.cancelled is False
        # Sequential preserves input order.
        assert calls == ["1", "2", "3"]

    def test_failure_records_and_continues(self, monkeypatch):
        def fake_download(chapter, *args, **kwargs):
            return (chapter.number != "2"), "boom" if chapter.number == "2" else ""

        monkeypatch.setattr(dl, "download_chapter", fake_download)

        result = download_chapters_batch(
            [_ch("1"), _ch("2"), _ch("3")],
            service=None,
            selected_manga=None,
            manga_url=None,
            selected_source="s",
            config=None,
            tracker=_FakeTracker(),
            max_parallel=1,
            on_failure=lambda _msg: True,  # keep going
        )
        assert result.successful == 2
        assert result.failed_chapters == ["2"]
        assert result.cancelled is False

    def test_on_failure_abort_stops_batch(self, monkeypatch):
        def fake_download(chapter, *args, **kwargs):
            return (chapter.number != "2"), "boom"

        monkeypatch.setattr(dl, "download_chapter", fake_download)

        result = download_chapters_batch(
            [_ch("1"), _ch("2"), _ch("3")],
            service=None,
            selected_manga=None,
            manga_url=None,
            selected_source="s",
            config=None,
            tracker=_FakeTracker(),
            max_parallel=1,
            on_failure=lambda _msg: False,  # abort
        )
        assert result.successful == 1
        assert result.failed_chapters == ["2"]
        assert result.cancelled is True

    def test_on_progress_called_per_chapter(self, monkeypatch):
        monkeypatch.setattr(dl, "download_chapter", lambda *a, **k: (True, ""))
        seen = []
        download_chapters_batch(
            [_ch("1"), _ch("2")],
            service=None,
            selected_manga=None,
            manga_url=None,
            selected_source="s",
            config=None,
            tracker=_FakeTracker(),
            max_parallel=1,
            on_progress=lambda ok, failed: seen.append((ok, len(failed))),
        )
        assert seen == [(1, 0), (2, 0)]


class TestParallelBatch:
    def test_parallel_counts_all(self, monkeypatch):
        monkeypatch.setattr(dl, "download_chapter", lambda *a, **k: (True, ""))
        result = download_chapters_batch(
            [_ch(str(i)) for i in range(1, 6)],
            service=None,
            selected_manga=None,
            manga_url=None,
            selected_source="s",
            config=None,
            tracker=_FakeTracker(),
            max_parallel=4,
        )
        assert result.successful == 5
        assert result.failed_chapters == []

    def test_parallel_mixed_results(self, monkeypatch):
        def fake_download(chapter, *args, **kwargs):
            ok = int(chapter.number) % 2 == 1
            return ok, "" if ok else "err"

        monkeypatch.setattr(dl, "download_chapter", fake_download)
        result = download_chapters_batch(
            [_ch(str(i)) for i in range(1, 5)],
            service=None,
            selected_manga=None,
            manga_url=None,
            selected_source="s",
            config=None,
            tracker=_FakeTracker(),
            max_parallel=4,
        )
        assert result.successful == 2  # 1 and 3
        assert sorted(result.failed_chapters) == ["2", "4"]

    def test_parallel_progress_callback_fires_for_each(self, monkeypatch):
        monkeypatch.setattr(dl, "download_chapter", lambda *a, **k: (True, ""))
        count = {"n": 0}
        download_chapters_batch(
            [_ch(str(i)) for i in range(1, 4)],
            service=None,
            selected_manga=None,
            manga_url=None,
            selected_source="s",
            config=None,
            tracker=_FakeTracker(),
            max_parallel=2,
            on_progress=lambda ok, failed: count.__setitem__("n", count["n"] + 1),
        )
        assert count["n"] == 3
