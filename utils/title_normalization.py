"""Title normalization utilities for anime search.

Handles title cleaning, variation generation, and bilingual title processing
for improved search results across different anime sources.
"""

import re
import unicodedata

from thefuzz import fuzz


# Normalize typographic apostrophe variants to straight apostrophe before any processing
__all__ = [
    "are_language_version_markers_compatible",
    "are_season_markers_compatible",
    "dedup_signature",
    "get_compact_normalized_title_key",
    "get_language_version_markers",
    "get_season_markers",
    "normalize_anime_title",
    "normalize_search_cache_key",
    "normalize_title_for_dedup",
    "roman_to_int",
    "signatures_merge",
]


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


_SEASON_EXPLICIT_PATTERNS = (
    re.compile(r"\bseason\s+(\d+)\b"),
    # Ordinal is optional so "2 season" (goyabu) matches like "2nd season".
    re.compile(r"\b(\d+)(?:st|nd|rd|th)?\s+season\b"),
    re.compile(r"\btemporada\s+(\d+)\b"),
    re.compile(r"\bparte\s+(\d+)\b"),
    re.compile(r"\bpart\s+(\d+)\b"),
    re.compile(r"\bcour\s+(\d+)\b"),
    re.compile(r"(?<=\s)s(\d+)\b"),
)
_BARE_TRAILING_NUMBER = re.compile(r"\s(\d{1,2})$")
_LANGUAGE_WORDS = _DUB_MARKERS + _SUB_MARKERS

# Scraper boilerplate that carries no title identity (e.g. anitube's
# "... Todos os Episódios", MAL-style "(TV)" media tags). Stripped before season
# extraction so it never leaks into the base key. Accents are already removed by
# normalize_title_for_dedup, and parentheses collapsed to bare words.
# Kept deliberately narrow: a bare "online" would wrongly gut "Sword Art Online".
_JUNK_PHRASES = (
    re.compile(r"\btodos\s+(?:os\s+)?episodios?\b"),
    re.compile(r"\btv\b"),
)
# Cross-language synonyms canonicalized to one token so equivalent labels merge.
# We canonicalize rather than delete: dropping "movie" outright would collapse a
# film into its parent series (e.g. "Detective Conan Movie 1" -> the TV series).
_SYNONYMS = ((re.compile(r"\bfilme\b"), "movie"),)

# Roman numerals used as season/part markers (e.g. "Parte III", "Overlord III").
_ROMAN_VALUES = {
    "i": 1,
    "ii": 2,
    "iii": 3,
    "iv": 4,
    "v": 5,
    "vi": 6,
    "vii": 7,
    "viii": 8,
    "ix": 9,
    "x": 10,
    "xi": 11,
    "xii": 12,
    "xiii": 13,
    "xiv": 14,
    "xv": 15,
    "xvi": 16,
    "xvii": 17,
    "xviii": 18,
    "xix": 19,
    "xx": 20,
}
# Season/part keywords after which even a single-letter roman (Parte I / Parte V)
# is unambiguously a numeral. Outside this context single letters are left alone
# so titles like "Hunter x Hunter" survive untouched.
_SEASON_KEYWORD = r"(?:season|temporada|parte|part|cour)"
_KEYWORD_ROMAN_RE = re.compile(rf"\b({_SEASON_KEYWORD})\s+([ivx]+)\b", re.IGNORECASE)
# Standalone romans are only converted when at least two letters long.
_STANDALONE_ROMAN_RE = re.compile(r"\b([ivx]{2,})\b", re.IGNORECASE)

# Series numeral sitting between the base name and a subtitle separator
# ("Mushoku Tensei III: Isekai Ittara Honki Dasu"). Matched on the RAW title,
# because normalize_title_for_dedup() collapses separators into spaces and the
# separator is exactly what tells a season numeral apart from a numeral that
# belongs to the name ("Jujutsu Kaisen 0", "Mob Psycho 100", "86 Eighty-Six").
# Requirements encoded here: at least one preceding token (so "86: Eighty Six"
# is untouched), the numeral as a whole token, and a subtitle after the separator.
_MID_TITLE_SERIES_NUMERAL = re.compile(
    r"(?<=\S)\s+(\d{1,2}|[ivx]{2,})\s*(?=[:\-–—|]\s*\S)", re.IGNORECASE
)


def roman_to_int(token: str) -> int | None:
    """Return the integer value of a roman numeral token, or None if unknown."""
    return _ROMAN_VALUES.get(token.lower())


def _normalize_roman_seasons(text: str) -> str:
    """Rewrite roman-numeral season/part markers as arabic digits.

    Keyword-scoped conversion handles single-letter numerals ("Parte I" -> "parte 1");
    the standalone pass only touches multi-letter romans so ambiguous single letters
    (the "x" in "Hunter x Hunter") are preserved.
    """

    def _keyword(match: re.Match) -> str:
        value = roman_to_int(match.group(2))
        return f"{match.group(1)} {value}" if value is not None else match.group(0)

    def _standalone(match: re.Match) -> str:
        value = roman_to_int(match.group(1))
        return str(value) if value is not None else match.group(0)

    text = _KEYWORD_ROMAN_RE.sub(_keyword, text)
    return _STANDALONE_ROMAN_RE.sub(_standalone, text)


def _strip_mid_title_series_numeral(title: str) -> tuple[str, int | None]:
    """Pull a series numeral that precedes a subtitle separator out of the title.

    Returns the title without the numeral plus its value, or the title unchanged
    and ``None`` when there is no such numeral. A single-letter roman ("Mushoku
    Tensei I: ...") is deliberately not recognized, mirroring
    :data:`_STANDALONE_ROMAN_RE`: it is indistinguishable from a real word.
    """
    match = _MID_TITLE_SERIES_NUMERAL.search(title)
    if not match:
        return title, None

    token = match.group(1)
    value = int(token) if token.isdigit() else roman_to_int(token)
    if value is None or not (1 <= value <= 99):
        return title, None

    return title[: match.start()] + title[match.end() :], value


def dedup_signature(title: str) -> tuple[str, int | None, frozenset[str]]:
    """Reduce a title to a merge signature: (base_key, season_num, lang_markers).

    Titles from different sources merge iff their signatures are equal. Season is
    extracted from explicit wordings (season N / Nth season / temporada N / parte N
    / part N / cour N / sN, roman or arabic) or, failing that, a trailing bare
    number 2-99. Season 1 (or absent) normalizes to None. Language and season tokens
    are stripped from the base so wording differs but signatures match.

    "Legendado"/sub is the implicit default in the pt-br ecosystem: sources that omit
    a language marker are subtitled. Only an explicit dub distinguishes a release, so
    sub-marked and unmarked titles share a signature and merge.
    """
    title, mid_title_season = _strip_mid_title_series_numeral(title)
    normalized = normalize_title_for_dedup(title)
    lang_markers = frozenset(get_language_version_markers(normalized)) & {"dub"}

    base = _normalize_roman_seasons(normalized)
    # Strip language words and scraper boilerplate first so a trailing season
    # number is exposed and junk never leaks into the base key.
    for word in _LANGUAGE_WORDS:
        base = re.sub(rf"\b{word}\b", " ", base)
    for junk in _JUNK_PHRASES:
        base = junk.sub(" ", base)
    for pattern, canonical in _SYNONYMS:
        base = pattern.sub(canonical, base)
    base = re.sub(r"\s+", " ", base).strip()

    season: int | None = None
    for pattern in _SEASON_EXPLICIT_PATTERNS:
        match = pattern.search(base)
        if match:
            season = int(match.group(1))
            base = pattern.sub(" ", base)
            break
    else:
        if mid_title_season is not None:
            season = mid_title_season
        else:
            match = _BARE_TRAILING_NUMBER.search(base)
            if match:
                candidate = int(match.group(1))
                if 2 <= candidate <= 99:
                    season = candidate
                    base = _BARE_TRAILING_NUMBER.sub("", base)

    if season == 1:
        season = None

    base = re.sub(r"\s+", " ", base).strip()
    base_key = base.replace(" ", "")
    return base_key, season, lang_markers


# Guards for the fuzzy cross-source merge fallback. Sources transliterate romaji
# inconsistently ("Caramelise" vs "Carameliser"), so base keys that differ only by
# minor spelling variance never merge under exact matching and the fallback stays
# disabled. The length floor keeps short titles on exact matching (where a single
# edit is proportionally huge), and the ratio was calibrated so real variants score
# ~98 while distinct titles stay <=80.
_FUZZY_MERGE_MIN_LEN = 8
_FUZZY_MERGE_THRESHOLD = 90
# Digits inside a base key carry series identity (season numeral left in place,
# "Jujutsu Kaisen 0", "Mob Psycho 100"). The longer the title, the cheaper a
# one-digit difference looks to fuzz.ratio — so numeric tokens are compared
# exactly instead of being left to the ratio.
_DIGIT_RUN_RE = re.compile(r"\d+")


def signatures_merge(
    sig_a: tuple[str, int | None, frozenset[str]],
    sig_b: tuple[str, int | None, frozenset[str]],
) -> bool:
    """Return True when two dedup signatures should merge into one entry.

    Exact equality always merges. As a fallback, base keys that differ only by
    minor transliteration variance merge — but ONLY when season, language markers
    and numeric tokens are identical, so the dub/leg/season separation that
    :func:`dedup_signature` encodes is never collapsed.
    """
    if sig_a == sig_b:
        return True

    base_a, season_a, lang_a = sig_a
    base_b, season_b, lang_b = sig_b
    if season_a != season_b or lang_a != lang_b:
        return False
    if _DIGIT_RUN_RE.findall(base_a) != _DIGIT_RUN_RE.findall(base_b):
        return False
    if len(base_a) < _FUZZY_MERGE_MIN_LEN or len(base_b) < _FUZZY_MERGE_MIN_LEN:
        return False
    return fuzz.ratio(base_a, base_b) >= _FUZZY_MERGE_THRESHOLD


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
