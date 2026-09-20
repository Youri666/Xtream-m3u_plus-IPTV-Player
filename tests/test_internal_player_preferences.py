from pathlib import Path
import tempfile
import unittest

from iptv_player.config.internal_player import (
    InternalPlayerPreferences,
    load_internal_player_preferences,
    save_internal_player_preferences,
)


class InternalPlayerPreferenceTests(unittest.TestCase):
    def test_round_trip_preserves_controls_and_existing_volume(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            filename.write_text("[InternalPlayer]\nvolume=37\n", encoding="utf-8")
            expected = InternalPlayerPreferences(
                seek_step_seconds=15,
                volume_step_percent=3,
                speed_step=0.2,
                audio_language="eng",
                subtitle_language="disabled",
                resume_behavior="resume",
            )

            save_internal_player_preferences(filename, expected)

            self.assertEqual(load_internal_player_preferences(filename), expected)
            self.assertIn("volume = 37", filename.read_text())

    def test_invalid_controls_are_validated_independently(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            filename.write_text(
                "[InternalPlayer]\n"
                "seek_step_seconds=999\n"
                "volume_step_percent=invalid\n"
                "speed_step=0.001\n"
                "audio_language=unsupported\n"
                "subtitle_language=fra\n"
                "resume_behavior=invalid\n",
                encoding="utf-8",
            )

            preferences = load_internal_player_preferences(filename)

            self.assertEqual(preferences.seek_step_seconds, 300)
            self.assertEqual(preferences.volume_step_percent, 2)
            self.assertEqual(preferences.speed_step, 0.05)
            self.assertEqual(preferences.audio_language, "")
            self.assertEqual(preferences.subtitle_language, "fra")
            self.assertEqual(preferences.resume_behavior, "ask")


if __name__ == "__main__":
    unittest.main()
