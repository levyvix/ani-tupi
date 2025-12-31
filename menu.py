"""
Textual-based menu system for ani-tupi
Modern TUI with search, themes, and preview support
"""

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, OptionList, Static, Input, Label
from textual.containers import Container, Vertical, Horizontal
from textual.binding import Binding
from textual.screen import Screen
from typing import Optional, Callable, Any
from rich.text import Text
from pathlib import Path
import sys
import os


# Theme system - Path for saving user preference
THEME_FILE = Path.home() / ".local/state/ani-tupi/theme.txt"


class PreviewPanel(Vertical):
    """Painel lateral para preview de informações"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_data = None

    def compose(self) -> ComposeResult:
        yield Label("Preview", id="preview-title")
        yield Static("Selecione um item para ver detalhes", id="preview-content")

    def update_preview(self, item_data: dict):
        """Atualiza preview com dados do item"""
        self.current_data = item_data

        if not item_data:
            content = "Selecione um item para ver detalhes"
        else:
            parts = []

            if "title" in item_data:
                parts.append(f"[bold yellow]{item_data['title']}[/bold yellow]")

            if "synopsis" in item_data:
                parts.append(f"\n{item_data['synopsis']}")

            if "rating" in item_data:
                parts.append(f"\n⭐ Rating: {item_data['rating']}")

            if "episodes" in item_data:
                parts.append(f"\n📺 Episodes: {item_data['episodes']}")

            content = "\n".join(parts) if parts else "Sem informações disponíveis"

        preview_widget = self.query_one("#preview-content", Static)
        preview_widget.update(content)


class SearchInput(Input):
    """Input field for fuzzy search"""

    def __init__(self, **kwargs):
        super().__init__(
            placeholder="Digite para buscar...",
            id="search-input",
            **kwargs
        )


class MenuScreen(Screen):
    """Tela de menu principal com suporte a search e preview"""

    BINDINGS = [
        Binding("escape", "back", "Voltar", priority=True),
        Binding("q", "quit", "Sair", priority=True),
        Binding("/", "toggle_search", "Buscar", priority=True),
        Binding("t", "toggle_theme", "Tema", show=True),
    ]

    CSS = """
    /* Base styling - Yellow theme (classic ani-tupi) */
    Screen {
        background: black;
    }

    #menu-container {
        width: 3fr;
        height: 100%;
        border: solid yellow;
    }

    #menu-title {
        background: yellow;
        color: black;
        text-align: center;
        text-style: bold;
        padding: 1;
        dock: top;
    }

    #menu-options {
        height: 1fr;
        background: black;
    }

    #search-input {
        dock: bottom;
        border: tall yellow;
        display: none;  /* Hidden by default */
    }

    #preview-panel {
        width: 2fr;
        height: 100%;
        background: #1a1a1a;
        border: solid yellow;
        padding: 1;
    }

    #preview-title {
        background: yellow;
        color: black;
        text-align: center;
        text-style: bold;
        padding: 1;
    }

    #preview-content {
        padding: 1;
        color: yellow;
    }

    OptionList > .option-list--option {
        background: black;
        color: yellow;
    }

    OptionList > .option-list--option-highlighted {
        background: yellow;
        color: black;
    }

    OptionList > .option-list--option-disabled {
        color: #555555;
        background: black;
    }

    Header {
        background: yellow;
        color: black;
    }

    Footer {
        background: yellow;
        color: black;
    }
    """

    def __init__(
        self,
        options: list[str],
        title: str,
        on_select: Optional[Callable[[str], None]] = None,
        show_preview: bool = False,
        preview_callback: Optional[Callable[[str], dict]] = None,
        mode: str = "exit_on_sair",
        **kwargs
    ):
        super().__init__(**kwargs)
        self.options = options
        self.all_options = options.copy()  # Store original for search
        self.title_text = title
        self.on_select_callback = on_select
        self.show_preview = show_preview
        self.preview_callback = preview_callback
        self.mode = mode  # "exit_on_sair" or "navigate"
        self.search_active = False

    def compose(self) -> ComposeResult:
        yield Header()

        if self.show_preview:
            with Horizontal():
                with Container(id="menu-container"):
                    yield Static(self.title_text, id="menu-title")
                    yield self._create_option_list()
                    yield SearchInput()

                yield PreviewPanel(id="preview-panel")
        else:
            with Container(id="menu-container"):
                yield Static(self.title_text, id="menu-title")
                yield self._create_option_list()
                yield SearchInput()

        yield Footer()

    def _create_option_list(self) -> OptionList:
        """Create and populate the option list"""
        option_list = OptionList(id="menu-options")

        for opt in self.options:
            # Handle separators - add as disabled option with dim styling
            if opt.startswith("─"):
                option_list.add_option(opt, disabled=True)
            else:
                option_list.add_option(opt)

        return option_list

    def on_mount(self) -> None:
        """Called when screen is mounted"""
        # Focus the option list
        self.query_one("#menu-options", OptionList).focus()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Called when an option is highlighted"""
        if self.show_preview and self.preview_callback:
            # Get the option text
            option_text = str(event.option.prompt)

            # Get preview data from callback
            preview_data = self.preview_callback(option_text)

            # Update preview panel
            preview = self.query_one("#preview-panel", PreviewPanel)
            preview.update_preview(preview_data)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Called when an option is selected"""
        # Get the selected option prompt (text)
        selected = str(event.option.prompt)

        # Skip separators
        if selected.startswith("─") or not selected.strip():
            return

        if self.on_select_callback:
            self.on_select_callback(selected)
        else:
            self.app.exit(selected)

    def action_back(self) -> None:
        """Handle back action (ESC key)"""
        if self.search_active:
            # If search is active, close it
            self.action_toggle_search()
        else:
            # Otherwise, exit with None
            self.app.exit(None)

    def action_quit(self) -> None:
        """Handle quit action (Q key)"""
        if self.mode == "exit_on_sair":
            sys.exit(0)
        else:
            self.app.exit(None)

    def action_toggle_search(self) -> None:
        """Toggle search input visibility"""
        search_input = self.query_one("#search-input", SearchInput)

        if self.search_active:
            # Hide search, restore original options
            search_input.styles.display = "none"
            self.search_active = False
            search_input.value = ""
            self._update_options(self.all_options)
            self.query_one("#menu-options", OptionList).focus()
        else:
            # Show search
            search_input.styles.display = "block"
            self.search_active = True
            search_input.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes"""
        if event.input.id == "search-input":
            query = event.value.lower()

            if not query:
                # Empty query - show all
                self._update_options(self.all_options)
            else:
                # Filter options using fuzzy matching
                from fuzzywuzzy import fuzz

                matches = []
                for opt in self.all_options:
                    # Skip separators
                    if opt.startswith("─"):
                        continue

                    score = fuzz.ratio(query, opt.lower())
                    if score > 60:  # Threshold
                        matches.append((score, opt))

                # Sort by score
                matches.sort(reverse=True, key=lambda x: x[0])
                filtered = [opt for score, opt in matches]

                self._update_options(filtered if filtered else ["Nenhum resultado encontrado"])

    def _update_options(self, options: list[str]) -> None:
        """Update the option list with new options"""
        option_list = self.query_one("#menu-options", OptionList)
        option_list.clear_options()

        for opt in options:
            if opt.startswith("─"):
                option_list.add_option(opt, disabled=True)
            else:
                option_list.add_option(opt)

    def action_toggle_theme(self) -> None:
        """Cycle through available themes"""
        # TODO: Implement dynamic theme switching
        # For now, theme is fixed to yellow (classic ani-tupi)
        pass


class MenuApp(App):
    """Main menu application"""

    def __init__(
        self,
        options: list[str],
        title: str,
        mode: str = "exit_on_sair",
        show_preview: bool = False,
        preview_callback: Optional[Callable[[str], dict]] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.options = options
        self.title_text = title
        self.mode = mode
        self.show_preview = show_preview
        self.preview_callback = preview_callback
        self.result: Optional[str] = None
        self._current_theme = self._load_theme()

    def _load_theme(self) -> str:
        """Load saved theme preference"""
        try:
            if THEME_FILE.exists():
                return THEME_FILE.read_text().strip()
        except:
            pass
        return "yellow"

    def _save_theme(self, theme: str) -> None:
        """Save theme preference"""
        try:
            THEME_FILE.parent.mkdir(parents=True, exist_ok=True)
            THEME_FILE.write_text(theme)
        except:
            pass

    def set_theme(self, theme_name: str) -> None:
        """Change application theme"""
        self._current_theme = theme_name
        self._save_theme(theme_name)

        # Apply theme colors by updating CSS variables
        # Note: Theme is applied via CSS in MenuScreen class
        # This method primarily saves the preference

        # Refresh the screen if mounted
        try:
            self.refresh()
        except:
            pass  # Not mounted yet

    def on_mount(self) -> None:
        """Called when app is mounted"""
        # Apply saved theme
        self.set_theme(self._current_theme)

        # Push the menu screen
        self.push_screen(
            MenuScreen(
                self.options,
                self.title_text,
                on_select=None,
                mode=self.mode,
                show_preview=self.show_preview,
                preview_callback=self.preview_callback,
            )
        )


def menu(opts: list[str], msg: str = "", show_preview: bool = False, preview_callback: Optional[Callable] = None) -> str:
    """
    Display interactive menu with automatic "Sair" option

    Args:
        opts: List of menu options
        msg: Title message
        show_preview: Show preview panel (default: False)
        preview_callback: Function to get preview data for an option

    Returns:
        Selected option (without "Sair")

    Behavior:
        - Adds "Sair" automatically to the end
        - If "Sair" is selected → calls sys.exit()
        - Returns selected option
    """
    # Add "Sair" to options
    opts_copy = opts.copy()
    opts_copy.append("Sair")

    # Run app
    app = MenuApp(
        opts_copy,
        msg or "Menu",
        mode="exit_on_sair",
        show_preview=show_preview,
        preview_callback=preview_callback,
    )
    result = app.run()

    # Handle result
    if result == "Sair" or result is None:
        sys.exit(0)

    # Remove "Sair" from original list (to preserve behavior)
    # Note: Original curses version did opts.pop()
    # But since we used a copy, we don't need to modify original

    return result


def menu_navigate(
    opts: list[str],
    msg: str = "",
    show_preview: bool = False,
    preview_callback: Optional[Callable] = None
) -> Optional[str]:
    """
    Display interactive menu for navigation (returns None instead of exit)

    Args:
        opts: List of menu options (can include separators "─")
        msg: Title message
        show_preview: Show preview panel (default: False)
        preview_callback: Function to get preview data for an option

    Returns:
        Selected option or None if user cancels

    Behavior:
        - Does NOT add "Sair" automatically
        - ESC/Q returns None
        - Allows navigation without exiting program
    """
    # Run app
    app = MenuApp(
        opts,
        msg or "Menu",
        mode="navigate",
        show_preview=show_preview,
        preview_callback=preview_callback,
    )
    result = app.run()

    # Return None for cancel actions
    if result in ["Sair", "Voltar"]:
        return None

    return result


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

    selection = menu(test_options, "Menu de Teste")
    print(f"\nSelecionado: {selection}")
