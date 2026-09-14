import configparser
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from iptv_player.config.accounts import load_accounts, load_startup_account
from iptv_player.config.migrations import (
    migrate_legacy_player_volume,
    migrate_user_data_file,
)
from iptv_player.storage import load_provider_preferences


URL_FORMATS = {
    "live": "live-format",
    "movie": "movie-format",
    "series": "series-format",
}


class ConfigurationMigrationTests(unittest.TestCase):
    def test_migrates_legacy_content_and_missing_url_formats(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "userdata.ini"
            file_path.write_text(
                "[Credentials]\nExample=manual|host|user|password\n"
                "[VOD]\nenabled=False\n",
                encoding="utf-8",
            )

            migrate_user_data_file(str(file_path), URL_FORMATS, 4)

            config = configparser.ConfigParser()
            config.read(file_path)
            self.assertEqual(
                load_accounts(str(file_path))["Example"],
                "manual|host|user|password|live-format|movie-format|series-format",
            )
            self.assertNotIn("Credentials", config)
            self.assertTrue(config.getboolean("Content", "LIVE"))
            self.assertFalse(config.getboolean("Content", "Movies"))
            self.assertFalse(config.getboolean("Content", "Series"))
            self.assertEqual(config.getint("Application", "config_schema_version"), 4)

    def test_migrates_account_names_and_startup_selection_to_stable_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "userdata.ini"
            file_path.write_text(
                "[Credentials]\n"
                "maestro test=manual|host|user|password|live|movie|series\n"
                "Second Provider=m3u_plus|url|live|movie|series\n\n"
                "[Startup credentials]\n"
                "startup_credentials=Maestro Test\n\n"
                "[Hidden categories]\n"
                "LIVE=[\"12\"]\n\n"
                "[Category sorting]\n"
                "fallback=z_a\n"
                "LIVE={\"category:12\":\"a_z\"}\n",
                encoding="utf-8",
            )

            migrate_user_data_file(str(file_path), URL_FORMATS, 4)
            first_result = file_path.read_text(encoding="utf-8")
            migrated = configparser.ConfigParser()
            migrated.read(file_path)
            startup_id = migrated["Startup credentials"]["startup_account_id"]
            preferences_file = (
                Path(directory) / f"provider_preferences.{startup_id}.json"
            )
            first_preferences = preferences_file.read_text(encoding="utf-8")

            migrate_user_data_file(str(file_path), URL_FORMATS, 4)

            self.assertEqual(
                list(load_accounts(str(file_path))),
                ["Maestro Test", "Second Provider"],
            )
            self.assertEqual(load_startup_account(str(file_path)), "Maestro Test")
            account_section = migrated[f"Account:{startup_id}"]
            self.assertNotIn("hidden_categories", account_section)
            self.assertNotIn("category_sorting", account_section)
            preferences = load_provider_preferences(preferences_file)
            self.assertEqual(
                preferences["hidden_categories"]["LIVE"], ["12"]
            )
            self.assertEqual(
                preferences["category_sorting"]["fallback"],
                "z_a",
            )
            self.assertEqual(first_result, file_path.read_text(encoding="utf-8"))
            self.assertEqual(
                first_preferences, preferences_file.read_text(encoding="utf-8")
            )

    def test_retries_provider_preference_migration_after_write_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "userdata.ini"
            file_path.write_text(
                "[Application]\nconfig_schema_version=3\n\n"
                "[Account:account123]\n"
                "name=Example\n"
                "credentials=manual|host|user|password|live|movie|series\n"
                'hidden_categories={"LIVE":["12"]}\n',
                encoding="utf-8",
            )

            with patch(
                "iptv_player.config.migrations.save_provider_preferences",
                side_effect=OSError("read-only destination"),
            ):
                migrate_user_data_file(str(file_path), URL_FORMATS, 4)

            config = configparser.ConfigParser()
            config.read(file_path)
            self.assertEqual(
                config.getint("Application", "config_schema_version"), 3
            )
            self.assertTrue(
                config.has_option("Account:account123", "hidden_categories")
            )

    def test_preserves_newer_schema_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "userdata.ini"
            file_path.write_text(
                "[Application]\nconfig_schema_version=5\nlast_run_version=old\n",
                encoding="utf-8",
            )

            migrate_user_data_file(str(file_path), URL_FORMATS, 4)

            config = configparser.ConfigParser()
            config.read(file_path)
            self.assertEqual(config.getint("Application", "config_schema_version"), 5)
            self.assertFalse(config.has_option("Application", "last_run_version"))

    def test_moves_legacy_volume_without_overwriting_current_value(self):
        with tempfile.TemporaryDirectory() as directory:
            data_directory = Path(directory)
            user_data_file = data_directory / "userdata.ini"
            legacy_file = data_directory / ".embedded_player_volume"
            user_data_file.write_text("[InternalPlayer]\nvolume=25\n", encoding="utf-8")
            legacy_file.write_text("80", encoding="utf-8")

            migrate_legacy_player_volume(str(user_data_file), str(data_directory))

            config = configparser.ConfigParser()
            config.read(user_data_file)
            self.assertEqual(config.getint("InternalPlayer", "volume"), 25)
            self.assertFalse(legacy_file.exists())


if __name__ == "__main__":
    unittest.main()
