import configparser
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iptv_player.config.ini import read_config_file, write_config_file


class IniFileTests(unittest.TestCase):
    def test_generic_rewrite_preserves_credential_name_case(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            filename.write_text(
                "[Credentials]\n"
                "Maestro Test = manual|host|user|password|live|movie|series\n\n"
                "[Startup credentials]\n"
                "startup_credentials = Maestro Test\n",
                encoding="utf-8",
            )

            config = configparser.ConfigParser()
            config.read(filename)
            config["Window"] = {"active_tab": "LIVE"}
            write_config_file(filename, config)

            preserved = configparser.ConfigParser()
            preserved.optionxform = str
            preserved.read(filename)
            self.assertIn("Maestro Test", preserved["Credentials"])
            self.assertNotIn("maestro test", preserved["Credentials"])

    def test_legacy_key_recovers_case_from_startup_account(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            filename.write_text(
                "[Credentials]\n"
                "maestro = manual|host|user|password|live|movie|series\n\n"
                "[Startup credentials]\n"
                "startup_credentials = Maestro\n",
                encoding="utf-8",
            )

            config = configparser.ConfigParser()
            config.read(filename)
            write_config_file(filename, config)

            preserved = configparser.ConfigParser()
            preserved.optionxform = str
            preserved.read(filename)
            self.assertIn("Maestro", preserved["Credentials"])

    def test_round_trip_preserves_sections_and_values(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            config = configparser.ConfigParser()
            config["Theme"] = {"mode": "Dark"}

            write_config_file(filename, config)

            loaded = read_config_file(filename)
            self.assertEqual(loaded.get("Theme", "mode"), "Dark")

    def test_failed_replacement_keeps_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            filename.write_text("[Theme]\nmode = Light\n", encoding="utf-8")
            config = configparser.ConfigParser()
            config["Theme"] = {"mode": "Dark"}

            with patch("iptv_player.config.ini.os.replace", side_effect=OSError):
                with self.assertRaises(OSError):
                    write_config_file(filename, config)

            self.assertEqual(
                filename.read_text(encoding="utf-8"),
                "[Theme]\nmode = Light\n",
            )
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()

