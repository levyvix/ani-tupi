"""JSON file persistence utilities.

Provides a unified interface for loading/saving JSON data files
with consistent error handling and directory creation.
"""

from json import dump, load
from pathlib import Path
from typing import Any

from utils.exceptions import PersistenceError


class JSONStore:
    """Manages JSON file persistence with automatic directory creation and error handling.

    Provides a consistent interface for loading and saving JSON data,
    handles missing files, serialization errors, and file permissions gracefully.
    """

    def __init__(self, file_path: Path) -> None:
        """Initialize JSONStore with a file path.

        Args:
            file_path: Path to the JSON file to manage
        """
        self.file_path = Path(file_path)

    def load(self, default: Any = None) -> Any:
        """Load JSON data from file.

        Args:
            default: Value to return if file doesn't exist or is invalid.
                    Defaults to empty dict.

        Returns:
            Loaded JSON data, or default value if file doesn't exist/is invalid

        Raises:
            PersistenceError: On permission errors (won't auto-create file)
        """
        if default is None:
            default = {}

        try:
            with self.file_path.open() as f:
                return load(f)
        except FileNotFoundError:
            return default
        except ValueError as e:
            # JSON decode error
            return default
        except PermissionError as e:
            raise PersistenceError(f"Permission denied reading {self.file_path}") from e

    def save(self, data: Any, *, indent: int = 2) -> None:
        """Save JSON data to file.

        Creates parent directories if they don't exist.

        Args:
            data: Data to serialize to JSON
            indent: JSON indentation level (default 2)

        Raises:
            PersistenceError: On serialization or permission errors
        """
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("w") as f:
                dump(data, f, indent=indent)
        except TypeError as e:
            raise PersistenceError(f"Cannot serialize data: {e}") from e
        except PermissionError as e:
            raise PersistenceError(f"Permission denied writing {self.file_path}") from e

    def get(self, key: str, default: Any = None) -> Any:
        """Load JSON file and get a specific key.

        Args:
            key: Key to retrieve from loaded JSON dict
            default: Value to return if key doesn't exist

        Returns:
            Value at key, or default if missing
        """
        data = self.load({})
        return data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Load JSON file, update a key, and save back.

        Args:
            key: Key to update
            value: Value to set
        """
        data = self.load({})
        data[key] = value
        self.save(data)

    def update(self, updates: dict) -> None:
        """Load JSON file, update multiple keys, and save back.

        Args:
            updates: Dict of key-value pairs to update
        """
        data = self.load({})
        data.update(updates)
        self.save(data)

    def delete(self, key: str) -> None:
        """Load JSON file, delete a key, and save back.

        Args:
            key: Key to delete (silently succeeds if key doesn't exist)
        """
        data = self.load({})
        data.pop(key, None)
        self.save(data)

    def exists(self) -> bool:
        """Check if JSON file exists.

        Returns:
            True if file exists and is readable
        """
        return self.file_path.exists()

    def clear(self) -> None:
        """Clear all data from the JSON file."""
        self.save({})
