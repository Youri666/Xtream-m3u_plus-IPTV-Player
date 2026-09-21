import unittest

from iptv_player.utils.search import (
    normalize_search_text,
    search_relevance_key,
    title_matches_search,
)


class NormalizeSearchTextTests(unittest.TestCase):
    def test_normalizes_case_accents_spaces_and_punctuation(self):
        self.assertEqual(
            normalize_search_text("  L'Été... en   FRANCE!  "),
            "l ete en france",
        )

    def test_accepts_empty_and_non_string_values(self):
        self.assertEqual(normalize_search_text(None), "")
        self.assertEqual(normalize_search_text(2026), "2026")


class TitleMatchesSearchTests(unittest.TestCase):
    def test_matches_all_partial_terms_in_any_position(self):
        self.assertTrue(title_matches_search("Le Fabuleux Destin d'Amélie", ["amel", "fabul"]))

    def test_rejects_title_when_one_term_is_missing(self):
        self.assertFalse(title_matches_search("Le Fabuleux Destin d'Amélie", ["amel", "paris"]))

    def test_repeated_terms_must_match_distinct_title_words(self):
        terms = ["dan", "da", "dan"]
        self.assertTrue(title_matches_search("[FR] DAN DA DAN (MULTI)", terms))
        self.assertFalse(title_matches_search("Dans la sauce", terms))
        self.assertFalse(title_matches_search("Danny Go!", terms))

    def test_matches_query_with_omitted_spaces(self):
        self.assertTrue(title_matches_search("[FR] DAN DA DAN (MULTI)", ["dandadan"]))
        self.assertTrue(title_matches_search("Star Wars", ["starwars"]))


class SearchRelevanceKeyTests(unittest.TestCase):
    def test_ranks_phrase_match_before_distributed_match(self):
        terms = ["amour", "est", "dans", "le", "pre"]
        direct = search_relevance_key("L'amour est dans le pré", terms)
        distributed = search_relevance_key(
            "Dans le grand jeu, l'amour est enfin préservé",
            terms,
        )
        self.assertLess(direct, distributed)

    def test_compact_phrase_has_direct_match_priority(self):
        self.assertEqual(search_relevance_key("DAN DA DAN", ["dandadan"]), (0,))


if __name__ == "__main__":
    unittest.main()

