"""Plugin/source management system.

This module provides functions for managing anime scraper plugins:
- Loading/saving plugin preferences (active/disabled)
- Interactive menu for toggling sources
- Integration with loader.py for selective plugin loading

Used by: cli.py, main.py
"""

from json import dump, load
from pathlib import Path

from config import get_data_path, settings
from repository import rep
from ui.components import menu_navigate


def load_plugin_preferences() -> dict:
    """Load plugin preferences from JSON file.

    Returns:
        Dict with format: {"disabled_plugins": ["animesonlinecc", ...]}
    """
    prefs_file = settings.plugins.preferences_file
    try:
        if prefs_file.exists():
            with prefs_file.open() as f:
                return load(f)
        return {"disabled_plugins": []}
    except Exception:
        return {"disabled_plugins": []}


def save_plugin_preferences(disabled_plugins: list[str]) -> None:
    """Save plugin preferences to JSON file.

    Args:
        disabled_plugins: List of plugin names to disable (e.g., ["animesonlinecc"])
    """
    prefs_file = settings.plugins.preferences_file
    try:
        # Ensure directory exists
        prefs_file.parent.mkdir(parents=True, exist_ok=True)

        data = {"disabled_plugins": disabled_plugins}
        with prefs_file.open("w") as f:
            dump(data, f, indent=2)
    except Exception as e:
        print(f"⚠️  Erro ao salvar preferências: {e}")


def get_all_available_plugins() -> list[str]:
    """Get list of all available plugins (by scanning plugins/ directory).

    Returns:
        List of plugin names (sorted alphabetically)
    """
    from os import listdir
    from os.path import isfile, join

    from loader import get_resource_path

    # Scan plugins directory
    path = get_resource_path("plugins/")
    system = {"__init__.py", "utils.py"}

    try:
        all_plugins = [
            file[:-3]
            for file in listdir(path)
            if isfile(join(path, file)) and file.endswith(".py") and file not in system
        ]
        return sorted(all_plugins)
    except Exception:
        # Fallback: get from repository if directory scan fails
        return sorted(rep.get_active_sources())


def plugin_management_menu() -> None:
    """Interactive menu for managing plugin preferences.

    Shows all available plugins with checkmarks for active ones.
    Allows user to toggle plugins on/off.
    """
    prefs = load_plugin_preferences()
    disabled_plugins = set(prefs.get("disabled_plugins", []))

    # Get all available plugins
    all_plugins = get_all_available_plugins()

    if not all_plugins:
        print("\n❌ Nenhum plugin encontrado!")
        input("\nPressione Enter para continuar...")
        return

    while True:
        # Build menu options with status indicators
        options = []
        for plugin in all_plugins:
            if plugin in disabled_plugins:
                status = "❌"
            else:
                status = "✅"
            options.append(f"{status} {plugin}")

        options.append("💾 Salvar e Sair")

        selected = menu_navigate(
            options,
            msg="Gerenciar Fontes de Anime (selecione para ativar/desativar)",
        )

        if not selected or selected == "💾 Salvar e Sair":
            # Save and exit
            save_plugin_preferences(list(disabled_plugins))
            print("\n✅ Preferências salvas!")
            print("ℹ️  Reinicie o ani-tupi para aplicar as mudanças.")
            input("\nPressione Enter para continuar...")
            return

        # Toggle plugin status
        # Extract plugin name (remove status emoji)
        plugin_name = selected.split(" ", 1)[1]

        if plugin_name in disabled_plugins:
            disabled_plugins.remove(plugin_name)
        else:
            disabled_plugins.add(plugin_name)


def get_enabled_plugins() -> list[str]:
    """Get list of enabled plugin names (excluding disabled ones).

    Returns:
        List of enabled plugin names
    """
    prefs = load_plugin_preferences()
    disabled_plugins = set(prefs.get("disabled_plugins", []))

    # Get all available plugins
    all_plugins = get_all_available_plugins()

    # Filter out disabled ones
    enabled = [p for p in all_plugins if p not in disabled_plugins]
    return enabled
