"""Anime title normalization and utility functions.

Consolidates all title normalization logic in a single module for consistency.
Used for improving search accuracy and handling title variations.
"""

import re


def normalize_title_for_search(title: str) -> str:
    """Normalize anime title for search operations.

    Removes common Portuguese suffixes and normalizes spacing.
    Used internally by search algorithms to improve matching.

    Args:
        title: Original anime title (may contain suffixes like Dublado, Legendado)

    Returns:
        Normalized title for search

    Examples:
        "Tougen Anki (Dublado)" -> "tougen anki"
        "Dandadan 2ª Temporada Legendado" -> "dandadan 2ª temporada"
    """
    # Remove common Portuguese suffixes in parentheses
    title = re.sub(
        r"\s*\((Dublado|Legendado|Completo|Dual Audio|PT-BR)\)\s*",
        "",
        title,
        flags=re.IGNORECASE,
    )
    # Remove standalone suffixes at the end
    title = re.sub(
        r"\s+(Dublado|Legendado|Completo|Dual Audio|PT-BR)\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    # Normalize whitespace and convert to lowercase for comparison
    title = re.sub(r"\s+", " ", title.strip().lower())
    return title


def clean_title_for_display(title: str) -> str:
    """Clean title for display purposes (preserves case, removes only extra whitespace).

    Args:
        title: Original anime title

    Returns:
        Cleaned title with normalized whitespace
    """
    # Remove common Portuguese suffixes in parentheses
    title = re.sub(
        r"\s*\((Dublado|Legendado|Completo|Dual Audio|PT-BR)\)\s*",
        "",
        title,
        flags=re.IGNORECASE,
    )
    # Remove standalone suffixes at the end
    title = re.sub(
        r"\s+(Dublado|Legendado|Completo|Dual Audio|PT-BR)\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    # Normalize whitespace (keep case)
    title = re.sub(r"\s+", " ", title.strip())
    return title


def generate_search_variations(title: str) -> list[str]:
    """Generate title variations for searching when exact match fails.

    Progressively removes words from title to create simpler search terms.

    Args:
        title: Original anime title

    Returns:
        List of title variations from longest to shortest

    Examples:
        "Dandadan 2ª Temporada Dublado" -> ["dandadan 2ª temporada", "dandadan 2ª", "dandadan"]
    """
    cleaned = normalize_title_for_search(title)
    words = cleaned.split()

    if not words:
        return [cleaned]

    # Start with full title, progressively remove words from the end
    variations = []
    for i in range(len(words), 0, -1):
        variation = " ".join(words[:i])
        if variation and variation not in variations:
            variations.append(variation)

    return variations if variations else [cleaned]


def normalize_for_internal_filter(title: str) -> str:
    """Normalize title for internal filtering operations (Repository state).

    Used for matching titles against cached results, comparing anime entries.
    More aggressive normalization for reliable comparison.

    Args:
        title: Title to normalize

    Returns:
        Normalized title for filter operations
    """
    # Remove special characters except spaces and common punctuation
    title = re.sub(r"[^\w\s\-()ªº]", "", title)
    # Remove common suffixes
    title = normalize_title_for_search(title)
    return title
