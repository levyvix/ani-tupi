"""
Simple TUI using Rich + inquirer-py

Replaces complex Textual architecture with straightforward, synchronous menus.
No more terminal flicker, no app stacking, no event-driven complexity.
"""

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress
from inquirer import prompt, List, Confirm
from typing import Optional, List as ListType
import sys

console = Console()

# Logger for status messages
class SimpleLogger:
    """Simple logger using Rich console"""

    def log(self, msg: str, style: str = "white"):
        """Log a message"""
        console.print(msg, style=style)

    def info(self, msg: str):
        """Log info message"""
        self.log(f"ℹ️  {msg}", style="blue")

    def success(self, msg: str):
        """Log success message"""
        self.log(f"✅ {msg}", style="green")

    def error(self, msg: str):
        """Log error message"""
        self.log(f"❌ {msg}", style="red")

    def progress(self, msg: str):
        """Log progress message"""
        self.log(f"🔍 {msg}", style="yellow")


logger = SimpleLogger()


def menu(
    options: ListType[str],
    title: str = "Menu",
    show_exit: bool = True,
) -> Optional[str]:
    """
    Display a menu and return user selection.

    Args:
        options: List of menu options
        title: Menu title to display
        show_exit: Whether to add "Sair" (Exit) option

    Returns:
        Selected option or None if user exits
    """
    # Add "Sair" option if requested
    menu_options = options.copy()
    if show_exit:
        menu_options.append("Sair")

    # Filter out separators for the inquirer prompt
    inquirer_options = [opt for opt in menu_options if not opt.startswith("─")]

    if not inquirer_options:
        logger.error("Nenhuma opção disponível")
        return None

    # Display title
    if title and title != "Menu":
        console.print(f"\n[bold yellow]{title}[/bold yellow]")

    # Show menu with inquirer
    questions = [
        List(
            "selection",
            message="Escolha uma opção:",
            choices=inquirer_options,
            carousel=True,
        )
    ]

    try:
        answers = prompt(questions)
        result = answers.get("selection")

        # Handle "Sair" (exit)
        if result == "Sair":
            return None

        return result
    except (KeyboardInterrupt, EOFError):
        return None


def menu_navigate(
    options: ListType[str],
    title: str = "Menu",
) -> Optional[str]:
    """
    Display a navigation menu (no auto-exit).

    Args:
        options: List of menu options
        title: Menu title

    Returns:
        Selected option or None if cancelled
    """
    return menu(options, title, show_exit=False)


def show_progress_bar(current: int, total: int, message: str = "Progresso"):
    """
    Display a progress bar message.

    Args:
        current: Current progress
        total: Total items
        message: Message to display
    """
    percent = (current / total * 100) if total > 0 else 0
    bar_length = 20
    filled = int(bar_length * current / total) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_length - filled)
    console.print(f"{message}: [{bar}] {percent:.0f}% ({current}/{total})")


def show_status(message: str, style: str = "cyan"):
    """
    Display a status message.

    Args:
        message: Status message
        style: Rich style
    """
    console.print(f"⏳ {message}", style=style)


def confirm_action(message: str) -> bool:
    """
    Ask user for confirmation.

    Args:
        message: Confirmation message

    Returns:
        True if confirmed, False otherwise
    """
    questions = [
        Confirm(
            "confirm",
            message=message,
            default=False,
        )
    ]

    try:
        answers = prompt(questions)
        return answers.get("confirm", False)
    except (KeyboardInterrupt, EOFError):
        return False


def show_panel(content: str, title: str = "", style: str = "blue"):
    """
    Display content in a Rich panel.

    Args:
        content: Content to display
        title: Panel title
        style: Panel border style
    """
    panel = Panel(content, title=title, style=style)
    console.print(panel)


def clear_screen():
    """Clear terminal screen"""
    import os

    os.system("clear" if os.name == "posix" else "cls")


# Export logger
__all__ = [
    "menu",
    "menu_navigate",
    "show_progress_bar",
    "show_status",
    "confirm_action",
    "show_panel",
    "clear_screen",
    "logger",
    "console",
]
