"""Generic range parser utilities.

This module hosts a single, generic range-parsing core plus two public
entry points that reproduce the historical behaviors exactly:

- ``parse_range_input``  → manga chapter selection (float-based, works against
  a list of available chapter numbers, supports count / "all" / defaults).
- ``parse_episode_range`` → anime episode selection (int-based, clamps to a
  total episode count, supports open ranges like "5-" and "-12").

The genuinely shared logic — splitting a ``"start-end"`` string into numeric
bounds with a configurable numeric conversion — lives in
``_split_range_bounds`` and is used by both entry points.
"""

from collections.abc import Callable
from typing import TypeVar

N = TypeVar("N", int, float)


class RangeParseError(ValueError):
    """Raised when range parsing fails."""

    pass


def _safe_number(value: str, number_type: Callable[[str], N]) -> N | None:
    """Convert string to the given numeric type, returning None on failure.

    Used for values like 'extra' or 'bonus' that are not numeric.
    """
    try:
        return number_type(value)
    except (ValueError, TypeError):
        return None


def _split_range_bounds(
    user_input: str,
    number_type: Callable[[str], N],
) -> tuple[N, N]:
    """Split a ``"start-end"`` string into two numeric bounds.

    Both sides must be present and convertible with ``number_type``.

    Args:
        user_input: Range string containing exactly one ``-`` separator.
        number_type: Numeric conversion callable (``int`` or ``float``).

    Returns:
        Tuple ``(start, end)`` of converted numeric bounds.

    Raises:
        ValueError: With message ``"multiple-dashes"`` when the input does not
            contain exactly one separator, or the conversion error from
            ``number_type`` when a bound is not numeric. Callers translate these
            into their own user-facing messages.
    """
    parts = user_input.split("-")
    if len(parts) != 2:
        raise ValueError("multiple-dashes")

    start_str, end_str = parts[0].strip(), parts[1].strip()
    return number_type(start_str), number_type(end_str)


def parse_range_input(
    user_input: str,
    last_chapter: str | None = None,
    available_chapters: list[str] | None = None,
    default_count: int = 5,
) -> list[str]:
    """Parse user range input and return list of chapter numbers to download.

    Supported patterns:
    - "5" → Next 5 chapters after last_chapter (or from 1 if no history)
    - "3-10" → Chapters 3 through 10 (exact range)
    - "all" → All available chapters
    - "" (empty) → Use default (default_count chapters)

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
            last_num = _safe_number(last_chapter, float)
            if last_num is None:
                return available_chapters
            return [
                ch
                for ch in available_chapters
                if (v := _safe_number(ch, float)) is not None and v > last_num
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
    last_chapter: str | None,
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
        last_num = _safe_number(last_chapter, float)
        if last_num is None:
            return available_chapters[:default_count]
        chapters_after = [
            ch
            for ch in available_chapters
            if (v := _safe_number(ch, float)) is not None and v > last_num
        ]
        return chapters_after[:default_count]
    else:
        # Return first N chapters
        return available_chapters[:default_count]


def _get_offset_range(
    last_chapter: str | None,
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
    last_num = _safe_number(last_chapter, float)
    if last_num is None:
        return available_chapters[:count]
    chapters_after = [
        ch
        for ch in available_chapters
        if (v := _safe_number(ch, float)) is not None and v > last_num
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
    try:
        start, end = _split_range_bounds(user_input, float)
    except ValueError as e:
        if str(e) == "multiple-dashes":
            raise ValueError(f"Invalid range format: '{user_input}'. Use: 'start-end'")
        raise ValueError(f"Range bounds must be numbers: '{user_input}'")

    if start > end:
        raise ValueError(f"Range start ({start}) cannot be greater than end ({end})")

    if start < 0 or end < 0:
        raise ValueError(f"Range values must be non-negative: '{user_input}'")

    # Find chapters within range
    result = []
    for ch in available_chapters:
        v = _safe_number(ch, float)
        if v is not None and start <= v <= end:
            result.append(ch)

    if not result:
        raise ValueError(f"No chapters found in range {start}-{end}")

    return result


def parse_episode_range(user_input: str, total_episodes: int) -> list[int]:
    """Parse episode range from user input.

    Parses user input for episode ranges with flexible formats:
    - "1-12": Episodes 1 through 12
    - "5": Single episode 5
    - "5-": Episodes 5 through end
    - "-12": Episodes 1 through 12
    - "5-15": Episodes 5 through 15

    Args:
        user_input: User-provided range string (e.g., "1-12", "5", "5-", "-12")
        total_episodes: Total number of episodes available

    Returns:
        List of episode numbers (1-indexed, sorted, no duplicates)

    Raises:
        RangeParseError: If input is invalid, non-numeric, reversed, or out-of-bounds

    Examples:
        >>> parse_episode_range("1-12", 12)
        [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

        >>> parse_episode_range("5", 24)
        [5]

        >>> parse_episode_range("5-", 12)
        [5, 6, 7, 8, 9, 10, 11, 12]

        >>> parse_episode_range("-12", 24)
        [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

        >>> parse_episode_range("5-15", 24)
        [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    """
    if not user_input or not isinstance(user_input, str):
        raise RangeParseError("Intervalo inválido: entrada vazia ou não é texto")

    user_input = user_input.strip()

    if not user_input:
        raise RangeParseError("Intervalo inválido: entrada vazia")

    if total_episodes <= 0:
        raise RangeParseError("Total de episódios deve ser maior que 0")

    # Check for range operator
    if "-" in user_input:
        parts = user_input.split("-")

        # Multiple dashes like "1-5-10"
        if len(parts) != 2:
            raise RangeParseError(f"Intervalo inválido: múltiplos '-' encontrados em: {user_input}")

        start_str, end_str = parts
        start = None
        end = None

        # Parse start (validating incrementally, matching historical order)
        if start_str:
            start = _safe_number(start_str, int)
            if start is None:
                raise RangeParseError(f"Início do intervalo não é número: {start_str}")
            if start < 1:
                raise RangeParseError(f"Episódio deve ser >= 1, recebido: {start}")

        # Parse end
        if end_str:
            end = _safe_number(end_str, int)
            if end is None:
                raise RangeParseError(f"Fim do intervalo não é número: {end_str}")
            if end < 1:
                raise RangeParseError(f"Episódio deve ser >= 1, recebido: {end}")

        # Determine actual start and end
        if start is None and end is None:
            raise RangeParseError("Intervalo inválido: '-' sozinho")

        actual_start = start if start is not None else 1
        actual_end = end if end is not None else total_episodes

        # Clamp to valid range
        actual_start = max(1, min(actual_start, total_episodes))
        actual_end = max(1, min(actual_end, total_episodes))

        # Check if reversed
        if actual_start > actual_end:
            raise RangeParseError(f"Intervalo invertido: {actual_start}-{actual_end} (start > end)")

        return list(range(actual_start, actual_end + 1))

    else:
        # Single episode
        episode = _safe_number(user_input, int)
        if episode is None:
            raise RangeParseError(f"Episódio não é número: {user_input}")

        if episode < 1:
            raise RangeParseError(f"Episódio deve ser >= 1, recebido: {episode}")

        if episode > total_episodes:
            raise RangeParseError(
                f"Episódio {episode} fora do intervalo (máximo: {total_episodes})"
            )

        return [episode]
