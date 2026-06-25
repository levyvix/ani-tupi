"""Range parser utility for manga chapter selection.

Parses user input for chapter range selection and returns list of chapter numbers.

Supported patterns:
- "5" → Next 5 chapters after last_chapter (or from 1 if no history)
- "3-10" → Chapters 3 through 10 (exact range)
- "all" → All available chapters
- "" (empty) → Use default (5 chapters)
"""

from typing import Optional


def _safe_float(value: str) -> float | None:
    """Convert string to float, returning None for non-numeric values like 'extra', 'bonus'."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def parse_range_input(
    user_input: str,
    last_chapter: Optional[str] = None,
    available_chapters: Optional[list[str]] = None,
    default_count: int = 5,
) -> list[str]:
    """Parse user range input and return list of chapter numbers to download.

    Args:
        user_input: User input string (e.g., "5", "3-10", "all", "")
        last_chapter: Last read chapter number (e.g., "41", "42.5")
        available_chapters: List of available chapter numbers in order
        default_count: Default number of chapters to download if input is empty

    Returns:
        List of chapter numbers to download (e.g., ["42", "43", "44", "45", "46"])

    Raises:
        ValueError: If input format is invalid or out of range
    """
    if available_chapters is None:
        available_chapters = []

    # Handle empty input - use default
    user_input = user_input.strip()
    if not user_input:
        return _get_default_range(last_chapter, available_chapters, default_count)

    # Handle "all" keyword
    if user_input.lower() == "all":
        if last_chapter:
            # Return chapters after last_chapter
            try:
                last_num = float(last_chapter)
            except (ValueError, TypeError):
                return available_chapters
            return [
                ch
                for ch in available_chapters
                if (v := _safe_float(ch)) is not None and v > last_num
            ]
        else:
            # Return all available
            return available_chapters

    # Handle range format "3-10"
    if "-" in user_input:
        return _parse_range_format(user_input, available_chapters)

    # Handle count format "5"
    try:
        count = int(user_input)
        if count <= 0:
            raise ValueError(f"Count must be positive, got: {count}")
        if count > len(available_chapters):
            raise ValueError(
                f"Requested {count} chapters but only {len(available_chapters)} available"
            )
        return _get_offset_range(last_chapter, available_chapters, count)
    except ValueError as e:
        if "Count must be positive" in str(e) or "Requested" in str(e):
            raise
        raise ValueError(f"Invalid range format: '{user_input}'. Use: '5', '3-10', 'all', or empty")


def _get_default_range(
    last_chapter: Optional[str],
    available_chapters: list[str],
    default_count: int,
) -> list[str]:
    """Get default range of chapters.

    Args:
        last_chapter: Last read chapter
        available_chapters: Available chapters
        default_count: Number of chapters to return

    Returns:
        List of chapter numbers
    """
    if not available_chapters:
        return []

    if last_chapter:
        # Return next N chapters after last_chapter
        try:
            last_num = float(last_chapter)
        except (ValueError, TypeError):
            return available_chapters[:default_count]
        chapters_after = [
            ch for ch in available_chapters if (v := _safe_float(ch)) is not None and v > last_num
        ]
        return chapters_after[:default_count]
    else:
        # Return first N chapters
        return available_chapters[:default_count]


def _get_offset_range(
    last_chapter: Optional[str],
    available_chapters: list[str],
    count: int,
) -> list[str]:
    """Get N chapters starting from last_chapter + 1.

    Args:
        last_chapter: Last read chapter (e.g., "41", "42.5")
        available_chapters: Available chapters list
        count: Number of chapters to return

    Returns:
        List of chapter numbers
    """
    if not available_chapters:
        return []

    if not last_chapter:
        # No history, return first N chapters
        return available_chapters[:count]

    # Find chapters after last_chapter
    try:
        last_num = float(last_chapter)
    except (ValueError, TypeError):
        return available_chapters[:count]
    chapters_after = [
        ch for ch in available_chapters if (v := _safe_float(ch)) is not None and v > last_num
    ]

    if not chapters_after:
        raise ValueError(f"No chapters available after chapter {last_chapter}")

    return chapters_after[:count]


def _parse_range_format(user_input: str, available_chapters: list[str]) -> list[str]:
    """Parse range format "3-10" and return matching chapters.

    Args:
        user_input: Range string like "3-10"
        available_chapters: Available chapters list

    Returns:
        List of matching chapters

    Raises:
        ValueError: If range format is invalid
    """
    parts = user_input.split("-")
    if len(parts) != 2:
        raise ValueError(f"Invalid range format: '{user_input}'. Use: 'start-end'")

    try:
        start = float(parts[0].strip())
        end = float(parts[1].strip())
    except ValueError:
        raise ValueError(f"Range bounds must be numbers: '{user_input}'")

    if start > end:
        raise ValueError(f"Range start ({start}) cannot be greater than end ({end})")

    if start < 0 or end < 0:
        raise ValueError(f"Range values must be non-negative: '{user_input}'")

    # Find chapters within range
    result = []
    for ch in available_chapters:
        v = _safe_float(ch)
        if v is not None and start <= v <= end:
            result.append(ch)

    if not result:
        raise ValueError(f"No chapters found in range {start}-{end}")

    return result
