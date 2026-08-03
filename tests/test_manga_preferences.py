"""Round-trip tests for manga preferences services.

Verifies set/get/persist/reload behavior using a temporary data directory.
"""

import services.manga.reading_service as selection_module
import services.manga.reading_service as source_module
from services.manga.reading_service import MangaSelectionPreferences
from services.manga.reading_service import MangaSourcePreferences


def test_source_preferences_round_trip(tmp_path, monkeypatch):
    """Set a source preference, persist it, reload, and read it back."""
    monkeypatch.setattr(source_module, "get_data_path", lambda: tmp_path)

    prefs = MangaSourcePreferences()
    prefs.set_preferred_source("One Piece", "mangadex")

    # File persisted at the expected location
    assert (tmp_path / "manga_source_preferences.json").exists()

    # Reload from disk with a fresh instance
    reloaded = MangaSourcePreferences()
    assert reloaded.get_preferred_source("One Piece") == "mangadex"
    # Title matching is case/whitespace-insensitive
    assert reloaded.get_preferred_source("  one piece  ") == "mangadex"
    assert reloaded.get_all_preferences() == {"one piece": "mangadex"}

    # Removal persists too
    assert reloaded.remove_preference("One Piece") is True
    assert MangaSourcePreferences().get_preferred_source("One Piece") is None


def test_selection_preferences_round_trip(tmp_path, monkeypatch):
    """Set a selection preference, persist it, reload, and read it back."""
    monkeypatch.setattr(selection_module, "get_data_path", lambda: tmp_path)

    prefs = MangaSelectionPreferences()
    prefs.set_preferred_manga_id("naruto", "manga-123")

    assert (tmp_path / "manga_selection_preferences.json").exists()

    reloaded = MangaSelectionPreferences()
    assert reloaded.get_preferred_manga_id("naruto") == "manga-123"
    assert reloaded.get_preferred_manga_id("  NARUTO ") == "manga-123"
    assert reloaded.get_all_preferences() == {"naruto": "manga-123"}

    assert reloaded.remove_preference("naruto") is True
    assert MangaSelectionPreferences().get_preferred_manga_id("naruto") is None
