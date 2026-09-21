"""Text normalization and title matching used by catalog searches."""

from functools import lru_cache
import unicodedata


def normalize_search_text(value):
    """Return searchable text without case, accents, punctuation, or extra spaces."""
    decomposed = unicodedata.normalize("NFKD", str(value or "").casefold())
    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    words_and_spaces = "".join(
        character if character.isalnum() else " "
        for character in without_accents
    )
    return " ".join(words_and_spaces.split())


def title_matches_search(title, search_terms):
    """Match normalized query words, including queries with omitted spaces."""
    title_words = normalize_search_text(title).split()
    query_words = normalize_search_text(" ".join(search_terms)).split()
    if not query_words:
        return True

    compact_title = "".join(title_words)
    compact_query = "".join(query_words)
    if compact_query in compact_title:
        return True

    # Assign every query word to a different title word. This prevents repeated
    # terms such as "dan da dan" from all matching the same occurrence.
    @lru_cache(maxsize=None)
    def match_word(query_index, used_title_words):
        if query_index == len(query_words):
            return True

        query_word = query_words[query_index]
        for title_index, title_word in enumerate(title_words):
            title_word_bit = 1 << title_index
            if used_title_words & title_word_bit or query_word not in title_word:
                continue
            if match_word(query_index + 1, used_title_words | title_word_bit):
                return True
        return False

    return match_word(0, 0)


def search_relevance_key(title, search_terms):
    """Rank direct phrase matches before matches spread across a title."""
    normalized_title = normalize_search_text(title)
    normalized_query = normalize_search_text(" ".join(search_terms))
    if normalized_query in normalized_title:
        return (0,)
    if normalized_query.replace(" ", "") in normalized_title.replace(" ", ""):
        return (0,)
    return (1,)

