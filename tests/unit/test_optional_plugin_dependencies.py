"""Tests for optional runtime dependencies declared by scraper plugins."""

import importlib
import sys
from types import ModuleType

import pytest

from scrapers.core import plugin_dependencies
import manga_scrapers.loader as manga_loader
import scrapers.loader as anime_loader


def test_optional_dependencies_available_when_requirements_exist(monkeypatch):
    module = ModuleType("browser_plugin")
    module.OPTIONAL_DEPENDENCIES = {"selenium": "browser-scrapers"}
    monkeypatch.setattr(plugin_dependencies, "find_spec", lambda name: object())

    assert plugin_dependencies.optional_dependencies_available(module, "browser_plugin")


def test_missing_optional_dependency_skips_only_the_declaring_anime_plugin(monkeypatch):
    monkeypatch.setattr(
        plugin_dependencies,
        "find_spec",
        lambda name: None if name == "selenium" else importlib.util.find_spec(name),
    )
    loaded = []

    anime_loader.load_plugins(loaded.append, plugins=["anroll", "animefire"])

    assert [plugin.name for plugin in loaded] == ["animefire"]


def test_missing_optional_dependency_skips_only_the_declaring_manga_plugin(monkeypatch):
    monkeypatch.setattr(
        plugin_dependencies,
        "find_spec",
        lambda name: None if name == "selenium" else importlib.util.find_spec(name),
    )

    loaded = manga_loader.load_manga_plugins()

    assert "mangadex" in loaded
    assert "mangalivre" not in loaded
    assert "mugiwaras" not in loaded


def test_browser_plugins_and_adapter_import_without_selenium(monkeypatch):
    modules = [
        "scrapers.core.selenium_driver",
        "scrapers.plugins.anroll",
        "scrapers.plugins.animesdigital",
        "manga_scrapers.plugins.mangalivre",
        "manga_scrapers.plugins.mugiwaras",
    ]
    monkeypatch.setitem(sys.modules, "selenium", None)

    for module_name in modules:
        module = importlib.import_module(module_name)
        importlib.reload(module)


@pytest.mark.parametrize("optional_dependencies", [{}, {"selenium": "browser-scrapers"}])
def test_plugins_without_declared_missing_dependency_still_loads(
    optional_dependencies, monkeypatch
):
    module = ModuleType("plugin")
    module.OPTIONAL_DEPENDENCIES = optional_dependencies
    monkeypatch.setattr(plugin_dependencies, "find_spec", lambda _name: None)

    expected = not optional_dependencies
    assert plugin_dependencies.optional_dependencies_available(module, "plugin") is expected


def test_missing_dependency_diagnostic_includes_extra_install_command(monkeypatch):
    module = ModuleType("browser_plugin")
    module.OPTIONAL_DEPENDENCIES = {"selenium": "browser-scrapers"}
    messages = []
    monkeypatch.setattr(plugin_dependencies, "find_spec", lambda _name: None)
    monkeypatch.setattr(plugin_dependencies.logger, "warning", messages.append)

    assert not plugin_dependencies.optional_dependencies_available(module, "browser_plugin")
    assert "browser_plugin" in messages[0]
    assert "selenium" in messages[0]
    assert "ani-tupi[browser-scrapers]" in messages[0]


def test_anime_loader_does_not_treat_unexpected_import_error_as_optional(monkeypatch):
    def fail_import(_module_name):
        raise ModuleNotFoundError("internal package missing", name="internal_package")

    monkeypatch.setattr(anime_loader.importlib, "import_module", fail_import)

    with pytest.raises(ModuleNotFoundError, match="internal package missing"):
        anime_loader.load_plugins(lambda _plugin: None, plugins=["broken_plugin"])


def test_manga_loader_logs_unexpected_import_failure(monkeypatch):
    plugin_module = ModuleType("broken_plugin")

    def fail_load():
        raise ModuleNotFoundError("internal package missing", name="internal_package")

    plugin_module.load = fail_load
    messages = []
    monkeypatch.setattr(manga_loader, "listdir", lambda _path: ["broken_plugin.py"])
    monkeypatch.setattr(manga_loader, "isfile", lambda _path: True)
    monkeypatch.setattr(manga_loader.importlib, "import_module", lambda _name: plugin_module)
    monkeypatch.setattr(manga_loader.logger, "warning", messages.append)

    assert manga_loader.load_manga_plugins() == {}
    assert "internal package missing" in messages[0]
