"""Tests for the AnimesOnlineCloud scraper."""

from unittest.mock import MagicMock, patch

from scrapers.plugins.animesonlinecloud import AnimesOnlineCloud
from services.search_repository import SearchRepository


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
