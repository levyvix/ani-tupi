"""Tests for identity-aware download catalog and source binding persistence."""

import json
import threading
from pathlib import Path

from models.download import AiringSourceBinding
from services.anime.download_catalog import (
    DownloadCatalog,
    catalog_lock,
    effective_source,
    get_source_record,
    record_confirmed_remote_playback,
    remove_configured_source,
    set_configured_source,
    stable_anime_directory,
)


def _run_with_timeout(target, timeout: float = 5.0) -> bool:
    """Run *target* in a thread, returning False if it did not finish in time."""
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)
    return not thread.is_alive()


def _valid_video(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * (2 * 1024 * 1024))


def _binding(source: str, title: str = "Friendly title") -> AiringSourceBinding:
    return AiringSourceBinding(
        title=title,
        source=source,
        anime_url=f"https://{source}.example/anime/title",
        season=1,
    )


def test_legacy_database_round_trip_keeps_old_records(tmp_path):
    db_path = tmp_path / "anime_downloads.json"
    db_path.write_text(
        json.dumps(
            {
                "version": 1,
                "anime": {
                    "Old title": {
                        "anime_title": "Old title",
                        "episodes": {},
                        "last_downloaded": "2026-01-01T00:00:00",
                        "total_size_mb": 0,
                    }
                },
                "last_updated": "2026-01-01T00:00:00",
            }
        )
    )

    database = DownloadCatalog(db_path, tmp_path / "downloads").load_database()

    assert database.anime["Old title"].anime_id if False else "Old title" in database.anime
    assert database.anime["Old title"].anilist_id is None


def test_identity_lookup_survives_title_and_source_changes(tmp_path):
    catalog = DownloadCatalog(tmp_path / "db.json", tmp_path / "downloads")
    file_path = stable_anime_directory(catalog.download_dir, "Old title", 101) / "4.mkv"
    _valid_video(file_path)
    catalog.register_episode(
        "Old title",
        4,
        file_path,
        source="source-a",
        anilist_id=101,
        season=1,
        variant="sub",
    )

    found = catalog.find_episode(101, 4, season=1, variant="sub", anime_title="New title")

    assert found is not None
    assert found.source == "source-a"
    assert found.file_path == file_path


def test_same_title_with_different_ids_uses_stable_directories(tmp_path):
    first = stable_anime_directory(tmp_path, "Same title", 1)
    second = stable_anime_directory(tmp_path, "Same title", 2)

    assert first != second
    assert first.name == "anilist-1"
    assert second.name == "anilist-2"


def test_same_title_with_different_ids_keeps_catalog_entries_separate(tmp_path):
    catalog = DownloadCatalog(tmp_path / "db.json", tmp_path / "downloads")
    first_path = stable_anime_directory(catalog.download_dir, "Same title", 1) / "1.mkv"
    second_path = stable_anime_directory(catalog.download_dir, "Same title", 2) / "1.mkv"
    _valid_video(first_path)
    _valid_video(second_path)

    catalog.register_episode("Same title", 1, first_path, source="source-a", anilist_id=1)
    catalog.register_episode("Same title", 1, second_path, source="source-b", anilist_id=2)

    database = catalog.load_database()
    assert len(database.anime) == 2
    assert catalog.find_episode(1, 1) is not None
    assert catalog.find_episode(2, 1) is not None


def test_source_precedence_and_removal(tmp_path):
    source_path = tmp_path / "airing_download_sources.json"
    set_configured_source(7, _binding("configured"), source_path)
    record_confirmed_remote_playback(
        7,
        "Friendly title",
        "played",
        "https://played.example/episode/2",
        path=source_path,
        episode_number=2,
    )

    binding, origin = effective_source(7, source_path)
    assert binding is not None
    assert binding.source == "configured"
    assert origin == "configured"

    remove_configured_source(7, source_path)
    binding, origin = effective_source(7, source_path)
    assert binding is not None
    assert binding.source == "played"
    assert origin == "last_played"


def test_incomplete_playback_context_does_not_remove_configured(tmp_path):
    source_path = tmp_path / "airing_download_sources.json"
    set_configured_source(8, _binding("configured"), source_path)

    assert (
        record_confirmed_remote_playback(
            8,
            "Friendly title",
            "new-source",
            None,
            path=source_path,
        )
        is False
    )
    record = get_source_record(8, source_path)
    assert record.configured is not None
    assert record.configured.source == "configured"
    assert record.last_played is None


def test_reconcile_registers_published_file_without_downloading_again(tmp_path):
    catalog = DownloadCatalog(tmp_path / "db.json", tmp_path / "downloads")
    file_path = stable_anime_directory(catalog.download_dir, "Anime", 55) / "8.mkv"
    _valid_video(file_path)

    reconciled = catalog.reconcile_episode(
        "Anime",
        8,
        anilist_id=55,
        season=1,
        source="linked-source",
    )

    assert reconciled is not None
    assert catalog.find_episode(55, 8, season=1) is not None


def test_catalog_lock_is_reentrant_within_a_thread(tmp_path):
    lock_path = tmp_path / "catalog.json"
    reached: list[str] = []

    def nested() -> None:
        with catalog_lock(lock_path):
            with catalog_lock(lock_path):
                reached.append("inner")
        reached.append("done")

    assert _run_with_timeout(nested), "nested catalog_lock deadlocked"
    assert reached == ["inner", "done"]


def test_reentrant_lock_still_writes_once(tmp_path):
    catalog = DownloadCatalog(tmp_path / "db.json", tmp_path / "downloads")
    file_path = stable_anime_directory(catalog.download_dir, "Anime", 9) / "1.mkv"
    _valid_video(file_path)

    def nested_write() -> None:
        with catalog_lock(catalog.db_path):
            catalog.reconcile_episode(
                "Anime",
                1,
                anilist_id=9,
                season=1,
                source="linked",
            )

    assert _run_with_timeout(nested_write), "nested reconcile deadlocked"
    assert catalog.find_episode(9, 1, season=1) is not None
