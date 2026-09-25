from pathlib import Path
import tempfile
import unittest

from iptv_player.config.advanced import (
    AdvancedPreferences,
    load_advanced_preferences,
    save_advanced_preferences,
)


class AdvancedPreferenceTests(unittest.TestCase):
    def test_round_trip_preserves_complete_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            expected = AdvancedPreferences(
                user_agent="Test client",
                connection_timeout=12,
                read_timeout=45,
                live_status_timeout=8,
                live_status_retries=4,
                stream_status_enabled=False,
                account_refresh_interval=120,
                account_auto_refresh_enabled=False,
                catalog_cache_enabled=False,
                catalog_cache_max_age_hours=48,
                detailed_logging_enabled=True,
                history_size=125,
                allow_all_category_exports=True,
                max_series_per_export=42,
                tmdb_read_access_token="test-token",
            )

            save_advanced_preferences(filename, expected)

            self.assertEqual(load_advanced_preferences(filename), expected)

    def test_invalid_values_fall_back_or_are_clamped_independently(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            filename.write_text(
                "[Timeouts]\n"
                "connection_timeout=invalid\n"
                "read_timeout=5000\n"
                "live_status_retries=-5\n"
                "[CatalogCache]\n"
                "enabled=invalid\n"
                "max_age_hours=0\n"
                "[History]\n"
                "max_items_per_type=5000\n"
                "[Export]\n"
                "allow_all_category_exports=invalid\n"
                "max_series_per_export=200000\n",
                encoding="utf-8",
            )

            preferences = load_advanced_preferences(filename)

            self.assertEqual(preferences.connection_timeout, 3)
            self.assertEqual(preferences.read_timeout, 999)
            self.assertEqual(preferences.live_status_retries, 0)
            self.assertTrue(preferences.catalog_cache_enabled)
            self.assertEqual(preferences.catalog_cache_max_age_hours, 1)
            self.assertEqual(preferences.history_size, 1000)
            self.assertFalse(preferences.allow_all_category_exports)
            self.assertEqual(preferences.max_series_per_export, 100000)
            self.assertEqual(preferences.tmdb_read_access_token, "")


if __name__ == "__main__":
    unittest.main()
