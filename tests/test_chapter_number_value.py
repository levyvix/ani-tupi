"""Tests for the unified chapter-number parsing helper (M6)."""

import pytest

from services.manga.reading_flow import chapter_number_value


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1", 1.0),
        ("42", 42.0),
        (7, 7.0),
        (10.5, 10.5),
        ("10.5", 10.5),
        ("10,5", 10.5),  # comma decimal tolerated
        ("0", 0.0),
    ],
)
def test_parses_valid_numbers(value, expected):
    assert chapter_number_value(value) == expected


@pytest.mark.parametrize("value", ["", "extra", "cap. 5", "1-2", "abc", "5v2", None])
def test_junk_returns_none(value):
    assert chapter_number_value(value) is None
