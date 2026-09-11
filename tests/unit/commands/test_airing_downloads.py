"""CLI dispatch tests for the non-interactive monitor."""

import sys
from unittest.mock import patch

import pytest

import main


def test_airing_run_short_circuits_startup(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ani-tupi", "airing", "run"])
    with patch("utils.logging.configure_logging") as configure:
        with patch.object(main.airing_downloads_cmd, "airing_downloads", return_value=0) as handler:
            with patch.object(main, "run_startup_update_check") as startup:
                with patch("scrapers.loader.load_plugins") as load_plugins:
                    with pytest.raises(SystemExit) as exc_info:
                        main.cli()

    assert exc_info.value.code == 0
    configure.assert_called_once_with(debug=False)
    handler.assert_called_once()
    startup.assert_not_called()
    load_plugins.assert_not_called()


def test_airing_downloads_rejects_interactive_options(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["ani-tupi", "--query", "naruto", "airing", "run"],
    )
    with pytest.raises(SystemExit) as exc_info:
        main.cli()
    assert exc_info.value.code == 2


def test_airing_downloads_is_a_command_with_required_subcommand():
    args = main.build_parser().parse_args(["airing", "status"])

    assert args.command == "airing"
    assert args.airing_downloads == "status"


def test_airing_without_subcommand_shows_action_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["ani-tupi", "airing"])

    with pytest.raises(SystemExit) as exc_info:
        main.cli()

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "configure" in output
    assert "Escolher e salvar a fonte" in output
    assert "remove" in output
    assert "sem apagar os downloads" in output
