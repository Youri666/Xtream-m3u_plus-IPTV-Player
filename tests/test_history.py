from pathlib import Path
import tempfile
import unittest

from iptv_player.storage.history import (
    load_history,
    record_history,
    remove_history_entry,
    repair_misclassified_history,
    resume_position,
)


class PlaybackHistoryTests(unittest.TestCase):
    def test_updates_existing_item_and_limits_each_content_type(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "history.json"
            record_history(filename, self._entry("movie-1", "Movies", "First"), 1)
            record_history(filename, self._entry("live-1", "LIVE", "News"), 1)
            record_history(filename, self._entry("movie-2", "Movies", "Second"), 1)
            record_history(
                filename,
                self._entry("movie-2", "Movies", "Second", position_ms=42_000),
                1,
            )

            entries = load_history(filename)

            self.assertEqual([item["key"] for item in entries], ["movie-2", "live-1"])
            self.assertEqual(entries[0]["position_ms"], 42_000)

    def test_resume_position_ignores_opening_and_completed_media(self):
        self.assertEqual(resume_position({"position_ms": 999, "duration_ms": 90_000}), 0)
        self.assertEqual(resume_position({"position_ms": 1_353, "duration_ms": 90_000}), 1_353)
        self.assertEqual(resume_position({"position_ms": 80_000, "duration_ms": 90_000}), 0)
        self.assertEqual(
            resume_position({"position_ms": 40_000, "duration_ms": 90_000}),
            40_000,
        )

    def test_removes_one_unavailable_history_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "history.json"
            record_history(filename, self._entry("movie-1", "Movies", "First"), 10)
            record_history(filename, self._entry("movie-2", "Movies", "Second"), 10)

            self.assertTrue(remove_history_entry(filename, "movie-1"))
            self.assertFalse(remove_history_entry(filename, "missing"))
            self.assertEqual(
                [entry["key"] for entry in load_history(filename)],
                ["movie-2"],
            )

    def test_private_url_and_account_id_are_not_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "history.json"
            entry = self._entry("movie-1", "Movies", "Example")
            entry["url"] = "http://provider/user/password/movie.mkv"
            entry["account_id"] = "account123"

            record_history(filename, entry, 10)

            saved = load_history(filename)[0]
            self.assertNotIn("url", saved)
            self.assertNotIn("account_id", saved)

    def test_does_not_persist_runtime_track_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "history.json"
            entry = self._entry("movie-1", "Movies", "Example", 42_000)
            entry.update({
                "audio_track_name": "French",
                "subtitle_track_id": 4,
                "subtitle_track_name": "Forced French",
            })

            record_history(filename, entry, 10)

            saved = load_history(filename)[0]
            self.assertNotIn("audio_track_name", saved)
            self.assertNotIn("subtitle_track_id", saved)
            self.assertNotIn("subtitle_track_name", saved)

    def test_repairs_live_and_movie_rows_saved_as_series(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "history.json"
            for stream_id, title in (("11", "Live"), ("22", "Movie"), ("33", "Episode")):
                entry = self._entry(f"Series:{stream_id}", "Series", title)
                entry["stream_id"] = stream_id
                record_history(filename, entry, 10)

            repaired = repair_misclassified_history(filename, {"11"}, {"22"})

            by_title = {item["title"]: item for item in repaired}
            self.assertEqual(by_title["Live"]["type"], "LIVE")
            self.assertEqual(by_title["Movie"]["type"], "Movies")
            self.assertEqual(by_title["Episode"]["type"], "Series")

    @staticmethod
    def _entry(key, stream_type, title, position_ms=0):
        return {
            "key": key,
            "type": stream_type,
            "title": title,
            "position_ms": position_ms,
            "duration_ms": 90_000,
        }


if __name__ == "__main__":
    unittest.main()
