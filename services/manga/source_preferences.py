"""Manga source preferences manager.

Handles persisting and retrieving user's preferred source for each manga.
Allows users to save their source choice and automatically use it next time.
"""

import json

from models.config import get_data_path


class MangaSourcePreferences:
    """Manages manga source preferences with JSON persistence."""

    def __init__(self):
        """Initialize preferences manager."""
        self.preferences_file = get_data_path() / "manga_source_preferences.json"
        self._preferences: dict[str, str] = {}
        self._load_preferences()

    def _load_preferences(self) -> None:
        """Load preferences from JSON file."""
        try:
            if self.preferences_file.exists():
                with self.preferences_file.open("r", encoding="utf-8") as f:
                    self._preferences = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._preferences = {}

    def _save_preferences(self) -> None:
        """Save preferences to JSON file."""
        try:
            # Ensure directory exists
            self.preferences_file.parent.mkdir(parents=True, exist_ok=True)

            with self.preferences_file.open("w", encoding="utf-8") as f:
                json.dump(self._preferences, f, indent=2, ensure_ascii=False)
        except OSError:
            # Silently fail if unable to save (graceful degradation)
            pass

    def get_preferred_source(self, manga_title: str) -> str | None:
        """Get preferred source for a manga.

        Args:
            manga_title: The manga title

        Returns:
            Preferred source name or None if not set
        """
        # Normalize title for consistent matching
        normalized_title = manga_title.strip().lower()
        return self._preferences.get(normalized_title)

    def set_preferred_source(self, manga_title: str, source: str) -> None:
        """Set preferred source for a manga.

        Args:
            manga_title: The manga title
            source: The source name (e.g., "mugiwaras", "mangadex")
        """
        # Normalize title for consistent matching
        normalized_title = manga_title.strip().lower()
        self._preferences[normalized_title] = source
        self._save_preferences()

    def remove_preference(self, manga_title: str) -> bool:
        """Remove preference for a manga.

        Args:
            manga_title: The manga title

        Returns:
            True if preference was removed, False if not found
        """
        normalized_title = manga_title.strip().lower()
        if normalized_title in self._preferences:
            del self._preferences[normalized_title]
            self._save_preferences()
            return True
        return False

    def get_all_preferences(self) -> dict[str, str]:
        """Get all manga source preferences.

        Returns:
            Dictionary mapping manga titles to source names
        """
        return self._preferences.copy()


# Global instance for use throughout the app
manga_source_preferences = MangaSourcePreferences()
