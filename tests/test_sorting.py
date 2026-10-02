import unittest

from iptv_player.utils.sorting import ordered_catalog_entries, ordered_season_keys, provider_rating


class CatalogSortingTests(unittest.TestCase):
    def test_rating_orders_keep_unrated_last_and_ties_stable(self):
        entries = [
            {'name': 'Unrated'}, {'name': 'First tie', 'rating': '8'},
            {'name': 'Low', 'rating': 3}, {'name': 'Second tie', 'rating': 8},
            {'name': 'Invalid', 'rating': 'NaN'}, {'name': 'Zero', 'rating': 0},
        ]
        high = ordered_catalog_entries(entries, True, rating_order=2)
        low = ordered_catalog_entries(entries, True, rating_order=3)
        self.assertEqual([e['name'] for e in high],
                         ['First tie', 'Second tie', 'Low', 'Unrated', 'Invalid', 'Zero'])
        self.assertEqual([e['name'] for e in low],
                         ['Low', 'First tie', 'Second tie', 'Unrated', 'Invalid', 'Zero'])
        self.assertEqual(entries[0]['name'], 'Unrated')

    def test_rating_parser_handles_provider_formats_and_rejects_invalid_values(self):
        self.assertEqual(provider_rating({'rating': ' 8,5 '}), 8.5)
        self.assertEqual(provider_rating({'rating': '', 'rating_5based': '4.5'}), 9)
        self.assertEqual(provider_rating({'rating': 7, 'rating_5based': 5}), 7)
        for value in (None, '', 'N/A', 'inf', '-inf', 'NaN', -1, 0, 11, True, []):
            self.assertIsNone(provider_rating({'rating': value}))

    def test_all_unrated_entries_retain_provider_order(self):
        entries = [{'name': 'Zulu'}, {'name': 'Alpha', 'rating': 0}]
        for order in (2, 3):
            self.assertEqual(ordered_catalog_entries(entries, True, rating_order=order), entries)

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
