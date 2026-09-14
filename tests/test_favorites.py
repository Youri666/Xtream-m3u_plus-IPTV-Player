from pathlib import Path
import tempfile
import unittest

from iptv_player.storage.favorites import (
    account_favorites_file,
    entries_in_favorite_order,
    migrate_legacy_favorites_file,
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

    def test_initializes_empty_favorites_for_a_new_account(self):
        with tempfile.TemporaryDirectory() as directory:
            legacy_file = Path(directory) / "favorites.json"
            dedicated_file = Path(directory) / "provider_favorites.account.json"

            selected_file = migrate_legacy_favorites_file(
                legacy_file, dedicated_file
            )

            self.assertEqual(selected_file, dedicated_file)
            self.assertTrue(dedicated_file.is_file())
            self.assertEqual(dedicated_file.read_text(encoding="utf-8"), "{}")

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


if __name__ == "__main__":
    unittest.main()
