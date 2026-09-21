import unittest

from iptv_player.provider.catalog import (
    normalized_stream_type,
    prepare_catalog_entries,
)


class CatalogPreparationTests(unittest.TestCase):
    def test_normalizes_provider_stream_labels(self):
        self.assertEqual(normalized_stream_type("live_stream"), "live")
        self.assertEqual(normalized_stream_type("movie_archive"), "movie")
        self.assertEqual(normalized_stream_type("series"), "series")

    def test_adds_urls_and_favorite_state(self):
        entries = {
            "LIVE": [
                {"stream_type": "live", "stream_id": 10, "container_extension": "ts"}
            ],
            "Movies": [
                {"stream_type": "movie", "stream_id": 20, "container_extension": "mkv"}
            ],
            "Series": [{"series_id": 30}],
        }
        calls = []

        def build_url(stream_type, stream_id, extension):
            calls.append((stream_type, stream_id, extension))
            return f"url:{stream_type}:{stream_id}:{extension}"

        result = prepare_catalog_entries(
            entries,
            {"stream_ids": [20], "series_ids": [30]},
            build_url,
        )

        self.assertFalse(result["LIVE"][0]["favorite"])
        self.assertTrue(result["Movies"][0]["favorite"])
        self.assertTrue(result["Series"][0]["favorite"])
        self.assertEqual(result["Series"][0]["stream_type"], "series")
        self.assertEqual(result["LIVE"][0]["url"], "url:live:10:ts")
        self.assertIn(("movie", 20, "mkv"), calls)

    def test_false_stream_id_has_no_playable_url(self):
        entries = {
            "LIVE": [{"stream_type": "live", "stream_id": 0}],
            "Movies": [],
            "Series": [],
        }

        result = prepare_catalog_entries(entries, {}, lambda *_: "unexpected")

        self.assertIsNone(result["LIVE"][0]["url"])


if __name__ == "__main__":
    unittest.main()

