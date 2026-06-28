"""
Unit tests for anitube scraper episode ordering with ?ord=1 parameter.
"""

from unittest.mock import MagicMock, patch
from scrapers.plugins.anitube import AniTube


def _response(html: str) -> MagicMock:
    mock = MagicMock()
    mock.text = html
    mock.raise_for_status = MagicMock()
    return mock


class TestAnitubeEpisodeOrdering:
    """Test anitube scraper's handling of ?ord=1 parameter for episode ordering."""

    def test_ord_parameter_appended_to_clean_url(self):
        """Verify that ?ord=1 is appended to URLs without existing query parameters."""
        scraper = AniTube()

        with (
            patch("scrapers.plugins.anitube.httpx.get") as mock_get,
            patch("scrapers.plugins.anitube.rep"),
        ):
            mock_get.return_value = _response("<html></html>")

            # Call search_episodes with a clean URL
            base_url = "https://www.anitube.news/video/1030751/"
            scraper.search_episodes("Test Anime", base_url, None)

            # Verify that driver.fetch was called with the URL + ?ord=1
            expected_url = "https://www.anitube.news/video/1030751/?ord=1"
            mock_get.assert_called_once()
            assert mock_get.call_args.args[0] == expected_url

    def test_ord_parameter_appended_with_ampersand_to_existing_params(self):
        """Verify that ?ord=1 is appended with & when URL has existing query params."""
        scraper = AniTube()

        with (
            patch("scrapers.plugins.anitube.httpx.get") as mock_get,
            patch("scrapers.plugins.anitube.rep"),
        ):
            mock_get.return_value = _response("<html></html>")

            # Call search_episodes with a URL that already has query params
            base_url = "https://www.anitube.news/video/1030751/?existing=param"
            scraper.search_episodes("Test Anime", base_url, None)

            # Verify that driver.fetch was called with & separator
            expected_url = "https://www.anitube.news/video/1030751/?existing=param&ord=1"
            mock_get.assert_called_once()
            assert mock_get.call_args.args[0] == expected_url

    def test_episode_extraction_works_with_ord_parameter(self):
        """Verify that episode extraction still works correctly with ?ord=1."""
        scraper = AniTube()

        with (
            patch("scrapers.plugins.anitube.httpx.get") as mock_get,
            patch("scrapers.plugins.anitube.rep") as mock_rep,
        ):
            mock_get.return_value = _response(
                """
                <html><body>
                    <a href="https://www.anitube.news/video/123/episode-1" title="Test Anime – Episódio 1"></a>
                    <a href="https://www.anitube.news/video/123/episode-2" title="Test Anime – Episódio 2"></a>
                </body></html>
                """
            )

            # Call search_episodes
            base_url = "https://www.anitube.news/video/123/"
            scraper.search_episodes("Test Anime", base_url, None)

            # Verify that add_episode_list was called with extracted episodes
            mock_rep.add_episode_list.assert_called_once()
            call_args = mock_rep.add_episode_list.call_args

            # Check that titles and URLs were extracted
            assert len(call_args[0]) == 4  # anime, titles, urls, scraper_name
            assert isinstance(call_args[0][1], list)  # titles list
            assert isinstance(call_args[0][2], list)  # urls list
            assert len(call_args[0][1]) == 2  # 2 episodes
            assert len(call_args[0][2]) == 2  # 2 episodes  # 2 episodes

    def test_episode_extraction_does_not_filter_by_anime_title(self):
        """Verify that valid episode links are kept even when title formatting differs."""
        scraper = AniTube()

        with (
            patch("scrapers.plugins.anitube.httpx.get") as mock_get,
            patch("scrapers.plugins.anitube.rep") as mock_rep,
        ):
            mock_get.return_value = _response(
                """
                <html><body>
                    <a href="https://www.anitube.zip/video/1054054/" title="Yomi no Tsugai (Dublado) – Episódio 01"></a>
                </body></html>
                """
            )

            scraper.search_episodes(
                "Yomi no Tsugai Dublado", "https://www.anitube.zip/video/1054051/", None
            )

            mock_rep.add_episode_list.assert_called_once_with(
                "Yomi no Tsugai Dublado",
                ["Yomi no Tsugai (Dublado) – Episódio 01"],
                ["https://www.anitube.zip/video/1054054/"],
                "anitube",
            )
