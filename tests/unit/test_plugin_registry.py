"""Tests for PluginRegistry class."""

import pytest
from services.plugin_registry import PluginRegistry


class MockPlugin:
    """Mock plugin for testing."""

    def __init__(self, name: str):
        self.name = name

    def search_anime(self, query: str):
        pass

    def search_episodes(self, anime: str, url: str, params=None):
        pass

    def search_player_src(self, url: str, container: list, event):
        pass


@pytest.fixture
def registry():
    """Create a fresh registry for each test."""
    PluginRegistry.reset_singleton()
    return PluginRegistry()


class TestPluginRegistry:
    """Test PluginRegistry class."""

    def test_singleton_pattern(self):
        """PluginRegistry should be a singleton."""
        registry1 = PluginRegistry()
        registry2 = PluginRegistry()
        assert registry1 is registry2

    def test_register_single_and_multiple_plugins(self, registry):
        """Should register single and multiple plugins."""
        plugin1 = MockPlugin("animefire")
        registry.register(plugin1)
        assert registry.get_plugin("animefire") is plugin1

        plugin2 = MockPlugin("sushianimes")
        registry.register(plugin2)
        assert registry.get_plugin("animefire") is plugin1
        assert registry.get_plugin("sushianimes") is plugin2

    def test_get_active_sources_and_all_plugins(self, registry):
        """Should return sorted sources and dict of all plugins (empty and populated)."""
        # Empty case
        assert registry.get_active_sources() == []
        assert registry.get_all_plugins() == {}

        # Populated case
        plugin1 = MockPlugin("zulu")
        plugin2 = MockPlugin("alpha")
        plugin3 = MockPlugin("mike")
        registry.register(plugin1)
        registry.register(plugin2)
        registry.register(plugin3)

        assert registry.get_active_sources() == ["alpha", "mike", "zulu"]
        assert registry.get_all_plugins() == {
            "zulu": plugin1,
            "alpha": plugin2,
            "mike": plugin3,
        }

    def test_get_plugin_not_found(self, registry):
        """Should return None for non-existent plugin."""
        plugin = registry.get_plugin("nonexistent")
        assert plugin is None

    def test_reset_singleton(self):
        """Should clear singleton instance on reset."""
        registry1 = PluginRegistry()
        registry1.register(MockPlugin("test"))

        PluginRegistry.reset_singleton()

        registry2 = PluginRegistry()
        assert registry2.get_plugin("test") is None

    def test_register_overwrites_existing(self, registry):
        """Registering same name twice should overwrite."""
        plugin1 = MockPlugin("animefire")
        plugin2 = MockPlugin("animefire")  # Same name

        registry.register(plugin1)
        registry.register(plugin2)

        assert registry.get_plugin("animefire") is plugin2
