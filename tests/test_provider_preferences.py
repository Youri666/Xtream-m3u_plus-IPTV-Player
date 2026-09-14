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
            )

            self.assertEqual(
                load_provider_preferences(filename),
                {
                    "hidden_categories": {"LIVE": ["12"]},
                    "category_sorting": {
                        "fallback": "z_a",
                        "preferences": {"LIVE": {}},
                    },
                },
            )

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
                {"hidden_categories": {}, "category_sorting": {}},
            )


if __name__ == "__main__":
    unittest.main()
