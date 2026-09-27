from pathlib import Path
import tempfile
import unittest

from iptv_player.storage.favorites import (
    account_favorites_file,
    create_custom_category,
    delete_custom_category,
    entries_in_custom_category,
    entries_in_favorite_order,
    load_custom_categories,
    migrate_legacy_favorites_file,
    rename_custom_category,
    reorder_custom_category,
    reorder_favorites,
    set_custom_category_membership,
    set_favorite,
)


class FavoriteStorageTests(unittest.TestCase):
    def test_each_account_uses_a_dedicated_favorites_file(self):
        base_file = Path("data") / "provider_favorites.json"
        first = account_favorites_file(base_file, "first-account")
        second = account_favorites_file(base_file, "second-account")

        self.assertEqual(
            first,
            Path("data") / "provider_favorites.first-account.json",
        )
        self.assertNotEqual(first, second)

    def test_moves_legacy_favorites_to_first_account(self):
        with tempfile.TemporaryDirectory() as directory:
            legacy_file = Path(directory) / "favorites.json"
            dedicated_file = Path(directory) / "provider_favorites.account.json"
            legacy_file.write_text('{"stream_ids": [10]}', encoding="utf-8")

            selected_file = migrate_legacy_favorites_file(
                legacy_file, dedicated_file
            )

            self.assertEqual(selected_file, dedicated_file)
            self.assertFalse(legacy_file.exists())
            self.assertEqual(
                entries_in_favorite_order(
                    dedicated_file,
                    "Movies",
                    [{"stream_id": 10, "favorite": True}],
                ),
                [{"stream_id": 10, "favorite": True}],
            )

    def test_add_moves_existing_id_to_end_without_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "favorites.json"
            set_favorite(str(file_path), "Movies", 10, True)
            set_favorite(str(file_path), "Movies", 20, True)
            set_favorite(str(file_path), "Movies", 10, True)

            entries = [
                {"stream_id": 10, "favorite": True},
                {"stream_id": 20, "favorite": True},
            ]
            ordered = entries_in_favorite_order(str(file_path), "Movies", entries)
            self.assertEqual([entry["stream_id"] for entry in ordered], [20, 10])

    def test_remove_preserves_other_content_types(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "favorites.json"
            set_favorite(str(file_path), "Movies", 10, True)
            set_favorite(str(file_path), "Series", 30, True)
            set_favorite(str(file_path), "Movies", 10, False)

            series = [{"series_id": 30, "favorite": True}]
            self.assertEqual(
                entries_in_favorite_order(str(file_path), "Series", series),
                series,
            )

    def test_missing_order_falls_back_to_catalog_favorite_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "favorites.json"
            entries = [
                {"stream_id": 1, "favorite": False},
                {"stream_id": 2, "favorite": True},
            ]

            self.assertEqual(
                entries_in_favorite_order(str(file_path), "Live", entries),
                [entries[1]],
            )

    def test_reorders_favorites_without_position_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "favorites.json"
            set_favorite(str(file_path), "Movies", 10, True)
            set_favorite(str(file_path), "Movies", 20, True)
            set_favorite(str(file_path), "Movies", 30, True)

            reorder_favorites(str(file_path), "Movies", [30, 10, 20])

            entries = [
                {"stream_id": 10, "favorite": True},
                {"stream_id": 20, "favorite": True},
                {"stream_id": 30, "favorite": True},
            ]
            ordered = entries_in_favorite_order(str(file_path), "Movies", entries)
            self.assertEqual(
                [entry["stream_id"] for entry in ordered], [30, 10, 20]
            )

    def test_reordering_movies_preserves_unrelated_shared_stream_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "favorites.json"
            file_path.write_text(
                '{"stream_ids": [10, 999, 20]}', encoding="utf-8"
            )

            reorder_favorites(str(file_path), "Movies", [20, 10])

            entries = [
                {"stream_id": 10, "favorite": True},
                {"stream_id": 20, "favorite": True},
            ]
            ordered = entries_in_favorite_order(str(file_path), "Movies", entries)
            self.assertEqual([entry["stream_id"] for entry in ordered], [20, 10])

    def test_reorders_series_using_series_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "favorites.json"
            set_favorite(str(file_path), "Series", 10, True)
            set_favorite(str(file_path), "Series", 20, True)
            set_favorite(str(file_path), "Series", 30, True)

            reorder_favorites(str(file_path), "Series", [30, 10, 20])

            entries = [
                {"series_id": 10, "favorite": True},
                {"series_id": 20, "favorite": True},
                {"series_id": 30, "favorite": True},
            ]
            ordered = entries_in_favorite_order(str(file_path), "Series", entries)
            self.assertEqual(
                [entry["series_id"] for entry in ordered], [30, 10, 20]
            )

    def test_custom_live_category_lifecycle_and_membership(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "favorites.json"
            category_id = create_custom_category(file_path, "LIVE", "Sports")

            self.assertIsNotNone(category_id)
            self.assertIsNone(create_custom_category(
                file_path, "LIVE", "sports"
            ))
            self.assertTrue(set_custom_category_membership(
                file_path, "LIVE", category_id, [20, 10], True
            ))
            self.assertTrue(set_custom_category_membership(
                file_path, "LIVE", category_id, [30, 20], True
            ))
            self.assertEqual(
                load_custom_categories(file_path, "LIVE")[0]["stream_ids"],
                [10, 30, 20],
            )

            entries = [
                {"stream_id": 10}, {"stream_id": 20}, {"stream_id": 30}
            ]
            ordered = entries_in_custom_category(
                file_path, "LIVE", category_id, entries
            )
            self.assertEqual(
                [entry["stream_id"] for entry in ordered], [10, 30, 20]
            )

            self.assertTrue(reorder_custom_category(
                file_path, "LIVE", category_id, [30, 10, 20]
            ))
            self.assertTrue(set_custom_category_membership(
                file_path, "LIVE", category_id, [10], False
            ))
            self.assertTrue(rename_custom_category(
                file_path, "LIVE", category_id, "Documentaries"
            ))
            category = load_custom_categories(file_path, "LIVE")[0]
            self.assertEqual(category["name"], "Documentaries")
            self.assertEqual(category["stream_ids"], [30, 20])

            self.assertTrue(delete_custom_category(
                file_path, "LIVE", category_id
            ))
            self.assertEqual(load_custom_categories(file_path, "LIVE"), [])

    def test_custom_series_categories_use_series_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "favorites.json"
            category_id = create_custom_category(file_path, "Series", "Anime")
            set_custom_category_membership(
                file_path, "Series", category_id, [42], True
            )

            entries = [
                {"series_id": 42, "name": "Series"},
                {"series_id": 99, "name": "Other"},
            ]
            self.assertEqual(
                entries_in_custom_category(
                    file_path, "Series", category_id, entries
                ),
                [entries[0]],
            )
            self.assertEqual(load_custom_categories(file_path, "Movies"), [])


if __name__ == "__main__":
    unittest.main()
