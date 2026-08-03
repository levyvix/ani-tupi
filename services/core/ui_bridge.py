"""Lazy UI bridge for the service layer.

Services must not import from ``ui.*`` (presentation layer) so they stay
testable without a terminal. When a command does not inject its own UI
callables, service functions fall back to these thin proxies, which resolve
the real implementation from ``ui.components`` at call time.

Resolving lazily (rather than importing the symbols) means:
- the service module never has a static ``from ui`` dependency, and
- tests that patch ``ui.components.<name>`` are still honoured.

**Testing note**: functions in this module are used as default argument values
(e.g. ``progress=ui_bridge.loading``). Default args are captured at class/function
definition time, so ``monkeypatch.setattr(ui_bridge, "loading", fake)`` will NOT
affect callers that already have the default bound. Always inject UI callables
directly (``progress=fake``) in tests rather than monkeypatching this module.
"""

from contextlib import contextmanager

__all__ = [
    "loading",
    "menu_navigate",
    "menu_navigate_episodes",
    "pause",
    "prompt",
    "show_info",
    "show_warning",
]


def menu_navigate(opts, msg="", **kwargs):
    """Proxy to ``ui.components.menu_navigate``."""
    import ui.components

    return ui.components.menu_navigate(opts, msg=msg, **kwargs)


def menu_navigate_episodes(episode_numbers, msg="Escolha o episódio."):
    """Proxy to ``ui.components.menu_navigate_episodes``."""
    import ui.components

    return ui.components.menu_navigate_episodes(episode_numbers, msg=msg)


@contextmanager
def loading(msg="Carregando..."):
    """Proxy to ``ui.components.loading`` (cosmetic spinner)."""
    import ui.components

    with ui.components.loading(msg):
        yield


def pause(message="Pressione Enter para continuar..."):
    """Proxy to ``ui.components.pause``."""
    import ui.components

    return ui.components.pause(message)


def show_info(message, title="Info"):
    """Proxy to ``ui.components.show_info``."""
    import ui.components

    return ui.components.show_info(message, title=title)


def show_warning(message, title="Atenção"):
    """Proxy to ``ui.components.show_warning``."""
    import ui.components

    return ui.components.show_warning(message, title=title)


def prompt(message):
    """Proxy to the builtin ``input`` for interactive text entry."""
    return input(message)
