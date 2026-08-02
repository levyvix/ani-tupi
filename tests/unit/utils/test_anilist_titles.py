from models.models import AniListTitle
from utils.anilist_titles import format_title


def test_format_title_joins_different_romaji_and_english():
    title = AniListTitle(romaji="Boku no Hero Academia", english="My Hero Academia")

    assert format_title(title) == "Boku no Hero Academia / My Hero Academia"


def test_format_title_does_not_duplicate_case_only_difference():
    title = AniListTitle(romaji="Dandadan", english="dandadan")

    assert format_title(title) == "Dandadan"


def test_format_title_accepts_dict_input_case_insensitive():
    title = {"romaji": "One Piece", "english": "one piece", "native": None}

    assert format_title(title) == "One Piece"


def test_format_title_normalizes_punctuation_before_comparing():
    title = AniListTitle(romaji="Anime A: Force", english="ANIME A - FORCE")

    assert format_title(title) == "Anime A: Force"
