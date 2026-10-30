"""Persisted per-query manga selection and source preferences."""

import json

from models.config import get_data_path


class _JsonPreferences:
    """Persist normalized string keys and values in a small JSON file."""

    def __init__(self, filename: str, data_path_getter=None) -> None:
        data_path_getter = data_path_getter or get_data_path
        self.preferences_file = data_path_getter() / filename
        self._preferences: dict[str, str] = {}
        self._load_preferences()

    def _load_preferences(self) -> None:
        try:
            if self.preferences_file.exists():
                with self.preferences_file.open("r", encoding="utf-8") as file:
                    data = json.load(file)
                if isinstance(data, dict):
                    self._preferences = {str(key): str(value) for key, value in data.items()}
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            self._preferences = {}

    def _save_preferences(self) -> None:
        try:
            self.preferences_file.parent.mkdir(parents=True, exist_ok=True)
            with self.preferences_file.open("w", encoding="utf-8") as file:
                json.dump(self._preferences, file, indent=2, ensure_ascii=False)
        except OSError:
            # Preferences are optional; a read-only state directory should not
            # prevent searching or reading manga.
            pass

    @staticmethod
    def _normalize_key(key: str) -> str:
        return key.strip().lower()

    def get(self, key: str) -> str | None:
        return self._preferences.get(self._normalize_key(key))

    def set(self, key: str, value: str) -> None:
        self._preferences[self._normalize_key(key)] = value
        self._save_preferences()

    def remove(self, key: str) -> bool:
        normalized_key = self._normalize_key(key)
        if normalized_key not in self._preferences:
            return False
        del self._preferences[normalized_key]
        self._save_preferences()
        return True

    def all(self) -> dict[str, str]:
        return self._preferences.copy()


class MangaSelectionPreferences(_JsonPreferences):
    """Manage the preferred manga for each search query."""

    def __init__(self, data_path_getter=None) -> None:
        super().__init__("manga_selection_preferences.json", data_path_getter)

    def get_preferred_manga_id(self, search_query: str) -> str | None:
        return self.get(search_query)

    def set_preferred_manga_id(self, search_query: str, manga_id: str) -> None:
        self.set(search_query, manga_id)

    def remove_preference(self, search_query: str) -> bool:
        return self.remove(search_query)

    def get_all_preferences(self) -> dict[str, str]:
        return self.all()


class MangaSourcePreferences(_JsonPreferences):
    """Manage the preferred source for each manga."""

    def __init__(self, data_path_getter=None) -> None:
        super().__init__("manga_source_preferences.json", data_path_getter)

    def get_preferred_source(self, manga_title: str) -> str | None:
        return self.get(manga_title)

    def set_preferred_source(self, manga_title: str, source: str) -> None:
        self.set(manga_title, source)

    def remove_preference(self, manga_title: str) -> bool:
        return self.remove(manga_title)

    def get_all_preferences(self) -> dict[str, str]:
        return self.all()


manga_selection_preferences = MangaSelectionPreferences()

manga_source_preferences = MangaSourcePreferences()

__all__ = ["MangaSelectionPreferences", "MangaSourcePreferences"]
