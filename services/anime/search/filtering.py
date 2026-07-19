"""Anime result filtering using normalized and compact matching."""


def _filter_anime_results(titles: list[str], query: str) -> list[str]:
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
    from services.anime.title_normalization import get_compact_normalized_title_key
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
