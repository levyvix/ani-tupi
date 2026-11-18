import json

from services.manga.manga_service import MangaHistory


def test_get_recent_reads_current_and_legacy_entries(tmp_path, monkeypatch):
    history_file = tmp_path / "manga_history.json"
    history_file.write_text(
        json.dumps(
            {
                "One Piece": {"last_chapter": "1100"},
                "Naruto": ["ignored", 699],
                "Unknown": {"timestamp": "today"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(MangaHistory, "_history_file", history_file)

    assert MangaHistory.get_recent() == [
        ("One Piece", "1100"),
        ("Naruto", "700"),
        ("Unknown", "Desconhecido"),
    ]


def test_get_recent_applies_limit_without_reordering(tmp_path, monkeypatch):
    history_file = tmp_path / "manga_history.json"
    history_file.write_text(
        json.dumps({"First": {"last_chapter": "1"}, "Second": {"last_chapter": "2"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(MangaHistory, "_history_file", history_file)

    assert MangaHistory.get_recent(limit=1) == [("First", "1")]
    assert MangaHistory.get_recent(limit=0) == []
