from pathlib import Path
import tempfile
import unittest

from iptv_player.config.preferences import (
    INTERNAL_VLC_COMMAND,
    PlayerPreference,
    load_auto_update_preference,
    load_player_preference,
    save_auto_update_preference,
    save_player_preference,
)


class ApplicationPreferenceTests(unittest.TestCase):
    def test_missing_player_preference_is_unconfigured(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"

            self.assertEqual(load_player_preference(filename), PlayerPreference())

    def test_external_player_is_remembered_automatically(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            save_player_preference(filename, r"C:\Players\player.exe")

            preference = load_player_preference(filename)

            self.assertEqual(preference.command, r"C:\Players\player.exe")
            self.assertEqual(
                preference.last_external_command, r"C:\Players\player.exe"
            )
            self.assertTrue(preference.configured)

    def test_internal_player_preserves_last_external_player(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            save_player_preference(
                filename, INTERNAL_VLC_COMMAND, r"C:\Players\player.exe"
            )

            preference = load_player_preference(filename)

            self.assertEqual(preference.command, INTERNAL_VLC_COMMAND)
            self.assertEqual(
                preference.last_external_command, r"C:\Players\player.exe"
            )

    def test_auto_update_preference_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            self.assertIsNone(load_auto_update_preference(filename))

            save_auto_update_preference(filename, False)
            self.assertFalse(load_auto_update_preference(filename))

            save_auto_update_preference(filename, True)
            self.assertTrue(load_auto_update_preference(filename))


if __name__ == "__main__":
    unittest.main()
