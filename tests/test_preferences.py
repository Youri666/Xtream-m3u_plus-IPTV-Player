from pathlib import Path
import tempfile
import unittest

from iptv_player.config.preferences import (
    INTERNAL_VLC_COMMAND,
    PlayerPreference,
    load_auto_update_preference,
    load_content_preferences,
    load_player_preference,
    load_sorting_preference,
    load_stream_status_preference,
    load_theme_preference,
    save_auto_update_preference,
    save_content_preferences,
    save_player_preference,
    save_sorting_preference,
    save_theme_preference,
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

    def test_theme_preference_validates_saved_and_manually_edited_values(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            save_theme_preference(filename, "Dark")
            self.assertEqual(load_theme_preference(filename), "Dark")

            save_theme_preference(filename, "Unsupported")
            self.assertEqual(load_theme_preference(filename), "System")

    def test_content_preferences_preserve_independent_switches(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            save_content_preferences(
                filename, {"LIVE": True, "Movies": False, "Series": True}
            )

            self.assertEqual(
                load_content_preferences(filename),
                {"LIVE": True, "Movies": False, "Series": True},
            )

    def test_legacy_vod_switch_applies_to_movies_and_series(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            filename.write_text("[VOD]\nenabled=False\n", encoding="utf-8")

            self.assertEqual(
                load_content_preferences(filename),
                {"LIVE": True, "Movies": False, "Series": False},
            )

    def test_sorting_defaults_to_disabled_and_removes_legacy_section(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            self.assertEqual(load_sorting_preference(filename), "Sorting disabled")
            filename.write_text(
                "[Category sorting]\nfallback=z_a\n", encoding="utf-8"
            )

            save_sorting_preference(filename, "Remember per list")

            self.assertEqual(
                load_sorting_preference(filename), "Remember per list"
            )
            self.assertNotIn("Category sorting", filename.read_text(encoding="utf-8"))

    def test_legacy_remember_sorting_label_is_upgraded_when_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            filename.write_text(
                "[Sorting order]\nOrder=Remember per category\n",
                encoding="utf-8",
            )

            self.assertEqual(load_sorting_preference(filename), "Remember per list")

    def test_stream_status_defaults_to_enabled(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            self.assertTrue(load_stream_status_preference(filename))


if __name__ == "__main__":
    unittest.main()
