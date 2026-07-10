import plugin_manager
from scrapers.loader import discover_plugin_names


class PluginSettingsStub:
    disabled_plugins = ["animefire"]
    priority_order = ["sushianimes", "animesdigital", "animefire"]


class SettingsStub:
    plugins = PluginSettingsStub()


def test_plugin_helpers_read_configured_settings(monkeypatch):
    monkeypatch.setattr(plugin_manager, "settings", SettingsStub())
    monkeypatch.setattr(
        plugin_manager,
        "get_all_available_plugins",
        lambda: ["animefire", "animesdigital", "sushianimes"],
    )

    assert plugin_manager.get_enabled_plugins() == ["animesdigital", "sushianimes"]
    assert plugin_manager.get_plugin_priority_order() == [
        "sushianimes",
        "animesdigital",
        "animefire",
    ]


def test_discover_plugin_names_scans_plugins_dir():
    names = discover_plugin_names()

    # Real plugins present in scrapers/plugins/ are discovered.
    assert "animefire" in names
    assert "sushianimes" in names
    # System modules are excluded.
    assert "utils" not in names
    assert "__init__" not in names
    # Result is sorted.
    assert names == sorted(names)


def test_get_all_available_plugins_uses_shared_discovery():
    # The pure helper delegates to the shared scanner and returns real names.
    plugins = plugin_manager.get_all_available_plugins()
    assert plugins == discover_plugin_names()
    assert "animefire" in plugins
