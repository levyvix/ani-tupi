"""Tests for the AnimesOnlineCloud scraper."""

from threading import Event
from unittest.mock import MagicMock, patch

import httpx
import pytest

from scrapers.plugins.animesonlinecloud import AnimesOnlineCloud
from scrapers.plugins.utils import CloudflareChallengeError
from services.repository.search_repository import SearchRepository


SEARCH_HTML = """
<html><body>
  <article>
    <div class="details">
      <div class="title">
        <a href="https://animesonline.cloud/anime/shikanoko-nokonoko-koshitantan/">
          Shikanoko Nokonoko Koshitantan Todos os Episódios
        </a>
      </div>
    </div>
  </article>
</body></html>
"""


def _html_response(html: str) -> MagicMock:
    response = MagicMock()
    response.text = html
    response.raise_for_status = MagicMock()
    return response


def _cloudflare_error(url: str) -> CloudflareChallengeError:
    request = httpx.Request("GET", url)
    response = httpx.Response(
        403,
        request=request,
        headers={"cf-mitigated": "challenge", "server": "cloudflare"},
    )
    return CloudflareChallengeError(
        f"Automated access to {url} requires a browser challenge from Cloudflare",
        request=request,
        response=response,
    )


class TestAnimesOnlineCloudScraper:
    def setup_method(self) -> None:
        SearchRepository.reset_singleton()
        self.scraper = AnimesOnlineCloud()

    def teardown_method(self) -> None:
        SearchRepository.reset_singleton()

    @patch("scrapers.plugins.animesonlinecloud.http_get_with_retry")
    def test_search_removes_all_episodes_suffix_to_enable_source_merge(self, mock_get) -> None:
        mock_get.return_value = _html_response(SEARCH_HTML)

        result = self.scraper.search_anime("shikanoko")

        assert result[0].title == "Shikanoko Nokonoko Koshitantan"

        repository = SearchRepository()
        repository.add_anime(
            "shikanoko nokonoko koshitantan",
            "https://another-source.example/anime/shikanoko",
            "animefire",
            {},
        )
        repository.add_anime(result[0].title, result[0].url, result[0].source, {})

        assert len(repository.anime_to_urls) == 1
        assert {source for _, source, _ in next(iter(repository.anime_to_urls.values()))} == {
            "animefire",
            "animesonlinecloud",
        }

    @patch("scrapers.plugins.animesonlinecloud.logger.warning")
    @patch("scrapers.plugins.animesonlinecloud.http_get_with_retry")
    def test_search_warns_when_cloudflare_requires_browser(self, mock_get, mock_warning) -> None:
        url = "https://animesonline.cloud/?s=naruto"
        mock_get.side_effect = _cloudflare_error(url)

        result = self.scraper.search_anime("naruto")

        assert result == []
        assert "Cloudflare" in mock_warning.call_args.args[0]

    @patch("scrapers.plugins.animesonlinecloud.logger.warning")
    @patch("scrapers.plugins.animesonlinecloud.http_get_with_retry")
    def test_episode_search_warns_when_cloudflare_requires_browser(
        self, mock_get, mock_warning
    ) -> None:
        url = "https://animesonline.cloud/anime/naruto/"
        mock_get.side_effect = _cloudflare_error(url)

        result = self.scraper.search_episodes("Naruto", url, None)

        assert result == []
        assert "Cloudflare" in mock_warning.call_args.args[0]

    @patch("scrapers.plugins.animesonlinecloud.http_get_with_retry")
    def test_player_reports_cloudflare_challenge_without_masking_error(self, mock_get) -> None:
        url = "https://animesonline.cloud/episodio/example-episodio-1/"
        mock_get.side_effect = _cloudflare_error(url)

        with pytest.raises(RuntimeError, match="requires a browser challenge") as exc_info:
            self.scraper.search_player_src(url, [], Event())

        assert str(exc_info.value).startswith("AnimesOnlineCloud: ")
        assert isinstance(exc_info.value.__cause__, CloudflareChallengeError)
