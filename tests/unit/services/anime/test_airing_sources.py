import json
from datetime import datetime, UTC

from models.download import AiringSourceBinding
from services.anime.airing_sources import AiringSourceStore


def _binding(source: str = "source-a") -> AiringSourceBinding:
    return AiringSourceBinding(
        title="Example Anime",
        source=source,
        anime_url="https://example.test/anime",
        params={"slug": "example"},
        variant="dubbed",
        episode_number_offset=0,
        recorded_at=datetime(2026, 9, 8, tzinfo=UTC),
    )


def test_round_trip_keeps_one_shared_binding(tmp_path):
    path = tmp_path / "airing_download_sources.json"
    store = AiringSourceStore(path)

    store.save_configured(42, _binding("source-a"))
    store.save_last_played(42, _binding("source-b"))

    record = store.load(42)
    assert record is not None
    assert record.binding.source == "source-b"
    assert record.configured.source == "source-b"
    assert record.last_played.source == "source-b"
    assert store.effective(42).origin == "binding"
    assert store.effective(42).binding.source == "source-b"
    assert set(json.loads(path.read_text(encoding="utf-8"))["42"]) == {"binding"}
    assert not list(tmp_path.glob("*.tmp"))


def test_source_binding_is_shared_by_anilist_and_airing(tmp_path):
    store = AiringSourceStore(tmp_path / "airing_download_sources.json")
    selected = _binding("source-a")
    updated = _binding("source-b")

    store.save_configured(42, selected)
    assert store.effective(42).binding == selected

    store.save_last_played(42, updated)

    record = store.load(42)
    assert record is not None
    assert record.binding == updated
    assert store.effective(42).binding == updated


def test_clearing_source_removes_the_shared_binding(tmp_path):
    store = AiringSourceStore(tmp_path / "airing_download_sources.json")
    store.save_configured(42, _binding("source-a"))
    store.save_last_played(42, _binding("source-b"))

    store.clear_configured(42)

    effective = store.effective(42)
    assert effective.origin == "missing"
    assert effective.binding is None


def test_source_binding_does_not_require_a_season(tmp_path):
    path = tmp_path / "airing_download_sources.json"
    store = AiringSourceStore(path)

    store.save_binding(42, _binding())

    assert store.effective(42).binding is not None


def test_new_store_does_not_touch_legacy_files(tmp_path):
    legacy = tmp_path / "history.json"
    legacy.write_text('{"anime": ["kept"]}\n', encoding="utf-8")
    store = AiringSourceStore(tmp_path / "airing_download_sources.json")

    store.save_last_played(42, _binding())

    assert legacy.read_text(encoding="utf-8") == '{"anime": ["kept"]}\n'
