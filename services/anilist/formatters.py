"""Title formatting utilities for AniList data.

Handles conversion of AniList title objects to display and search strings.
"""

from models.models import AniListTitle
from utils.title_utils import normalize_title_for_filter


def format_title(title_obj: AniListTitle | dict) -> str:
    """Format title object to single string.

    Shows romaji + english when both available.

    Args:
        title_obj: AniListTitle model or dict with romaji/english/native fields

    Returns:
        Formatted title string
    """
    # Handle both Pydantic model and dict for backward compatibility
    if isinstance(title_obj, dict):
        romaji = title_obj.get("romaji")
        english = title_obj.get("english")
        native = title_obj.get("native")
    else:
        romaji = title_obj.romaji
        english = title_obj.english
        native = title_obj.native

    # If both romaji and english exist and are different after normalization
    if (
        romaji
        and english
        and normalize_title_for_filter(romaji) != normalize_title_for_filter(english)
    ):
        return f"{romaji} / {english}"
    # If only romaji
    if romaji:
        return romaji
    # If only english
    if english:
        return english
    # Fallback to native
    return native or "Unknown"


def get_search_title(title_obj: AniListTitle | dict) -> str:
    """Extract title for scraper search (English only).

    Returns English title if available, otherwise romaji or native.
    Used for scraper queries to ensure consistent results.

    Args:
        title_obj: AniListTitle model or dict with romaji/english/native fields

    Returns:
        Search-optimized title string (English preferred)
    """
    # Handle both Pydantic model and dict for backward compatibility
    if isinstance(title_obj, dict):
        english = title_obj.get("english")
        romaji = title_obj.get("romaji")
        native = title_obj.get("native")
    else:
        english = title_obj.english
        romaji = title_obj.romaji
        native = title_obj.native

    # Prefer English for scraper searches (most reliable for searches)
    if english:
        return english
    # If only romaji
    if romaji:
        return romaji
    # Fallback to native
    return native or "Unknown"
