"""Text normalization and title matching used by catalog searches."""

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
    """Match every query term as a partial word anywhere in the normalized title."""
    normalized_title = normalize_search_text(title)
    return all(term in normalized_title for term in search_terms)

