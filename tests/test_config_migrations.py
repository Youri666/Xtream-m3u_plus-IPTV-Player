import configparser
from pathlib import Path
import tempfile
import unittest

from iptv_player.config.migrations import (
    migrate_legacy_player_volume,
    migrate_user_data_file,
)


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

            migrate_user_data_file(str(file_path), URL_FORMATS, 1)

            config = configparser.ConfigParser()
            config.read(file_path)
            self.assertEqual(
                config["Credentials"]["Example"],
                "manual|host|user|password|live-format|movie-format|series-format",
            )
            self.assertTrue(config.getboolean("Content", "LIVE"))
            self.assertFalse(config.getboolean("Content", "Movies"))
            self.assertFalse(config.getboolean("Content", "Series"))
            self.assertEqual(config.getint("Application", "config_schema_version"), 1)

    def test_preserves_newer_schema_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "userdata.ini"
            file_path.write_text(
                "[Application]\nconfig_schema_version=5\nlast_run_version=old\n",
                encoding="utf-8",
            )

            migrate_user_data_file(str(file_path), URL_FORMATS, 1)

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
