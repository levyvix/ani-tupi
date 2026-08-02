"""Coverage tests for services/manga/download.py.

Strategy: mock httpx.get and inquirer only. Real filesystem via tmp_path.
Tests: _construct_chapter_url, _get_image_files, download_images,
       download_chapter (success/failure branches), prompt_download_range.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


from services.manga.download_service import (
    _construct_chapter_url,
    download_images,
    _get_image_files,
    download_chapter,
    prompt_download_range,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ch(number="1", id_="ch-1", url=None):
    return SimpleNamespace(number=number, id=id_, url=url or "")


def _manga(id_="m1", title="Test Manga"):
    return SimpleNamespace(id=id_, title=title)


def _config(tmp_path, debug=False, delete_images=False, pdf_quality=85):
    return SimpleNamespace(
        output_directory=tmp_path,
        debug_download_failures=debug,
        delete_images_after_pdf=delete_images,
        pdf_quality=pdf_quality,
    )


class _FakeTracker:
    def __init__(self):
        self.calls = []

    def mark_downloaded(self, *args, **kwargs):
        self.calls.append((args, kwargs))

    def is_downloaded(self, manga_id, chapter_number):
        return False


# ---------------------------------------------------------------------------
# _construct_chapter_url
# ---------------------------------------------------------------------------


class TestConstructChapterUrl:
    def test_returns_chapter_url_if_set(self):
        ch = _ch(url="http://already/set")
        result = _construct_chapter_url("mangadex", "http://base/", ch, _manga())
        assert result == "http://already/set"

    def test_mugiwaras_constructs_slug_url(self):
        ch = _ch(url="")
        manga = _manga(title="One Piece")
        result = _construct_chapter_url("mugiwaras", "http://mugi.com/", ch, manga)
        assert result is not None
        assert "capitulo-1" in result
        assert "one-piece" in result

    def test_mangadex_constructs_url(self):
        ch = _ch(id_="uuid-123", url="")
        result = _construct_chapter_url("mangadex", None, ch, _manga())
        assert result == "https://mangadex.org/chapter/uuid-123"

    def test_mangalivre_constructs_url(self):
        ch = _ch(url="")
        manga = _manga(title="Naruto")
        result = _construct_chapter_url(
            "mangalivre", "http://mangalivre.net/manga/naruto/", ch, manga
        )
        assert result is not None
        assert "naruto" in result

    def test_unknown_source_returns_none(self):
        ch = _ch(url="")
        result = _construct_chapter_url("unknown_source", "http://x/", ch, _manga())
        assert result is None

    def test_mugiwaras_strips_special_chars(self):
        ch = _ch(url="")
        manga = _manga(title="Berserk: The Black Swordsman?")
        result = _construct_chapter_url("mugiwaras", "http://m/", ch, manga)
        assert result is not None
        # Slug portion (after the base URL) should not have ? or :
        slug_part = result.replace("http://m/", "")
        assert "?" not in slug_part
        assert ":" not in slug_part


# ---------------------------------------------------------------------------
# _get_image_files
# ---------------------------------------------------------------------------


class TestGetImageFiles:
    def test_returns_empty_for_empty_dir(self, tmp_path):
        assert _get_image_files(tmp_path) == []

    def test_finds_png_files(self, tmp_path):
        (tmp_path / "001.png").write_bytes(b"x")
        (tmp_path / "002.png").write_bytes(b"x")
        files = _get_image_files(tmp_path)
        assert len(files) == 2

    def test_finds_all_image_extensions(self, tmp_path):
        for name in ["a.png", "b.jpg", "c.jpeg", "d.webp", "e.pdf"]:
            (tmp_path / name).write_bytes(b"x")
        files = _get_image_files(tmp_path)
        assert len(files) == 4  # no PDF

    def test_ignores_non_image_files(self, tmp_path):
        (tmp_path / "readme.txt").write_bytes(b"text")
        assert _get_image_files(tmp_path) == []


# ---------------------------------------------------------------------------
# download_images
# ---------------------------------------------------------------------------


class TestDownloadImages:
    def _cfg(self, debug=False):
        return SimpleNamespace(debug_download_failures=debug)

    def test_downloads_valid_image(self, tmp_path):
        img_data = b"\x89PNG" + b"\x00" * 2000

        mock_response = MagicMock()
        mock_response.content = img_data
        mock_response.headers = {"content-type": "image/png"}
        mock_response.raise_for_status.return_value = None

        with patch(
            "services.manga.download_service.http_get_with_retry", return_value=mock_response
        ):
            count = download_images(["http://example.com/img.png"], tmp_path, self._cfg())

        assert count == 1
        saved = list(tmp_path.glob("*.png"))
        assert len(saved) == 1

    def test_skips_file_too_small(self, tmp_path):
        mock_response = MagicMock()
        mock_response.content = b"tiny"
        mock_response.headers = {"content-type": "image/png"}
        mock_response.raise_for_status.return_value = None

        with patch(
            "services.manga.download_service.http_get_with_retry", return_value=mock_response
        ):
            count = download_images(["http://example.com/img.png"], tmp_path, self._cfg())

        assert count == 0

    def test_handles_timeout(self, tmp_path):
        import httpx

        with patch(
            "services.manga.download_service.http_get_with_retry",
            side_effect=httpx.TimeoutException("timeout"),
        ):
            count = download_images(["http://example.com/img.png"], tmp_path, self._cfg())

        assert count == 0

    def test_handles_connect_error(self, tmp_path):
        import httpx

        with patch(
            "services.manga.download_service.http_get_with_retry",
            side_effect=httpx.ConnectError("no connection"),
        ):
            count = download_images(["http://example.com/img.png"], tmp_path, self._cfg())

        assert count == 0

    def test_handles_http_status_error(self, tmp_path):
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=mock_response
        )

        with patch(
            "services.manga.download_service.http_get_with_retry",
            side_effect=mock_response.raise_for_status.side_effect,
        ):
            count = download_images(["http://example.com/img.png"], tmp_path, self._cfg())

        assert count == 0

    def test_skips_non_image_content_type(self, tmp_path):
        mock_response = MagicMock()
        mock_response.content = b"x" * 5000
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status.return_value = None

        with patch(
            "services.manga.download_service.http_get_with_retry", return_value=mock_response
        ):
            count = download_images(["http://example.com/img.png"], tmp_path, self._cfg())

        assert count == 0

    def test_accepts_octet_stream_with_image_extension(self, tmp_path):
        mock_response = MagicMock()
        mock_response.content = b"\x89PNG" + b"\x00" * 2000
        mock_response.headers = {"content-type": "application/octet-stream"}
        mock_response.raise_for_status.return_value = None

        with patch(
            "services.manga.download_service.http_get_with_retry", return_value=mock_response
        ):
            count = download_images(["http://example.com/img.png"], tmp_path, self._cfg())

        assert count == 1

    def test_skips_existing_file(self, tmp_path):
        existing = tmp_path / "000.png"
        existing.write_bytes(b"x" * 5000)

        with patch("services.manga.download_service.http_get_with_retry") as mock_get:
            count = download_images(["http://example.com/img.png"], tmp_path, self._cfg())

        # http_get_with_retry should NOT be called since file exists
        mock_get.assert_not_called()
        assert count == 1

    def test_multiple_pages_partial_success(self, tmp_path):
        import httpx

        good_response = MagicMock()
        good_response.content = b"\x89PNG" + b"\x00" * 2000
        good_response.headers = {"content-type": "image/png"}
        good_response.raise_for_status.return_value = None

        def side_effect(url, **kwargs):
            if "good" in url:
                return good_response
            raise httpx.TimeoutException("timeout")

        urls = ["http://good1.png", "http://bad1.png", "http://good2.png"]
        with patch("services.manga.download_service.http_get_with_retry", side_effect=side_effect):
            count = download_images(urls, tmp_path, self._cfg())

        assert count == 2

    def test_debug_mode_logs_urls(self, tmp_path):
        import httpx

        with patch(
            "services.manga.download_service.http_get_with_retry",
            side_effect=httpx.ConnectError("no"),
        ):
            # Just verify it doesn't crash in debug mode
            count = download_images(
                ["http://x.png"], tmp_path, SimpleNamespace(debug_download_failures=True)
            )
        assert count == 0


# ---------------------------------------------------------------------------
# download_chapter
# ---------------------------------------------------------------------------


class TestDownloadChapter:
    def _mock_service(self, pages=None):
        svc = MagicMock()
        svc.get_chapter_pages.return_value = (
            ["http://img1.png", "http://img2.png"] if pages is None else pages
        )
        return svc

    def test_full_success_flow(self, tmp_path):
        svc = self._mock_service()
        chapter = _ch("5")
        manga = _manga("m1", "Naruto")
        config = _config(tmp_path)
        tracker = _FakeTracker()
        img_data = b"\x89PNG" + b"\x00" * 2000

        mock_response = MagicMock()
        mock_response.content = img_data
        mock_response.headers = {"content-type": "image/png"}
        mock_response.raise_for_status.return_value = None

        with patch(
            "services.manga.download_service.http_get_with_retry", return_value=mock_response
        ):
            with patch("services.manga.download_service.create_pdf_from_images") as mock_pdf:

                def fake_pdf(src, dest, quality=85):
                    dest.write_bytes(b"PDF content")

                mock_pdf.side_effect = fake_pdf
                success, err = download_chapter(
                    chapter, svc, manga, "http://naruto/", "src_a", config, tracker, 1, 1
                )

        assert success is True
        assert err == ""
        assert len(tracker.calls) == 1

    def test_returns_false_when_get_pages_fails(self, tmp_path):
        svc = self._mock_service()
        svc.get_chapter_pages.side_effect = RuntimeError("network")
        chapter = _ch("1")
        manga = _manga()
        config = _config(tmp_path)

        success, err = download_chapter(
            chapter, svc, manga, None, "src_a", config, _FakeTracker(), 1, 1
        )

        assert success is False
        assert "Falha ao buscar páginas" in err

    def test_returns_false_when_no_pages(self, tmp_path):
        svc = self._mock_service(pages=[])
        chapter = _ch("1")
        config = _config(tmp_path)

        success, err = download_chapter(
            chapter, svc, _manga(), None, "src_a", config, _FakeTracker(), 1, 1
        )

        assert success is False
        assert "Nenhuma página" in err

    def test_returns_false_when_no_valid_images(self, tmp_path):
        svc = self._mock_service(pages=["http://img.png"])
        chapter = _ch("1")
        config = _config(tmp_path)

        # All downloads fail
        import httpx

        with patch(
            "services.manga.download_service.http_get_with_retry",
            side_effect=httpx.ConnectError("x"),
        ):
            success, err = download_chapter(
                chapter, svc, _manga(), None, "src_a", config, _FakeTracker(), 1, 1
            )

        assert success is False

    def test_returns_false_when_too_few_valid_images(self, tmp_path):
        # 4 pages but only 1 will succeed (< 50%)
        svc = self._mock_service(
            pages=["http://img1.png", "http://img2.png", "http://img3.png", "http://img4.png"]
        )
        chapter = _ch("1")
        config = _config(tmp_path)
        import httpx

        call_count = [0]

        def side_effect(url, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                m = MagicMock()
                m.content = b"\x89PNG" + b"\x00" * 2000
                m.headers = {"content-type": "image/png"}
                m.raise_for_status.return_value = None
                return m
            raise httpx.ConnectError("x")

        with patch("services.manga.download_service.http_get_with_retry", side_effect=side_effect):
            success, err = download_chapter(
                chapter, svc, _manga(), None, "src_a", config, _FakeTracker(), 1, 1
            )

        assert success is False
        assert "imagens válidas" in err

    def test_debug_mode_logs_extra(self, tmp_path):
        svc = self._mock_service(pages=[])
        chapter = _ch("1")
        config = _config(tmp_path, debug=True)

        success, err = download_chapter(
            chapter, svc, _manga(), None, "src_a", config, _FakeTracker(), 1, 1
        )
        assert success is False

    def test_deletes_images_after_pdf_when_configured(self, tmp_path):
        svc = self._mock_service()
        chapter = _ch("7")
        manga = _manga("m1", "Bleach")
        config = _config(tmp_path, delete_images=True)
        tracker = _FakeTracker()

        img_data = b"\x89PNG" + b"\x00" * 2000
        mock_response = MagicMock()
        mock_response.content = img_data
        mock_response.headers = {"content-type": "image/png"}
        mock_response.raise_for_status.return_value = None

        with patch(
            "services.manga.download_service.http_get_with_retry", return_value=mock_response
        ):
            with patch("services.manga.download_service.create_pdf_from_images") as mock_pdf:

                def fake_pdf(src, dest, quality=85):
                    dest.write_bytes(b"PDF")

                mock_pdf.side_effect = fake_pdf
                success, _ = download_chapter(
                    chapter, svc, manga, "http://x/", "src_a", config, tracker, 1, 1
                )

        chapter_dir = tmp_path / manga.title / chapter.number
        remaining_images = list(chapter_dir.glob("*.png")) + list(chapter_dir.glob("*.jpg"))
        assert remaining_images == []


# ---------------------------------------------------------------------------
# prompt_download_range
# ---------------------------------------------------------------------------


class TestPromptDownloadRange:
    def test_returns_none_when_no_chapters(self):
        result = prompt_download_range(None, [])
        assert result is None

    def test_returns_none_on_keyboard_interrupt(self):
        chapters = [_ch("1"), _ch("2")]
        with patch("services.manga.download_service.inquirer") as mock_inq:
            mock_inq.text.return_value.execute.side_effect = KeyboardInterrupt
            result = prompt_download_range(None, chapters)
        assert result is None

    def test_returns_none_when_input_is_none(self):
        chapters = [_ch("1"), _ch("2")]
        with patch("services.manga.download_service.inquirer") as mock_inq:
            mock_inq.text.return_value.execute.return_value = None
            result = prompt_download_range(None, chapters)
        assert result is None

    def test_returns_chapters_for_valid_input(self):
        chapters = [_ch("1"), _ch("2"), _ch("3")]
        with patch("services.manga.download_service.inquirer") as mock_inq:
            mock_inq.text.return_value.execute.return_value = "1-2"
            result = prompt_download_range(None, chapters)
        assert result is not None
        numbers = [c.number for c in result]
        assert "1" in numbers
        assert "2" in numbers

    def test_invalid_range_returns_none(self):
        chapters = [_ch("1"), _ch("2")]
        with patch("services.manga.download_service.inquirer") as mock_inq:
            mock_inq.text.return_value.execute.return_value = "invalid!!!"
            with patch(
                "services.manga.download_service.parse_range_input", side_effect=ValueError("bad")
            ):
                result = prompt_download_range(None, chapters)
        assert result is None

    def test_includes_last_chapter_in_prompt(self):
        chapters = [_ch("5"), _ch("6")]
        with patch("services.manga.download_service.inquirer") as mock_inq:
            mock_inq.text.return_value.execute.return_value = None
            prompt_download_range("4", chapters)
        call_kwargs = mock_inq.text.call_args
        prompt_text = call_kwargs[1]["message"] if call_kwargs[1] else call_kwargs[0][0]
        assert "4" in prompt_text

    def test_returns_none_when_selection_empty(self):
        chapters = [_ch("1"), _ch("2")]
        with patch("services.manga.download_service.inquirer") as mock_inq:
            mock_inq.text.return_value.execute.return_value = "all"
            with patch("services.manga.download_service.parse_range_input", return_value=[]):
                result = prompt_download_range(None, chapters)
        assert result is None
