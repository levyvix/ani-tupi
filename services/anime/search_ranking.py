"""Pure filtering and ranking helpers for anime search results."""

from services.repository.search_repository import SearchRepository
from utils.title_utils import normalize_title_for_filter


def filter_anime_results(titles: list[str], query: str) -> list[str]:
    """Filter anime titles using normalized and compact matching.

    This function filters a list of "Title [sources]" formatted strings
    using the repository's normalization rules plus a whitespace-insensitive
    compact form. The compact comparison is important for titles that appear
    concatenated in scraper sources, such as "himekishi", while the query
    may arrive as "hime kishi".

    Uses the same normalization logic as the repository to ensure
    consistent filtering behavior.

    Args:
        titles: List of anime titles in "Title [source1, source2]" format
        query: Query to filter by (e.g., "tate no yuusha no nariagari 2")

    Returns:
        Filtered list of titles where the normalized query appears in the
        normalized title, or the compact normalized query appears in the
        compact normalized title
    """
    from utils.title_normalization import get_compact_normalized_title_key
    from utils.title_utils import normalize_title_for_filter as normalize_fn

    query_normalized = normalize_fn(query)
    query_compact = get_compact_normalized_title_key(query_normalized)
    filtered = []

    for title in titles:
        # Extract base title (remove source indicators like "[source1, source2]")
        base_title = title.split(" [")[0] if " [" in title else title

        # Normalize title for comparison
        title_normalized = normalize_fn(base_title)
        title_compact = get_compact_normalized_title_key(title_normalized)
        title_words = title_normalized.split()
        query_words = query_normalized.split()

        if (
            query_normalized in title_normalized
            or query_compact in title_compact
            or all(word in title_words for word in query_words)
        ):
            filtered.append(title)

    return filtered


def rank_anime_results_by_reference(titles: list[str], reference_title: str) -> list[str]:
    """Rank title strings using the canonical AniList reference title."""
    reference_title = reference_title.split(" / ")[0]
    reference_normalized = normalize_title_for_filter(reference_title)
    reference_compact = SearchRepository._normalize_for_similarity(reference_title)
    reference_words = SearchRepository._normalize_words_for_similarity(reference_title)

    scored_titles = []
    for title in titles:
        base_title = title.split(" [")[0] if " [" in title else title
        normalized_title = normalize_title_for_filter(base_title)
        compact_title = SearchRepository._normalize_for_similarity(base_title)
        title_words = SearchRepository._normalize_words_for_similarity(base_title)

        score = SearchRepository._fuzz_score(
            reference_normalized,
            reference_compact,
            normalized_title,
            compact_title,
        )

        if reference_words and title_words[: len(reference_words)] == reference_words:
            score = min(100, score + 40)
        elif reference_normalized in normalized_title:
            score = min(100, score + 20)
        elif reference_compact in compact_title:
            score = min(100, score + 10)

        if SearchRepository._contains_word_sequence(title_words, reference_words):
            score = min(100, score + 25)
        else:
            score = max(0, score - 25)

        # Prefer more specific titles over short prefix-only matches.
        score = SearchRepository._apply_word_count_adjustment(score, title_words, reference_words)

        scored_titles.append((title, score, len(title_words), base_title))

    scored_titles.sort(key=lambda item: (-item[1], item[2], item[3]))
    return [item[0] for item in scored_titles]


def best_similarity_score_for_reference(titles: list[str], reference_title: str) -> int:
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

        score = SearchRepository._fuzz_score(
            reference_normalized,
            reference_compact,
            normalized_title,
            compact_title,
        )
        best_score = max(best_score, score)

    return best_score


__all__ = [
    "best_similarity_score_for_reference",
    "filter_anime_results",
    "rank_anime_results_by_reference",
]
