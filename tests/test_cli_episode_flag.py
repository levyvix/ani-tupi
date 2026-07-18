"""Tests for the public CLI parser and episode selection contract."""

import pytest

from commands.anime import episode_index
from main import build_parser


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1", 1), ("05", 5), ("25", 25)],
)
def test_parser_converts_episode_to_integer(value, expected):
    args = build_parser().parse_args(["-q", "anime", "-e", value])
    assert args.episode == expected


@pytest.mark.parametrize("value", ["invalid", "5-10", "5-"])
def test_parser_rejects_non_single_episode(value):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["-q", "anime", "-e", value])


@pytest.mark.parametrize(
    ("episode", "total", "expected"),
    [(1, 25, 0), (5, 25, 4), (25, 25, 24)],
)
def test_episode_index_uses_project_conversion(episode, total, expected):
    assert episode_index(episode, total) == expected


@pytest.mark.parametrize("episode", [0, -5, 26])
def test_episode_index_rejects_unavailable_episode(episode):
    with pytest.raises(ValueError, match="Episódio"):
        episode_index(episode, 25)


def test_episode_index_rejects_empty_catalog():
    with pytest.raises(ValueError, match="Episódio"):
        episode_index(1, 0)
