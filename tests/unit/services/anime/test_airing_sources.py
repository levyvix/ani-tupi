from datetime import datetime, UTC

import pytest

from models.download import AiringSourceBinding
from services.anime.airing_sources import (
    AiringSourceStore,
    AmbiguousAiringSourceError,
)


def _binding(source: str = "source-a", *, season: int | None = 2) -> AiringSourceBinding:
    return AiringSourceBinding(
        title="Example Anime",
        source=source,
        anime_url="https://example.test/anime",
        params={"slug": "example"},
        variant="dubbed",
        season=season,
        episode_number_offset=0,
        recorded_at=datetime(2026, 9, 8, tzinfo=UTC),
    )


def test_round_trip_keeps_configured_and_last_played_independent(tmp_path):
    path = tmp_path / "airing_download_sources.json"
    store = AiringSourceStore(path)

    store.save_configured(42, _binding("source-a"))
    store.save_last_played(42, _binding("source-b", season=1))

    record = store.load(42)
    assert record is not None
    assert record.configured.source == "source-a"
    assert record.last_played.source == "source-b"
    assert store.effective(42).origin == "configured"
    assert store.effective(42).binding.source == "source-a"
    assert not list(tmp_path.glob("*.tmp"))


def test_clearing_configured_source_falls_back_to_last_played(tmp_path):
    store = AiringSourceStore(tmp_path / "airing_download_sources.json")
    store.save_configured(42, _binding("source-a"))
    store.save_last_played(42, _binding("source-b"))

    store.clear_configured(42)

    effective = store.effective(42)
    assert effective.origin == "last_played"
    assert effective.binding.source == "source-b"


def test_ambiguous_season_is_rejected_without_writing(tmp_path):
    path = tmp_path / "airing_download_sources.json"
    store = AiringSourceStore(path)

    with pytest.raises(AmbiguousAiringSourceError):
        store.save_configured(42, _binding(season=None))

    assert not path.exists()


def test_new_store_does_not_touch_legacy_files(tmp_path):
    legacy = tmp_path / "history.json"
    legacy.write_text('{"anime": ["kept"]}\n', encoding="utf-8")
    store = AiringSourceStore(tmp_path / "airing_download_sources.json")

    store.save_last_played(42, _binding())

    assert legacy.read_text(encoding="utf-8") == '{"anime": ["kept"]}\n'
