"""Plugin/source management helpers."""

from models.config import settings
from services.repository import rep


def get_all_available_plugins() -> list[str]:
    """Get list of all available plugins (by scanning plugins/ directory).

    Returns:
        List of plugin names (sorted alphabetically)
    """
    from scrapers.loader import discover_plugin_names

    try:
        return discover_plugin_names()
    except Exception:
        # Fallback: get from repository if directory scan fails
        return sorted(rep.get_active_sources())


def get_enabled_plugins() -> list[str]:
    """Get list of enabled plugin names (excluding disabled ones)."""
    disabled_plugins = set(settings.plugins.disabled_plugins)
    return [plugin for plugin in get_all_available_plugins() if plugin not in disabled_plugins]


def get_plugin_priority_order() -> list[str]:
    """Get plugin priority order from settings."""
    return settings.plugins.priority_order
