import unittest

from iptv_player.utils.sorting import ordered_catalog_entries, ordered_season_keys


class CatalogSortingTests(unittest.TestCase):
    def test_catalog_sort_is_case_insensitive_and_does_not_mutate_input(self):
        entries = [{"name": "zulu"}, {"name": "Alpha"}, {"name": "beta"}]

        ordered = ordered_catalog_entries(entries, True)

        self.assertEqual([entry["name"] for entry in ordered], ["Alpha", "beta", "zulu"])
        self.assertEqual(entries[0]["name"], "zulu")

    def test_disabled_catalog_sort_preserves_provider_order(self):
        entries = [{"name": "Second"}, {"name": "First"}]

        self.assertEqual(ordered_catalog_entries(entries, False), entries)

    def test_catalog_sort_accepts_an_alternate_title_field(self):
        entries = [{"title": "Zulu"}, {"title": "alpha"}]

        ordered = ordered_catalog_entries(
            entries, True, title_key="title"
        )

        self.assertEqual([entry["title"] for entry in ordered], ["alpha", "Zulu"])

    def test_catalog_sort_ignores_accents_punctuation_and_invisible_marks(self):
        entries = [
            {"name": "[FR] \u200bPapa à plein temps"},
            {"name": "[FR] Élise sous Emprise"},
            {"name": "[FR] Youngblood"},
        ]

        ordered = ordered_catalog_entries(entries, True, descending=True)

        self.assertEqual(
            [entry["name"] for entry in ordered],
            [
                "[FR] Youngblood",
                "[FR] \u200bPapa à plein temps",
                "[FR] Élise sous Emprise",
            ],
        )

    def test_seasons_use_numeric_order_before_named_entries(self):
        seasons = ["10", "Specials", "2", "1"]

        self.assertEqual(
            ordered_season_keys(seasons),
            ["1", "2", "10", "Specials"],
        )
        self.assertEqual(
            ordered_season_keys(seasons, descending=True),
            ["Specials", "10", "2", "1"],
        )


if __name__ == "__main__":
    unittest.main()
