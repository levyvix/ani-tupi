"""Plugin/source management command handler.

This module handles:
- Interactive plugin management UI
- Enabling/disabling anime sources
"""

from models.config import settings
from plugin_manager import get_all_available_plugins
from ui.components import menu_navigate, pause
from utils.logging import get_logger

logger = get_logger(__name__)


def plugin_management_menu() -> None:
    """Show configured plugin status and priority order."""
    all_plugins = get_all_available_plugins()
    disabled_plugins = set(settings.plugins.disabled_plugins)
    priority_order = settings.plugins.priority_order

    if not all_plugins:
        logger.info("\n❌ Nenhum plugin encontrado!")
        pause()
        return

    priority_index = {plugin: index for index, plugin in enumerate(priority_order)}
    ordered_plugins = sorted(
        all_plugins,
        key=lambda plugin: (priority_index.get(plugin, len(priority_order)), plugin),
    )
    options = [
        f"{'❌' if plugin in disabled_plugins else '✅'} {plugin}" for plugin in ordered_plugins
    ]
    options.append("Voltar")

    menu_navigate(
        options,
        msg="Fontes configuradas via ANI_TUPI__PLUGINS__DISABLED_PLUGINS / PRIORITY_ORDER",
    )


def manage_sources(args) -> None:
    """Handle plugin management UI for enabling/disabling sources."""
    plugin_management_menu()
