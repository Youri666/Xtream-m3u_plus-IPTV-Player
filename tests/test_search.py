import unittest

from iptv_player.utils.search import normalize_search_text, title_matches_search


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


if __name__ == "__main__":
    unittest.main()

