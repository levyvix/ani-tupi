"""Reusable UI components: menu(), loading()

This module consolidates menu system and loading indicators:
- menu() / menu_navigate() - Interactive menus with InquirerPy
- loading() - Rich spinners for API calls
"""

import sys
from collections.abc import Callable
from contextlib import contextmanager

from InquirerPy import inquirer
from InquirerPy.separator import Separator
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.theme import Theme

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
    show_preview: bool = False,
    preview_callback: Callable | None = None,
    enable_search: bool = True,
) -> str:
    """Display interactive menu with automatic "Sair" option.

    Args:
        opts: List of menu options
        msg: Title message
        show_preview: Ignored (preview feature removed in refactor)
        preview_callback: Ignored (preview feature removed in refactor)
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
        answer = inquirer.fuzzy(
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
                    {"key": "q"},
                    {"key": "Q"},
                ],
            },
            max_height="70%",
            raise_keyboard_interrupt=False,
        ).execute()
    else:
        # Use simple select for small menus
        answer = inquirer.select(
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
                    {"key": "q"},
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
    show_preview: bool = False,
    preview_callback: Callable | None = None,
    enable_search: bool = True,
) -> str | None:
    """Display interactive menu for navigation (returns None instead of exit).

    Args:
        opts: List of menu options (can include separators "─")
        msg: Title message
        show_preview: Ignored (preview feature removed in refactor)
        preview_callback: Ignored (preview feature removed in refactor)
        enable_search: Enable fuzzy search (default: True)

    Returns:
        Selected option or None if user cancels

    Behavior:
        - Adds "← Voltar" and "Sair" automatically
        - "← Voltar" returns None (go back)
        - "Sair" exits to terminal
        - Q key exits to terminal immediately
        - Fuzzy search enabled by default

    """
    # Add navigation options
    opts_copy = opts.copy()
    if not enable_search:
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
        answer = inquirer.fuzzy(
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
                    {"key": "q"},
                    {"key": "Q"},
                ],
            },
            max_height="70%",
            raise_keyboard_interrupt=False,
        ).execute()
    else:
        # Use simple select for small menus
        answer = inquirer.select(
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
                    {"key": "q"},
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

    # Return selection (filter out the added options)
    return answer


@contextmanager
def loading(msg: str = "Carregando..."):
    """Context manager for displaying loading indicators during operations.

    Args:
        msg: The message to display alongside the spinner

    Usage:
        with loading("Buscando animes..."):
            results = fetch_anime()

    """
    console_instance = Console()

    with Live(
        Spinner("dots", text=msg),
        console=console_instance,
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

    console.print("\n[menu.title]Testando menu()[/menu.title]")
    selection = menu(test_options, "Menu de Teste")
    console.print(f"\n[success]Selecionado: {selection}[/success]")
