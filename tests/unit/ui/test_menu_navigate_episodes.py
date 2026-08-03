"""Testes do menu de seleção de episódio (``ui.components``).

O único boundary externo mockado é o próprio prompt interativo
(``ui.components.menu_navigate``), que exige TTY.
"""

from unittest.mock import patch

import ui.components as components


def test_returns_index_of_selected_episode():
    with patch.object(components, "menu_navigate", return_value="Episódio 3") as menu:
        assert components.menu_navigate_episodes([1, 2, 3, 4]) == 2
    assert menu.call_args.args[0] == ["Episódio 1", "Episódio 2", "Episódio 3", "Episódio 4"]


def test_extra_options_are_appended_after_episodes():
    with patch.object(components, "menu_navigate", return_value="Episódio 1") as menu:
        components.menu_navigate_episodes([1, 2], extra_options=["🔀 Trocar fonte"])
    assert menu.call_args.args[0] == ["Episódio 1", "Episódio 2", "🔀 Trocar fonte"]


def test_selecting_extra_option_returns_the_option_label():
    with patch.object(components, "menu_navigate", return_value="🔀 Trocar fonte"):
        result = components.menu_navigate_episodes([1, 2], extra_options=["🔀 Trocar fonte"])
    assert result == "🔀 Trocar fonte"


def test_cancel_returns_none():
    with patch.object(components, "menu_navigate", return_value=None):
        assert components.menu_navigate_episodes([1, 2], extra_options=["🔀 Trocar fonte"]) is None
