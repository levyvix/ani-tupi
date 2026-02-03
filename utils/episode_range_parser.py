"""Episode range parser for download selection.

Parses user input for episode ranges with flexible formats:
- "1-12": Episodes 1 through 12
- "5": Single episode 5
- "5-": Episodes 5 through end
- "-12": Episodes 1 through 12
- "5-15": Episodes 5 through 15

Validates against total episode count and raises errors for invalid input.
"""


class RangeParseError(ValueError):
    """Raised when range parsing fails."""

    pass


def parse_episode_range(user_input: str, total_episodes: int) -> list[int]:
    """Parse episode range from user input.

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

        # Handle cases like "5-" or "-12" or "5-15"
        if len(parts) == 2:
            start_str, end_str = parts
            start = None
            end = None

            # Parse start
            if start_str:
                try:
                    start = int(start_str)
                except ValueError:
                    raise RangeParseError(f"Início do intervalo não é número: {start_str}")

                if start < 1:
                    raise RangeParseError(f"Episódio deve ser >= 1, recebido: {start}")

            # Parse end
            if end_str:
                try:
                    end = int(end_str)
                except ValueError:
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
                raise RangeParseError(
                    f"Intervalo invertido: {actual_start}-{actual_end} (start > end)"
                )

            return list(range(actual_start, actual_end + 1))

        else:
            # Multiple dashes like "1-5-10"
            raise RangeParseError(f"Intervalo inválido: múltiplos '-' encontrados em: {user_input}")

    else:
        # Single episode
        try:
            episode = int(user_input)
        except ValueError:
            raise RangeParseError(f"Episódio não é número: {user_input}")

        if episode < 1:
            raise RangeParseError(f"Episódio deve ser >= 1, recebido: {episode}")

        if episode > total_episodes:
            raise RangeParseError(
                f"Episódio {episode} fora do intervalo (máximo: {total_episodes})"
            )

        return [episode]


def validate_episode_range(episodes: list[int], total_episodes: int) -> bool:
    """Validate that all episodes are within valid range.

    Args:
        episodes: List of episode numbers to validate
        total_episodes: Total number of episodes available

    Returns:
        True if all episodes are valid (1 <= ep <= total_episodes)

    Raises:
        RangeParseError: If any episode is out of bounds
    """
    if not episodes:
        raise RangeParseError("Lista de episódios está vazia")

    for episode in episodes:
        if episode < 1 or episode > total_episodes:
            raise RangeParseError(f"Episódio {episode} fora do intervalo (1-{total_episodes})")

    return True
