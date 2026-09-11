"""Focused tests for the one-shot airing monitor."""

from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from models.anime import ScrapedEpisodes
from models.download import AiringSourceBinding
from services.anime.airing_download_scheduler import (
    AiringDownloadScheduler,
    AiringDownloadSettings,
    _CycleLock,
)


def _entry(anilist_id: int, title: str, status: str = "RELEASING") -> dict:
    return {
        "progress": 3,
        "media": {
            "id": anilist_id,
            "status": status,
            "title": {"romaji": title, "english": None},
        },
    }


class FakeClient:
    def __init__(self, entries):
        self.entries = entries

    def is_authenticated(self):
        return True

    def get_airing_episodes_for_watching(self):
        return self.entries


def test_settings_default_and_allowed_intervals(monkeypatch):
    monkeypatch.delenv("ANI_TUPI__AIRING_DOWNLOADS__POLL_INTERVAL_MINUTES", raising=False)
    assert AiringDownloadSettings().poll_interval_minutes == 30

    monkeypatch.setenv("ANI_TUPI__AIRING_DOWNLOADS__POLL_INTERVAL_MINUTES", "60")
    assert AiringDownloadSettings.from_application().poll_interval_minutes == 60

    with pytest.raises(ValueError):
        AiringDownloadSettings(poll_interval_minutes=7)


def test_cycle_deduplicates_ids_isolates_failures_and_persists_state(tmp_path: Path):
    entries = [_entry(1, "One"), _entry(1, "One duplicate"), _entry(2, "Two")]

    def process(entry, _binding):
        if entry["media"]["id"] == 1:
            raise RuntimeError("source unavailable")
        return {"status": "completed", "successful": 2, "failed": 0, "skipped": 0}

    scheduler = AiringDownloadScheduler(
        client=FakeClient(entries),
        binding_resolver={1: {"source": "a"}, 2: {"source": "b"}},
        processor=process,
        state_path=tmp_path / "state.json",
        lock_path=tmp_path / "lock",
        log_path=tmp_path / "monitor.log",
    )

    result = scheduler.run_once()

    assert result.exit_code == 1
    assert [item["anilist_id"] for item in result.animes] == [1, 2]
    assert result.animes[0]["status"] == "failed"
    assert result.animes[1]["successful"] == 2
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved["status"] == "failed"
    assert saved["animes"][1]["anilist_id"] == 2


def test_cycle_lock_reports_active_without_running_client(tmp_path: Path):
    lock_path = tmp_path / "lock"
    held = _CycleLock(lock_path)
    assert held.acquire() is True
    try:
        scheduler = AiringDownloadScheduler(
            client=FakeClient([]),
            state_path=tmp_path / "state.json",
            lock_path=lock_path,
            log_path=tmp_path / "monitor.log",
        )
        result = scheduler.run_once()
    finally:
        held.release()

    assert result.exit_code == 0
    assert result.active is True
    assert not (tmp_path / "state.json").exists()


def test_cycle_skips_non_releasing_and_unconfigured_anime(tmp_path: Path):
    scheduler = AiringDownloadScheduler(
        client=FakeClient([_entry(1, "Finished", "FINISHED"), _entry(2, "Missing")]),
        binding_resolver={},
        processor=lambda *_: pytest.fail("processor should not run"),
        state_path=tmp_path / "state.json",
        lock_path=tmp_path / "lock",
        log_path=tmp_path / "monitor.log",
    )

    result = scheduler.run_once()

    assert result.exit_code == 0
    assert [item["reason"] for item in result.animes] == ["not_releasing", "source_not_configured"]
    assert result.skipped == 2


def test_mapped_source_episode_uses_source_number_for_storage(tmp_path: Path):
    binding = AiringSourceBinding(
        title="Mapped Anime",
        source="source-a",
        anime_url="https://example.test/anime",
        episode_number_offset=1,
        season=1,
    )

    class Plugin:
        def search_episodes(self, title, url, params):
            return [
                ScrapedEpisodes(
                    titles=["Episode 4"],
                    urls=["https://example.test/episode-4"],
                    source="source-a",
                    season=1,
                )
            ]

    download_calls = []

    class Downloader:
        def download_episodes(self, **kwargs):
            download_calls.append(kwargs)
            return SimpleNamespace(successful=1, skipped=[])

    repository = SimpleNamespace(
        sources={"source-a": Plugin()},
        search_player_from_page=lambda _url, _source: ["https://video.test/4"],
    )
    source_store = SimpleNamespace(effective=lambda _id: SimpleNamespace(binding=binding))
    scheduler = AiringDownloadScheduler(
        repository=repository,
        download_service=Downloader(),
        binding_resolver=source_store,
        state_path=tmp_path / "state.json",
        lock_path=tmp_path / "lock",
        log_path=tmp_path / "monitor.log",
    )

    result = scheduler._process_anime(_entry(7, "Mapped Anime"), binding, "Mapped Anime")

    assert result["successful"] == 1
    assert download_calls[0]["range_input"] == "4"
    assert download_calls[0]["total_episodes"] == 4
    assert download_calls[0]["catalog_episode_number"] == 5
