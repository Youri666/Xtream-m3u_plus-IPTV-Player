import unicodedata


def normalize_search_text(value):
    """Return searchable text without case, accents, punctuation, or extra spaces."""
    decomposed = unicodedata.normalize('NFKD', str(value or '').casefold())
    without_accents = ''.join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    words_and_spaces = ''.join(
        character if character.isalnum() else ' '
        for character in without_accents
    )
    return ' '.join(words_and_spaces.split())


def title_matches_search(title, search_terms):
    """Match every partial query term against a distinct normalized title word."""
    title_words = normalize_search_text(title).split()
    normalized_terms = [
        word
        for term in search_terms
        for word in normalize_search_text(term).split()
    ]

    # Match longer terms first, then backtrack when two partial terms can use the
    # same title word. This prevents one word such as "dans" from satisfying every
    # term in a query such as "dan da dan".
    normalized_terms.sort(key=len, reverse=True)

    match_cache = {}

    def assign_term(term_index, used_word_mask):
        cache_key = (term_index, used_word_mask)
        if cache_key in match_cache:
            return match_cache[cache_key]
        if term_index >= len(normalized_terms):
            return True

        term = normalized_terms[term_index]
        for word_index, word in enumerate(title_words):
            word_bit = 1 << word_index
            if used_word_mask & word_bit or term not in word:
                continue
            if assign_term(term_index + 1, used_word_mask | word_bit):
                match_cache[cache_key] = True
                return True
        match_cache[cache_key] = False
        return False

    return assign_term(0, 0)


def search_relevance_key(title, search_terms):
    """Place contiguous query phrases before distributed partial matches."""
    normalized_title = normalize_search_text(title)
    normalized_query = normalize_search_text(" ".join(search_terms))
    return (0,) if normalized_query and normalized_query in normalized_title else (1,)
