import importlib
from os import listdir
from os.path import abspath, dirname, isfile, join


def get_resource_path(relative_path: str) -> str:
    """Get the path to resources relative to this loader."""
    return join(dirname(abspath(__file__)), relative_path)


def discover_plugin_names() -> list[str]:
    """Scan the ``plugins/`` directory for available scraper plugin names.

    Excludes system modules (``__init__.py``, ``utils.py``) and returns the
    plugin module names (without the ``.py`` suffix), sorted alphabetically.

    Returns:
        Sorted list of plugin names (e.g. ``["animefire", "sushianimes"]``).
    """
    path = get_resource_path("plugins/")
    system = {"__init__.py", "utils.py"}
    names = [
        file[:-3]
        for file in listdir(path)
        if isfile(join(path, file)) and file.endswith(".py") and file not in system
    ]
    return sorted(names)


def load_plugins(register, plugins: list[str] | None = None) -> None:
    """Load anime scraper plugins based on configured preferences.

    Respects plugin priority order from preferences if configured.
    Plugins are loaded in priority order (highest priority first).

    Args:
        register: Callback each plugin uses to register itself (e.g. ``rep.register``).
                  Injected so plugins stay pure adapters, free of service imports.
        plugins: Optional list of specific plugins to load (overrides preferences)
                 If None, loads all plugins except disabled ones
    """

    available_plugins = discover_plugin_names()

    if plugins is None:
        from models.config import settings

        disabled_plugins = set(settings.plugins.disabled_plugins)
        enabled_plugins = [plugin for plugin in available_plugins if plugin not in disabled_plugins]

        priority_order = settings.plugins.priority_order
        if priority_order:
            priority_index = {plugin: index for index, plugin in enumerate(priority_order)}

            def priority_key(plugin):
                return (0, priority_index[plugin]) if plugin in priority_index else (1, plugin)

            plugins = sorted(enabled_plugins, key=priority_key)
        else:
            plugins = enabled_plugins

    for plugin in plugins:
        importlib.import_module(f"scrapers.plugins.{plugin}").load(register)
