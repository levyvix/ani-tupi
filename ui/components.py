"""Reusable UI components: menu(), loading()

This module consolidates menu system and loading indicators:
- menu() / menu_navigate() - Interactive menus with InquirerPy
- loading() - Rich spinners for API calls
"""

import sys
from contextlib import contextmanager

from InquirerPy import inquirer  # type: ignore[import-untyped]
from InquirerPy.separator import Separator
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.theme import Theme
from utils.logging import get_logger

logger = get_logger(__name__)

# Catppuccin Mocha Theme
CATPPUCCIN_MOCHA = Theme(
    {
        "menu.title": "bold #cba6f7",  # Purple header
        "menu.text": "#cdd6f4",  # Light text
        "menu.highlight": "reverse #cba6f7",  # Inverted purple
        "menu.muted": "#6c7086",  # Muted gray
        "info": "#89dceb",  # Sky blue for info
        "success": "#a6e3a1",  # Green for success
        "warning": "#f9e2af",  # Yellow for warnings
        "error": "#f38ba8",  # Red for errors
    }
)

# Global console with theme
console = Console(theme=CATPPUCCIN_MOCHA)


def menu(
    opts: list[str],
    msg: str = "",
    enable_search: bool = True,
) -> str:
    """Display interactive menu with automatic "Sair" option.

    Args:
        opts: List of menu options
        msg: Title message
        enable_search: Enable fuzzy search (default: True)

    Returns:
        Selected option (without "Sair")

    Behavior:
        - Adds "Sair" automatically to the end
        - If "Sair" is selected → calls sys.exit()
        - Returns selected option
        - Q key exits to terminal immediately
        - Fuzzy search enabled by default

    """
    # Add "Sair" to options
    opts_copy = opts.copy()
    opts_copy.append("Sair")

    # Convert options to InquirerPy choices
    choices = []
    for opt in opts_copy:
        # Handle separators (lines starting with ─)
        if opt.startswith("─"):
            # Fuzzy search doesn't support separators, skip them
            if not enable_search:
                choices.append(Separator())
        else:
            choices.append(opt)

    # Display menu
    answer = None
    if enable_search:
        # Use fuzzy search for large menus
        answer = inquirer.fuzzy(  # type: ignore[attr-defined]
            message=msg or "Menu",
            choices=choices,
            default=None,
            qmark="",
            amark="►",
            pointer="►",
            instruction="(Type to search, Q to quit)",
            mandatory=False,
            keybindings={
                "skip": [
                    {"key": "Q"},
                ],
            },
            max_height="70%",
            raise_keyboard_interrupt=False,
        ).execute()
    else:
        # Use simple select for small menus
        answer = inquirer.select(  # type: ignore[attr-defined]
            message=msg or "Menu",
            choices=choices,
            default=None,
            qmark="",
            amark="►",
            pointer="►",
            instruction="(Use arrow keys, Q to quit)",
            mandatory=False,
            keybindings={
                "skip": [
                    {"key": "Q"},
                ],
            },
            raise_keyboard_interrupt=False,
        ).execute()

    # Handle result
    if answer == "Sair" or answer is None:
        # None means Q was pressed or skip was triggered
        sys.exit(0)

    return answer


def menu_navigate(
    opts: list[str],
    msg: str = "",
    enable_search: bool = True,
    search_state=None,
    alternative_language_available: bool = False,
    alternative_language_label: str | None = None,
) -> str | None:
    """Display interactive menu for navigation (returns None instead of exit).

    Args:
        opts: List of menu options (can include separators "─")
        msg: Title message
        enable_search: Enable fuzzy search (default: True)
        search_state: Optional IncrementalSearchState for navigation between result sets
        alternative_language_available: Whether language toggle button should be shown
        alternative_language_label: Label for language toggle button (e.g., "🔄 Re-buscar em Inglês")

    Returns:
        Selected option, special navigation commands ("__nav_previous__", "__nav_next__", "__research_language__"),
        or None if user cancels

    Behavior:
        - Adds navigation buttons: "← Voltar" (back), "Sair" (exit)
        - If search_state: adds "◀ Resultados Anteriores" and/or "▶ Próximos Resultados"
        - If alternative_language_available: adds language toggle button
        - "← Voltar" returns None (go back)
        - Navigation buttons return special commands for search flow handling
        - Language toggle button returns "__research_language__"
        - "Sair" exits to terminal
        - Q key exits to terminal immediately
        - Fuzzy search enabled by default

    """
    # Add navigation options
    opts_copy = opts.copy()

    # Add incremental search navigation if state is provided
    if search_state:
        if not enable_search:
            opts_copy.append("─" * 30)

        # Only show "◀ Resultados Anteriores" if previous iteration has DIFFERENT result count
        # This avoids confusion when filtering doesn't change the result set
        if search_state.has_previous():
            current_result = search_state.get_current()
            prev_result = search_state.search_history[search_state.current_index - 1]
            # Show button only if result count differs
            if current_result and len(current_result.results) != len(prev_result.results):
                opts_copy.append(
                    f"◀ Resultados Anteriores ({prev_result.word_count} palavras: {len(prev_result.results)} resultados)"
                )

        # Only show "▶ Próximos Resultados" if next iteration has DIFFERENT result count
        if search_state.has_next():
            current_result = search_state.get_current()
            next_result = search_state.search_history[search_state.current_index + 1]
            # Show button only if result count differs
            if current_result and len(current_result.results) != len(next_result.results):
                opts_copy.append(
                    f"▶ Próximos Resultados ({next_result.word_count} palavras: {len(next_result.results)} resultados)"
                )

    # Add language toggle button if available
    if alternative_language_available and alternative_language_label:
        if not (search_state or enable_search):
            opts_copy.append("─" * 30)
        opts_copy.append(alternative_language_label)

    if not enable_search and not search_state and not alternative_language_available:
        opts_copy.append("─" * 30)
    opts_copy.extend(["← Voltar", "Sair"])

    # Convert options to InquirerPy choices
    choices = []
    for opt in opts_copy:
        # Handle separators (lines starting with ─)
        if opt.startswith("─"):
            # Fuzzy search doesn't support separators, skip them
            if not enable_search:
                choices.append(Separator())
        else:
            choices.append(opt)

    # Display menu
    answer = None
    if enable_search:
        # Use fuzzy search for large menus
        answer = inquirer.fuzzy(  # type: ignore[attr-defined]
            message=msg or "Menu",
            choices=choices,
            default=None,
            qmark="",
            amark="►",
            pointer="►",
            instruction="(Type to search, Q to quit)",
            mandatory=False,
            keybindings={
                "skip": [
                    {"key": "Q"},
                ],
            },
            max_height="70%",
            raise_keyboard_interrupt=False,
        ).execute()
    else:
        # Use simple select for small menus
        answer = inquirer.select(  # type: ignore[attr-defined]
            message=msg or "Menu",
            choices=choices,
            default=None,
            qmark="",
            amark="►",
            pointer="►",
            instruction="(Use arrow keys, Q to quit)",
            mandatory=False,
            keybindings={
                "skip": [
                    {"key": "Q"},
                ],
            },
            raise_keyboard_interrupt=False,
        ).execute()

    # Handle special options
    if answer == "← Voltar" or answer is None:
        # Voltar selected or Q pressed (skip binding) - go back
        return None

    if answer == "Sair":
        # Sair selected - exit program
        sys.exit(0)

    # Handle incremental search navigation
    if search_state:
        if answer and answer.startswith("◀ Resultados Anteriores"):
            return "__nav_previous__"
        if answer and answer.startswith("▶ Próximos Resultados"):
            return "__nav_next__"

    # Handle language toggle
    if alternative_language_available and answer == alternative_language_label:
        return "__research_language__"

    # Return selection (filter out the added options)
    return answer


def menu_navigate_episodes(
    episode_numbers: list[int], msg: str = "Escolha o episódio."
) -> int | None:
    """Show an episode menu from a list of episode numbers.

    Episode lists are stored as plain ints; this renders them as "Episódio N"
    labels for selection and maps the choice back to its 0-based index.

    Args:
        episode_numbers: Episode numbers to display
        msg: Title message for the menu

    Returns:
        0-based index of the selected episode, or None if the user goes back/cancels.
    """
    labels = [f"Episódio {n}" for n in episode_numbers]
    selected = menu_navigate(labels, msg=msg)
    if not selected:
        return None
    return labels.index(selected)


@contextmanager
def loading(msg: str = "Carregando..."):
    """Context manager for displaying loading indicators during operations.

    Args:
        msg: The message to display alongside the spinner

    Usage:
        with loading("Buscando animes..."):
            results = fetch_anime()

    """
    with Live(
        Spinner("arc", text=msg),
        console=console,
        refresh_per_second=12.5,
        transient=True,  # Spinner disappears after completion
    ):
        yield


if __name__ == "__main__":
    # Test the menu
    test_options = [
        "Opção 1",
        "Opção 2",
        "Opção 3 com nome bem longo para testar",
        "─" * 30,
        "Opção 4",
        "Opção 5",
    ]

    console.logger.info("\n[menu.title]Testando menu()[/menu.title]")
    selection = menu(test_options, "Menu de Teste")
    console.logger.info(f"\n[success]Selecionado: {selection}[/success]")
