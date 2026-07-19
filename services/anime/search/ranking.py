"""Anime result ranking using similarity scoring."""

from thefuzz import fuzz

from services.repository.search_repository import SearchRepository
from utils.title_utils import normalize_title_for_filter


def _rank_anime_results_by_reference(titles: list[str], reference_title: str) -> list[str]:
    """Rank title strings using the canonical AniList reference title."""
    reference_title = reference_title.split(" / ")[0]
    reference_normalized = normalize_title_for_filter(reference_title)
    reference_compact = SearchRepository._normalize_for_similarity(reference_title)
    reference_words = SearchRepository._normalize_words_for_similarity(reference_title)

    def contains_word_sequence(haystack: list[str], needle: list[str]) -> bool:
        if not needle:
            return True
        it = iter(haystack)
        return all(any(word == candidate for candidate in it) for word in needle)

    scored_titles = []
    for title in titles:
        base_title = title.split(" [")[0] if " [" in title else title
        normalized_title = normalize_title_for_filter(base_title)
        compact_title = SearchRepository._normalize_for_similarity(base_title)
        title_words = SearchRepository._normalize_words_for_similarity(base_title)

        score = max(
            fuzz.ratio(reference_normalized, normalized_title),
            fuzz.partial_ratio(reference_normalized, normalized_title),
            fuzz.token_sort_ratio(reference_normalized, normalized_title),
            fuzz.ratio(reference_compact, compact_title),
        )

        if reference_words and title_words[: len(reference_words)] == reference_words:
            score = min(100, score + 40)
        elif reference_normalized in normalized_title:
            score = min(100, score + 20)
        elif reference_compact in compact_title:
            score = min(100, score + 10)

        if contains_word_sequence(title_words, reference_words):
            score = min(100, score + 25)
        else:
            score = max(0, score - 25)

        # Prefer more specific titles over short prefix-only matches.
        if len(title_words) < len(reference_words):
            if title_words == reference_words[: len(title_words)]:
                score = 0
            else:
                score = max(0, score - 50)
        elif len(title_words) > len(reference_words):
            score = min(100, score + min(30, (len(title_words) - len(reference_words)) * 5))

        scored_titles.append((title, score, len(title_words), base_title))

    scored_titles.sort(key=lambda item: (-item[1], item[2], item[3]))
    return [item[0] for item in scored_titles]


def _best_similarity_score_for_reference(titles: list[str], reference_title: str) -> int:
    """Return the best similarity score between results and a reference title."""
    if not titles or not reference_title:
        return 0

    reference_normalized = normalize_title_for_filter(reference_title)
    reference_compact = SearchRepository._normalize_for_similarity(reference_title)
    best_score = 0

    for title in titles:
        base_title = title.split(" [")[0] if " [" in title else title
        normalized_title = normalize_title_for_filter(base_title)
        compact_title = SearchRepository._normalize_for_similarity(base_title)

        score = max(
            fuzz.ratio(reference_normalized, normalized_title),
            fuzz.partial_ratio(reference_normalized, normalized_title),
            fuzz.token_sort_ratio(reference_normalized, normalized_title),
            fuzz.ratio(reference_compact, compact_title),
        )
        best_score = max(best_score, score)

    return best_score
