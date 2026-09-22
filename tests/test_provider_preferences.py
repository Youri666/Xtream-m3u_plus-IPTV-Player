import json
from pathlib import Path
import tempfile
import unittest

from iptv_player.storage.provider_preferences import (
    load_provider_preferences,
    provider_preferences_file,
    save_provider_preferences,
)


class ProviderPreferencesTests(unittest.TestCase):
    def test_builds_account_specific_filename(self):
        filename = provider_preferences_file(
            Path("data") / "provider_preferences.json", "account123"
        )

        self.assertEqual(
            filename, Path("data") / "provider_preferences.account123.json"
        )

    def test_round_trip_preserves_category_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "provider_preferences.account123.json"

            save_provider_preferences(
                filename,
                {"LIVE": ["12"]},
                {"fallback": "z_a", "preferences": {"LIVE": {}}},
                {"LIVE": False, "Movies": True, "Series": True},
                ["History", "Movies", "LIVE", "Series", "Info", "Settings"],
                "Movies",
                "Series",
            )

            self.assertEqual(
                load_provider_preferences(filename),
                {
                    "hidden_categories": {"LIVE": ["12"]},
                    "category_sorting": {
                        "fallback": "z_a",
                        "preferences": {"LIVE": {}},
                    },
                    "content_enabled": {
                        "LIVE": False, "Movies": True, "Series": True,
                    },
                    "tab_order": [
                        "History", "Movies", "LIVE", "Series", "Info", "Settings",
                    ],
                    "default_tab": "Movies",
                    "last_selected_tab": "Series",
                },
            )

            save_provider_preferences(
                filename,
                {"LIVE": ["34"]},
                {"fallback": "a_z", "preferences": {}},
                {"LIVE": True, "Movies": True, "Series": True},
            )
            updated = load_provider_preferences(filename)
            self.assertEqual(
                updated["tab_order"],
                ["History", "Movies", "LIVE", "Series", "Info", "Settings"],
            )
            self.assertEqual(updated["default_tab"], "Movies")
            self.assertEqual(updated["last_selected_tab"], "Series")

    def test_invalid_sections_use_safe_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "provider_preferences.account123.json"
            filename.write_text(
                json.dumps({
                    "hidden_categories": [],
                    "category_sorting": "invalid",
                }),
                encoding="utf-8",
            )

            self.assertEqual(
                load_provider_preferences(filename),
                {
                    "hidden_categories": {},
                    "category_sorting": {},
                    "content_enabled": {},
                    "tab_order": [],
                    "default_tab": "History",
                    "last_selected_tab": "History",
                },
            )


if __name__ == "__main__":
    unittest.main()
