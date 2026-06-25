"""Title normalization utilities for anime search.

Handles title cleaning, variation generation, and bilingual title processing
for improved search results across different anime sources.
"""

import re
import unicodedata


# Normalize typographic apostrophe variants to straight apostrophe before any processing
def _normalize_apostrophes(text: str) -> str:
    return text.replace("’", "'").replace("‘", "'").replace("ʼ", "'")


_DUB_MARKERS = ("dublado", "dub", "dubbed")
_SUB_MARKERS = ("legendado", "legendadas", "sub", "subbed", "subtitles", "subtitle")

_SEASON_PATTERNS = (
    re.compile(r"\bseason\s+(\d+)\b", re.IGNORECASE),
    re.compile(r"\b(\d+)(?:st|nd|rd|th)\s+season\b", re.IGNORECASE),
    re.compile(r"\btemporada\s+(\d+)\b", re.IGNORECASE),
    re.compile(r"(?<=[\s])s(\d+)\b", re.IGNORECASE),
)
_PART_PATTERNS = (
    re.compile(r"\bpart\s+(\d+)(?:st|nd|rd|th)?\b", re.IGNORECASE),
    re.compile(r"\bcour\s+(\d+)\b", re.IGNORECASE),
)


def normalize_title_for_dedup(title: str) -> str:
    """Normalize title for deduplication across multiple sources.

    This normalization is designed for DISPLAY ONLY - converting to lowercase
    with only letters and numbers, while PRESERVING all meaningful information
    like language markers (Dublado, Legendado) and season indicators.

    Why separate from normalize_anime_title()?
    - normalize_anime_title(): For search queries (preserves flexibility for partial matches)
    - normalize_title_for_dedup(): For display normalization (clean format, lowercase)

    Handles:
    - Unicode normalization (accents: á → a, ç → c)
    - Separator normalization (: - | / \\ → space)
    - Case normalization to lowercase
    - Whitespace cleanup

    PRESERVES (not removed):
    - Language markers: Dublado, Legendado, Sub, Dub (these are important distinctions!)
    - Season information: Season 2, 2nd Season, Temporada 2 (part of title identity)
    - All meaningful content words

    Examples:
        "Anime A: Revolucao Dublado" → "anime a revolucao dublado"
        "Anime A - Revolucao Dublado" → "anime a revolucao dublado"
        "Jujutsu Kaisen Season 2 Dublado" → "jujutsu kaisen season 2 dublado"
        "My Hero Academia Part 6 Legendado" → "my hero academia part 6 legendado"
        "Hell's Paradise: Jigokuraku" → "hell's paradise jigokuraku"

    Args:
        title: Raw title from scraper (may include separators, accents, etc.)

    Returns:
        Normalized lowercase form with letters, numbers, spaces, and apostrophes only.
        Returns empty string if title becomes empty after normalization.
    """
    if not title or not title.strip():
        return ""

    # Early exit: if stripped input has no alphanumeric characters, return ""
    if not re.search(r"[a-zA-Z0-9]", title):
        return ""

    # Normalize typographic apostrophes before unicode normalization
    title = _normalize_apostrophes(title)

    # Step 1: Normalize Unicode
    # Decompose accents: "Café" → "Cafe"
    normalized = unicodedata.normalize("NFKD", title)
    # Remove combining marks (accents)
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")

    # Step 2: Normalize separators to spaces
    # Replace common separators with space
    for sep in [
        (":", " "),
        ("-", " "),
        ("–", " "),
        ("—", " "),
        ("|", " "),
        ("/", " "),
        ("\\", " "),
    ]:
        normalized = normalized.replace(sep[0], sep[1])

    # Step 3: Clean whitespace (collapse multiple spaces)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    # Step 4: Keep only alphanumerics, spaces, and apostrophes
    # (Apostrophes preserved for English titles like "Hell's Paradise")
    normalized = re.sub(r"[^A-Za-z0-9\s']", "", normalized)

    # Step 5: Clean whitespace again
    # Previous step may have created spaces where special chars were removed
    normalized = re.sub(r"\s+", " ", normalized).strip()

    # Step 6: Convert to lowercase
    # Final normalized form for display
    normalized = normalized.lower()

    # Return normalized form, or empty string if everything was removed
    return normalized


def get_compact_normalized_title_key(normalized_title: str) -> str:
    """Return whitespace-insensitive key from normalized title."""
    return normalized_title.replace(" ", "")


def get_language_version_markers(normalized_title: str) -> set[str]:
    """Extract language/version markers from normalized title.

    Only matches 'sub'/'dub' markers as the LAST word (trailing suffix position)
    to avoid false positives like "Sub Zero" or "Subaru".
    """
    marker_set = set()
    words = normalized_title.split()
    if not words:
        return marker_set

    # Check full word set for multi-character unambiguous markers
    word_set = set(words)
    dub_full = {"dublado", "dubbed"}
    sub_full = {"legendado", "legendadas", "subbed", "subtitles", "subtitle"}

    if any(marker in word_set for marker in dub_full):
        marker_set.add("dub")
    elif words[-1] == "dub":
        marker_set.add("dub")

    if any(marker in word_set for marker in sub_full):
        marker_set.add("sub")
    elif words[-1] == "sub":
        marker_set.add("sub")

    return marker_set


def are_language_version_markers_compatible(title_a: str, title_b: str) -> bool:
    """Allow compact-key dedup only when language/version markers align."""
    return get_language_version_markers(title_a) == get_language_version_markers(title_b)


def get_season_markers(normalized_title: str) -> set[tuple[str, int]]:
    """Extract season/part markers from normalized title."""
    markers = set()

    for pattern in _SEASON_PATTERNS:
        for match in pattern.findall(normalized_title):
            markers.add(("season", int(match)))

    for pattern in _PART_PATTERNS:
        for match in pattern.findall(normalized_title):
            markers.add(("part", int(match)))

    return markers


def are_season_markers_compatible(title_a: str, title_b: str) -> bool:
    """Allow compact-key dedup only when season markers align."""
    return get_season_markers(title_a) == get_season_markers(title_b)


def normalize_anime_title(title: str, is_english: bool = False):
    """Generate sensible title variations for searching.

    For AniList titles with format "Romaji / English", extracts just the english part.
    Example: "Kimetsu no Yaiba: Hashira Geiko-hen / Demon Slayer: Hashira Training Arc"
             → ["demon slayer hashira training arc", "demon slayer hashira training", "demon slayer hashira", "demon slayer"]

    Args:
        title: Title to normalize
        is_english: If True, preserves apostrophes (for English titles like "Hell's Paradise")

    Returns variations in lowercase, from most specific to most generic.
    """
    # 1. Handle AniList bilingual format "Romaji / English"
    # Take only the english part (after the " / ")
    if " / " in title:
        parts = title.split(" / ")
        # Use english if available (after " / "), otherwise keep original
        title = parts[1] if len(parts) > 1 else parts[0]
        is_english = True  # Auto-detect: if we split, second part is English

    # 2. Extract season numbers BEFORE removing season patterns
    # This preserves "2" from "2nd Season" or "Season 2"
    extracted_season = None
    season_match = re.search(
        r"(?:Season\s+|Temporada\s+)(\d+)|(\d+)(?:st|nd|rd|th)?\s+Season",
        title,
        re.IGNORECASE,
    )
    if season_match:
        extracted_season = season_match.group(1) or season_match.group(2)

    # 3. Remove season/part/episode suffixes
    season_patterns = [
        r"\s+Season\s+\d+",
        r"\s+\d+(?:st|nd|rd|th)\s+Season",
        r"\s+Temporada\s+\d+",
        r"\s+S\d+",
        r"\s+Part\s+\d+",
        r"\s+Cour\s+\d+",
        r"\s+Arc\s+[^:]+",
        r"\s+Final\s+Season",
        r"\s+2nd\s+Season",
        r"[:−-]\s*Season\s+\d+",
        r"\s+Dublado.*$",
    ]

    cleaned = title
    for pattern in season_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # If we extracted a season number, append it to preserve it
    if extracted_season:
        cleaned = f"{cleaned} {extracted_season}"

    # 3. Keep only letters, numbers, spaces (and apostrophes if English)
    if is_english:
        # Preserve apostrophes for English titles (e.g., "Hell's Paradise")
        cleaned = re.sub(r"[^A-Za-z0-9\s']", " ", cleaned)
    else:
        # Remove all special characters including apostrophes for Romaji
        cleaned = re.sub(r"[^A-Za-z0-9\s]", " ", cleaned)
    # Remove multiple spaces and trim
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        return [title.strip().lower()]  # fallback

    # 4. Convert to lowercase
    cleaned = cleaned.lower()

    # 5. Get words
    words = cleaned.split()

    # 6. Generate variations intelligently
    # For AniList with progressive search: only use full query
    # Let progressive search handle the word reduction automatically
    variations = []

    if len(words) > 0:
        # Always include full query first
        variations.append(" ".join(words))

    # Only generate shorter variations if disabled (for compatibility)
    # With progressive search enabled, let the search function handle word count
    use_progressive_search = len(words) > 3  # Same logic as repository

    if not use_progressive_search:
        # Then progressively shorter versions (fallback for short queries)
        if len(words) > 3:
            # Medium: try 3 words
            variations.append(" ".join(words[:3]))
        if len(words) > 2:
            # Shorter: try 2 words
            variations.append(" ".join(words[:2]))
        if len(words) > 1:
            # Minimal: try 1 word
            variations.append(" ".join(words[:1]))

    # Remove duplicates while preserving order
    seen = set()
    result = []
    for v in variations:
        if v not in seen:
            seen.add(v)
            result.append(v)

    return result


def normalize_search_cache_key(query: str, language: str = "pt-br") -> str:
    """Normalize query into a consistent cache key.

    Ensures that different variations of the same query produce identical cache keys.
    This enables:
    - "jigokuraku 2" == "Jigokuraku 2nd Season" == "JIGOKURAKU 2"
    - Multi-language support with separate cache entries
    - Consistent cache hits across different search attempts

    Args:
        query: Raw search query from user
        language: Language code (default: "pt-br")

    Returns:
        Normalized cache key in format: "search:{normalized}:{language}"

    Examples:
        >>> normalize_search_cache_key("jigokuraku 2")
        "search:jigokuraku-pt-br"
        >>> normalize_search_cache_key("Jigokuraku 2nd Season", "pt-br")
        "search:jigokuraku-pt-br"
        >>> normalize_search_cache_key("DANDADAN", "en-us")
        "search:dandadan-en-us"
    """
    if not query or not query.strip():
        return f"search:empty-{language}"

    # Normalize typographic apostrophes before unicode normalization
    query = _normalize_apostrophes(query)

    # Step 1: Normalize unicode (decompose accents, etc.)
    normalized = unicodedata.normalize("NFKD", query)
    # Remove combining marks (accents)
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")

    # Step 2: Convert to lowercase
    normalized = normalized.lower()

    # Step 3: Extract season numbers BEFORE removing season patterns
    # This preserves "2" from "2nd Season" or "Season 2"
    # For bare 's', require preceding whitespace to avoid matching start of title
    extracted_season = None
    season_match = re.search(
        r"(?:season\s+|temporada\s+|(?<=\s)s)(\d+)|(\d+)(?:st|nd|rd|th)?\s+season",
        normalized,
        re.IGNORECASE,
    )
    if season_match:
        extracted_season = season_match.group(1) or season_match.group(2)

    # Step 4: Remove season/part/episode/language suffixes
    season_patterns = [
        r"\s+season\s+\d+",
        r"\s+\d+(?:st|nd|rd|th)?\s+season",
        r"\s+temporada\s+\d+",
        r"\s+s\d+",
        r"\s+part\s+\d+(?:st|nd|rd|th)?",
        r"\s+cour\s+\d+",
        r"\s+arc\s+[^:]+",
        r"\s+final\s+season",
        r"\s+dublado.*$",
        r"\s+legendad[oa]s?\b.*$",
        r"\s+(?:sub|subbed|subtitles?)\b.*$",
    ]

    for pattern in season_patterns:
        normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE)

    # Step 5: If we extracted a season number, append it to preserve it
    if extracted_season:
        normalized = f"{normalized} {extracted_season}"

    # Step 6: Keep only letters, numbers, spaces, and apostrophes
    normalized = re.sub(r"[^a-z0-9\s']", " ", normalized)

    # Step 7: Remove multiple spaces and strip
    normalized = re.sub(r"\s+", " ", normalized).strip()

    # Step 8: Replace remaining spaces with dashes
    normalized = normalized.replace(" ", "-")

    # Fallback: if everything was removed, use original query hash
    if not normalized:
        normalized = "empty"

    return f"search:{normalized}:{language}"
