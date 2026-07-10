"""Manga selection preferences manager.

Handles persisting and retrieving user's preferred manga version when multiple
results are found for the same search query (e.g., different scanlations).
"""

import json

from models.config import get_data_path


class MangaSelectionPreferences:
    """Manages manga selection preferences with JSON persistence."""

    def __init__(self):
        """Initialize preferences manager."""
        self.preferences_file = get_data_path() / "manga_selection_preferences.json"
        self._preferences: dict[str, str] = {}  # search_query -> manga_id
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

    def get_preferred_manga_id(self, search_query: str) -> str | None:
        """Get preferred manga ID for a search query.

        Args:
            search_query: The original search query

        Returns:
            Preferred manga ID or None if not set
        """
        # Normalize query for consistent matching
        normalized_query = search_query.strip().lower()
        return self._preferences.get(normalized_query)

    def set_preferred_manga_id(self, search_query: str, manga_id: str) -> None:
        """Set preferred manga ID for a search query.

        Args:
            search_query: The original search query
            manga_id: The manga ID to prefer
        """
        # Normalize query for consistent matching
        normalized_query = search_query.strip().lower()
        self._preferences[normalized_query] = manga_id
        self._save_preferences()

    def remove_preference(self, search_query: str) -> bool:
        """Remove preference for a search query.

        Args:
            search_query: The search query

        Returns:
            True if preference was removed, False if not found
        """
        normalized_query = search_query.strip().lower()
        if normalized_query in self._preferences:
            del self._preferences[normalized_query]
            self._save_preferences()
            return True
        return False

    def get_all_preferences(self) -> dict[str, str]:
        """Get all manga selection preferences.

        Returns:
            Dictionary mapping search queries to manga IDs
        """
        return self._preferences.copy()


# Global instance for use throughout the app
manga_selection_preferences = MangaSelectionPreferences()
