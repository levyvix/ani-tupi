"""Tests for main menu looping behavior."""

from types import SimpleNamespace

import main


def test_main_menu_flow_returns_to_main_menu_after_submenu(monkeypatch):
    """Returning from a submenu should redisplay the main menu."""
    choices = iter(["📂 Biblioteca Local", "⚙️  Gerenciar Fontes"])
    seen = []

    def fake_show_main_menu():
        return next(choices)

    def fake_local_library(args):
        seen.append("local")

    def fake_manage_sources(args):
        seen.append("sources")
        raise SystemExit(0)

    monkeypatch.setattr(main, "show_main_menu", fake_show_main_menu)
    monkeypatch.setattr(main, "handle_local_library", fake_local_library)
    monkeypatch.setattr(main, "manage_sources_cmd", fake_manage_sources)
    args = SimpleNamespace(continue_watching=False)

    try:
        main.main_menu_flow(args)
    except SystemExit:
        pass

    assert seen == ["local", "sources"]


def test_continue_watching_does_not_mutate_shared_arguments(monkeypatch):
    args = SimpleNamespace(continue_watching=False)
    received = []

    monkeypatch.setattr(main, "show_main_menu", lambda: "▶️  Continuar Assistindo")

    def fake_anime(command_args):
        received.append(command_args)
        raise SystemExit(0)

    monkeypatch.setattr(main, "anime_cmd", fake_anime)

    try:
        main.main_menu_flow(args)
    except SystemExit:
        pass

    assert args.continue_watching is False
    assert received[0].continue_watching is True
    assert received[0] is not args
