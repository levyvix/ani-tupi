"""
Rich + InquirerPy based menu system for ani-tupi
Modern, responsive TUI with Catppuccin theme
"""

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.separator import Separator
from rich.console import Console
from rich.theme import Theme
from typing import Optional, Callable
import sys


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
    preview_callback: Optional[Callable] = None,
) -> str:
    """
    Display interactive menu with automatic "Sair" option

    Args:
        opts: List of menu options
        msg: Title message
        show_preview: Ignored (preview feature removed in refactor)
        preview_callback: Ignored (preview feature removed in refactor)

    Returns:
        Selected option (without "Sair")

    Behavior:
        - Adds "Sair" automatically to the end
        - If "Sair" is selected → calls sys.exit()
        - Returns selected option
        - Q key exits to terminal immediately
        - ESC or Ctrl+C also exits to terminal
    """
    # Add "Sair" to options
    opts_copy = opts.copy()
    opts_copy.append("Sair")

    # Convert options to InquirerPy choices
    choices = []
    for opt in opts_copy:
        # Handle separators (lines starting with ─)
        if opt.startswith("─"):
            choices.append(Separator())
        else:
            choices.append(opt)

    # Display menu
    try:
        answer = inquirer.select(
            message=msg or "Menu",
            choices=choices,
            default=None,
            qmark="",  # Remove question mark prefix
            amark="►",  # Arrow for selected item
            pointer="►",  # Pointer for highlighted item
            instruction="(Use arrow keys, Q to quit, ESC to back)",
            keybindings={
                "skip": [{"key": "q"}, {"key": "Q"}],  # Q to quit (returns None via skip)
            },
        ).execute()
    except KeyboardInterrupt:
        # ESC or Ctrl+C pressed - also quit for main menu
        sys.exit(0)

    # Handle result
    if answer == "Sair" or answer is None:
        # None means Q was pressed (skip binding)
        sys.exit(0)

    return answer


def menu_navigate(
    opts: list[str],
    msg: str = "",
    show_preview: bool = False,
    preview_callback: Optional[Callable] = None,
) -> Optional[str]:
    """
    Display interactive menu for navigation (returns None instead of exit)

    Args:
        opts: List of menu options (can include separators "─")
        msg: Title message
        show_preview: Ignored (preview feature removed in refactor)
        preview_callback: Ignored (preview feature removed in refactor)

    Returns:
        Selected option or None if user cancels

    Behavior:
        - Does NOT add "Sair" automatically
        - ESC returns None (go back to previous menu)
        - Q key exits to terminal immediately
        - Ctrl+C also exits to terminal
        - Allows navigation without exiting program
    """
    # Convert options to InquirerPy choices
    choices = []
    for opt in opts:
        # Handle separators (lines starting with ─)
        if opt.startswith("─"):
            choices.append(Separator())
        else:
            choices.append(opt)

    # Display menu
    try:
        answer = inquirer.select(
            message=msg or "Menu",
            choices=choices,
            default=None,
            qmark="",  # Remove question mark prefix
            amark="►",  # Arrow for selected item
            pointer="►",  # Pointer for highlighted item
            instruction="(Use arrow keys, Q to quit, ESC to back)",
            keybindings={
                "skip": [{"key": "q"}, {"key": "Q"}],  # Q to quit (returns None via skip)
            },
        ).execute()
    except KeyboardInterrupt:
        # ESC or Ctrl+C pressed - go back (return None for navigation)
        return None

    # Handle Q key (skip binding returns None)
    if answer is None:
        sys.exit(0)

    # Return selection
    return answer


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
