"""Plugin/source management command handler.

This module handles:
- Interactive plugin management UI
- Enabling/disabling anime sources
"""


def manage_sources(args) -> None:
    """Handle plugin management UI for enabling/disabling sources."""
    from plugin_manager import plugin_management_menu

    plugin_management_menu()
