from pathlib import Path
import tempfile
import unittest

from iptv_player.storage.favorites import entries_in_favorite_order, set_favorite


class FavoriteStorageTests(unittest.TestCase):
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
