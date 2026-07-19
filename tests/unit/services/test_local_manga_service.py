"""Coverage tests for services/local_manga_service.py.

Strategy: build REAL temp directory trees; mock only create_pdf_from_images and
the AniList client. No mocking of the service itself or file operations.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch


from services.local_manga_service import LocalMangaService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manga_tree(base: Path, manga_title: str, chapters: dict[str, list[str]]) -> Path:
    """Create a manga directory structure under base.

    chapters = {"01": ["001.png", "002.png"], "02": ["02.pdf"]}
    """
    manga_dir = base / manga_title
    manga_dir.mkdir(parents=True, exist_ok=True)
    for chapter_num, files in chapters.items():
        ch_dir = manga_dir / chapter_num
        ch_dir.mkdir(parents=True, exist_ok=True)
        for fname in files:
            (ch_dir / fname).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    return manga_dir


def _make_pdf_chapter(base: Path, manga_title: str, chapter_num: str) -> Path:
    """Create a chapter directory with a PDF file."""
    ch_dir = base / manga_title / chapter_num
    ch_dir.mkdir(parents=True, exist_ok=True)
    pdf = ch_dir / f"{chapter_num}.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake content")
    return ch_dir


# ---------------------------------------------------------------------------
# scan_local_library
# ---------------------------------------------------------------------------


class TestScanLocalLibrary:
    def test_returns_empty_when_dir_does_not_exist(self, tmp_path):
        svc = LocalMangaService(tmp_path / "nonexistent")
        assert svc.scan_local_library() == {}

    def test_returns_empty_when_dir_is_empty(self, tmp_path):
        svc = LocalMangaService(tmp_path)
        assert svc.scan_local_library() == {}

    def test_finds_single_manga_with_images(self, tmp_path):
        _make_manga_tree(tmp_path, "Naruto", {"01": ["001.png", "002.png"]})
        svc = LocalMangaService(tmp_path)
        library = svc.scan_local_library()
        assert "Naruto" in library
        assert "01" in library["Naruto"]

    def test_finds_multiple_manga(self, tmp_path):
        _make_manga_tree(tmp_path, "Naruto", {"01": ["001.png"]})
        _make_manga_tree(tmp_path, "Bleach", {"01": ["001.jpg"]})
        svc = LocalMangaService(tmp_path)
        library = svc.scan_local_library()
        assert "Naruto" in library
        assert "Bleach" in library

    def test_finds_manga_with_pdf_chapter(self, tmp_path):
        _make_pdf_chapter(tmp_path, "One Piece", "01")
        svc = LocalMangaService(tmp_path)
        library = svc.scan_local_library()
        assert "One Piece" in library

    def test_skips_chapter_without_content(self, tmp_path):
        """Chapter directory exists but has no images or PDF."""
        empty_chapter = tmp_path / "Manga" / "01"
        empty_chapter.mkdir(parents=True)
        svc = LocalMangaService(tmp_path)
        library = svc.scan_local_library()
        # Manga should not appear because the only chapter is empty
        assert "Manga" not in library

    def test_skips_files_at_manga_level(self, tmp_path):
        """Files at the top level of output_dir should be ignored."""
        (tmp_path / "some_file.txt").write_text("ignore me")
        _make_manga_tree(tmp_path, "Bleach", {"01": ["001.png"]})
        svc = LocalMangaService(tmp_path)
        library = svc.scan_local_library()
        assert "Bleach" in library
        assert len(library) == 1

    def test_chapters_sorted_numerically(self, tmp_path):
        _make_manga_tree(
            tmp_path,
            "Manga",
            {"10": ["001.png"], "2": ["001.png"], "1": ["001.png"]},
        )
        svc = LocalMangaService(tmp_path)
        library = svc.scan_local_library()
        chapters = library["Manga"]
        assert chapters == sorted(chapters, key=lambda x: float(x))

    def test_handles_decimal_chapter_numbers(self, tmp_path):
        _make_manga_tree(tmp_path, "Manga", {"42.5": ["001.png"]})
        svc = LocalMangaService(tmp_path)
        library = svc.scan_local_library()
        assert "42.5" in library["Manga"]

    def test_mixed_valid_and_invalid_chapters(self, tmp_path):
        _make_manga_tree(tmp_path, "Manga", {"01": ["001.png"]})
        # Add empty chapter dir
        (tmp_path / "Manga" / "02").mkdir()
        svc = LocalMangaService(tmp_path)
        library = svc.scan_local_library()
        assert library["Manga"] == ["01"]


# ---------------------------------------------------------------------------
# get_manga_list
# ---------------------------------------------------------------------------


class TestGetMangaList:
    def test_returns_empty_list_when_no_manga(self, tmp_path):
        svc = LocalMangaService(tmp_path)
        assert svc.get_manga_list() == []

    def test_format_includes_chapter_count(self, tmp_path):
        _make_manga_tree(
            tmp_path, "Naruto", {"01": ["001.png"], "02": ["002.png"], "03": ["003.png"]}
        )
        svc = LocalMangaService(tmp_path)
        result = svc.get_manga_list()
        assert len(result) == 1
        assert "3 caps" in result[0]
        assert "Naruto" in result[0]

    def test_list_is_sorted_alphabetically(self, tmp_path):
        _make_manga_tree(tmp_path, "Zoro", {"01": ["001.png"]})
        _make_manga_tree(tmp_path, "Armin", {"01": ["001.png"]})
        svc = LocalMangaService(tmp_path)
        result = svc.get_manga_list()
        assert result[0].startswith("Armin")
        assert result[1].startswith("Zoro")


# ---------------------------------------------------------------------------
# get_chapters_for_manga
# ---------------------------------------------------------------------------


class TestGetChaptersForManga:
    def test_returns_empty_for_nonexistent_manga(self, tmp_path):
        svc = LocalMangaService(tmp_path)
        assert svc.get_chapters_for_manga("Nonexistent") == []

    def test_returns_chapters_with_images(self, tmp_path):
        _make_manga_tree(tmp_path, "Bleach", {"01": ["001.png", "002.png"]})
        svc = LocalMangaService(tmp_path)
        chapters = svc.get_chapters_for_manga("Bleach")
        assert len(chapters) == 1
        assert chapters[0].chapter_number == "01"
        assert chapters[0].has_images is True
        assert chapters[0].image_count == 2

    def test_returns_chapters_with_pdf(self, tmp_path):
        _make_pdf_chapter(tmp_path, "Manga", "05")
        svc = LocalMangaService(tmp_path)
        chapters = svc.get_chapters_for_manga("Manga")
        assert len(chapters) == 1
        assert chapters[0].has_pdf is True
        assert chapters[0].pdf_path is not None

    def test_chapter_without_content_is_skipped(self, tmp_path):
        (tmp_path / "Manga" / "01").mkdir(parents=True)
        svc = LocalMangaService(tmp_path)
        chapters = svc.get_chapters_for_manga("Manga")
        assert chapters == []

    def test_file_size_is_calculated(self, tmp_path):
        _make_manga_tree(tmp_path, "Manga", {"01": ["001.png"]})
        svc = LocalMangaService(tmp_path)
        chapters = svc.get_chapters_for_manga("Manga")
        assert chapters[0].file_size_mb >= 0

    def test_multiple_chapters_sorted(self, tmp_path):
        _make_manga_tree(tmp_path, "Manga", {"3": ["001.png"], "1": ["001.png"], "2": ["001.png"]})
        svc = LocalMangaService(tmp_path)
        chapters = svc.get_chapters_for_manga("Manga")
        numbers = [c.chapter_number for c in chapters]
        assert numbers == sorted(numbers, key=lambda x: float(x))

    def test_skips_non_directory_items(self, tmp_path):
        manga_dir = tmp_path / "Manga"
        manga_dir.mkdir()
        (manga_dir / "readme.txt").write_text("ignore")
        _make_manga_tree(tmp_path, "Manga", {"01": ["001.png"]})
        svc = LocalMangaService(tmp_path)
        chapters = svc.get_chapters_for_manga("Manga")
        assert len(chapters) == 1


# ---------------------------------------------------------------------------
# auto_create_pdf_if_needed
# ---------------------------------------------------------------------------


class TestAutoCreatePdfIfNeeded:
    def test_returns_existing_pdf_path(self, tmp_path):
        _make_pdf_chapter(tmp_path, "Manga", "01")
        svc = LocalMangaService(tmp_path)
        result = svc.auto_create_pdf_if_needed("Manga", "01")
        assert result is not None
        assert result.suffix == ".pdf"
        assert result.exists()

    def test_returns_none_when_no_images_and_no_pdf(self, tmp_path):
        (tmp_path / "Manga" / "01").mkdir(parents=True)
        svc = LocalMangaService(tmp_path)
        result = svc.auto_create_pdf_if_needed("Manga", "01")
        assert result is None

    def test_creates_pdf_from_images(self, tmp_path, monkeypatch):
        _make_manga_tree(tmp_path, "Manga", {"01": ["001.png", "002.png"]})
        svc = LocalMangaService(tmp_path)

        pdf_path = tmp_path / "Manga" / "01" / "01.pdf"

        def fake_create_pdf(src, dest, quality=85):
            dest.write_bytes(b"%PDF fake")

        with patch(
            "services.local_manga_service.create_pdf_from_images", side_effect=fake_create_pdf
        ):
            result = svc.auto_create_pdf_if_needed("Manga", "01")

        assert result is not None
        assert result == pdf_path

    def test_returns_none_when_pdf_creation_fails(self, tmp_path):
        _make_manga_tree(tmp_path, "Manga", {"01": ["001.png"]})
        svc = LocalMangaService(tmp_path)

        with patch(
            "services.local_manga_service.create_pdf_from_images", side_effect=OSError("fail")
        ):
            result = svc.auto_create_pdf_if_needed("Manga", "01")

        assert result is None

    def test_deletes_images_after_pdf_if_configured(self, tmp_path, monkeypatch):
        _make_manga_tree(tmp_path, "Manga", {"01": ["001.png", "002.png"]})

        def fake_create_pdf(src, dest, quality=85):
            dest.write_bytes(b"%PDF fake")

        monkeypatch.setattr(
            "services.local_manga_service.settings.manga.delete_images_after_pdf", True
        )
        with patch(
            "services.local_manga_service.create_pdf_from_images", side_effect=fake_create_pdf
        ):
            svc = LocalMangaService(tmp_path)
            result = svc.auto_create_pdf_if_needed("Manga", "01")

        assert result is not None
        # Images should be deleted
        ch_dir = tmp_path / "Manga" / "01"
        remaining = list(ch_dir.glob("*.png"))
        assert remaining == []

    def test_does_not_delete_images_when_configured_false(self, tmp_path, monkeypatch):
        _make_manga_tree(tmp_path, "Manga", {"01": ["001.png"]})

        def fake_create_pdf(src, dest, quality=85):
            dest.write_bytes(b"%PDF fake")

        monkeypatch.setattr(
            "services.local_manga_service.settings.manga.delete_images_after_pdf", False
        )
        with patch(
            "services.local_manga_service.create_pdf_from_images", side_effect=fake_create_pdf
        ):
            svc = LocalMangaService(tmp_path)
            svc.auto_create_pdf_if_needed("Manga", "01")

        ch_dir = tmp_path / "Manga" / "01"
        remaining = list(ch_dir.glob("*.png"))
        assert len(remaining) == 1


# ---------------------------------------------------------------------------
# sync_to_anilist_if_ahead
# ---------------------------------------------------------------------------


class TestSyncToAnilistIfAhead:
    def test_returns_false_when_no_anilist_service(self, tmp_path):
        svc = LocalMangaService(tmp_path)
        assert svc.sync_to_anilist_if_ahead("Manga", "5") is False

    def test_returns_false_for_invalid_chapter_number(self, tmp_path):
        svc = LocalMangaService(tmp_path)
        anilist = MagicMock()
        assert svc.sync_to_anilist_if_ahead("Manga", "not-a-number", anilist) is False

    def test_returns_false_when_anilist_id_not_found(self, tmp_path):
        svc = LocalMangaService(tmp_path)
        anilist = MagicMock()

        with patch("services.manga_service.MangaHistory") as mock_history:
            mock_history.load.return_value = {}
            with patch("services.anilist.discovery.get_anilist_id_from_title", return_value=None):
                result = svc.sync_to_anilist_if_ahead("Manga", "5", anilist)

        assert result is False

    def test_syncs_when_local_ahead(self, tmp_path):
        svc = LocalMangaService(tmp_path)
        anilist = MagicMock()

        anilist_entry = MagicMock()
        anilist_entry.progress = 3
        anilist.get_manga_list_entry.return_value = anilist_entry
        anilist.update_manga_progress.return_value = None

        with patch("services.manga_service.MangaHistory") as mock_history:
            mock_history.load.return_value = {"Manga": MagicMock(anilist_id=123, last_chapter="5")}
            result = svc.sync_to_anilist_if_ahead("Manga", "5", anilist)

        assert result is True
        anilist.update_manga_progress.assert_called_once_with(123, 5)

    def test_does_not_sync_when_local_not_ahead(self, tmp_path):
        svc = LocalMangaService(tmp_path)
        anilist = MagicMock()

        anilist_entry = MagicMock()
        anilist_entry.progress = 10  # AniList is ahead
        anilist.get_manga_list_entry.return_value = anilist_entry

        with patch("services.manga_service.MangaHistory") as mock_history:
            mock_history.load.return_value = {"Manga": MagicMock(anilist_id=123, last_chapter="5")}
            result = svc.sync_to_anilist_if_ahead("Manga", "5", anilist)

        assert result is False
        anilist.update_manga_progress.assert_not_called()

    def test_returns_false_when_anilist_entry_has_no_progress(self, tmp_path):
        svc = LocalMangaService(tmp_path)
        anilist = MagicMock()

        anilist_entry = MagicMock()
        anilist_entry.progress = None
        anilist.get_manga_list_entry.return_value = anilist_entry

        with patch("services.manga_service.MangaHistory") as mock_history:
            mock_history.load.return_value = {"Manga": MagicMock(anilist_id=123, last_chapter="5")}
            result = svc.sync_to_anilist_if_ahead("Manga", "5", anilist)

        assert result is False

    def test_returns_false_on_anilist_network_error(self, tmp_path):
        svc = LocalMangaService(tmp_path)
        anilist = MagicMock()
        anilist.get_manga_list_entry.side_effect = ValueError("network error")

        with patch("services.manga_service.MangaHistory") as mock_history:
            mock_history.load.return_value = {"Manga": MagicMock(anilist_id=123, last_chapter="5")}
            result = svc.sync_to_anilist_if_ahead("Manga", "5", anilist)

        assert result is False

    def test_handles_decimal_chapter_numbers(self, tmp_path):
        """Decimal chapter "6.5" → int 6, which is ahead of anilist progress 3."""
        svc = LocalMangaService(tmp_path)
        anilist = MagicMock()

        anilist_entry = MagicMock()
        anilist_entry.progress = 3
        anilist.get_manga_list_entry.return_value = anilist_entry

        with patch("services.manga_service.MangaHistory") as mock_history:
            mock_history.load.return_value = {"Manga": MagicMock(anilist_id=99, last_chapter="6.5")}
            result = svc.sync_to_anilist_if_ahead("Manga", "6.5", anilist)

        assert result is True

    def test_falls_back_to_anilist_discovery_when_no_history_entry(self, tmp_path):
        svc = LocalMangaService(tmp_path)
        anilist = MagicMock()

        anilist_entry = MagicMock()
        anilist_entry.progress = 1
        anilist.get_manga_list_entry.return_value = anilist_entry

        with patch("services.manga_service.MangaHistory") as mock_history:
            mock_history.load.return_value = {}
            with patch("services.anilist.discovery.get_anilist_id_from_title", return_value=42):
                result = svc.sync_to_anilist_if_ahead("Manga", "5", anilist)

        assert result is True


# ---------------------------------------------------------------------------
# _chapter_sort_key
# ---------------------------------------------------------------------------


class TestChapterSortKey:
    def test_numeric_chapter(self):
        key = LocalMangaService._chapter_sort_key("5")
        assert key == (0, 5.0)

    def test_decimal_chapter(self):
        key = LocalMangaService._chapter_sort_key("42.5")
        assert key == (0, 42.5)

    def test_string_chapter_fallback(self):
        key = LocalMangaService._chapter_sort_key("special")
        assert key == (1, "special")

    def test_numeric_sorts_before_string(self):
        k1 = LocalMangaService._chapter_sort_key("1")
        k2 = LocalMangaService._chapter_sort_key("special")
        assert k1 < k2

    def test_numeric_sorted_correctly(self):
        names = ["10", "2", "1", "42.5"]
        sorted_names = sorted(names, key=LocalMangaService._chapter_sort_key)
        assert sorted_names == ["1", "2", "10", "42.5"]
