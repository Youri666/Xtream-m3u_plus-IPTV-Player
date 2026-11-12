"""Playback track choices stay within the current player session."""
from pathlib import Path
import tempfile
import unittest

import test_live_timeshift as live_widgets


class PlaybackTrackMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        live_widgets.LiveTimeshiftTests.setUpClass()

    def window(self, directory):
        helper = live_widgets.LiveTimeshiftTests()
        window = helper.window(str(Path(directory) / "settings.ini"))
        self.addCleanup(helper.doCleanups)
        window.player.is_playing.return_value = True
        window.player.audio_set_track.return_value = 0
        window.player.video_set_spu.return_value = 0
        return window

    @staticmethod
    def episode(number, series="1", account="A", season="1"):
        return {
            "url": f"https://example.test/episode/{number}", "name": f"Episode {number}",
            "history": {"type": "Series", "account_id": account, "series_id": series,
                        "season": season, "key": f"Series:{number}"},
        }

    def test_next_episode_matches_label_and_keeps_subtitles_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(directory)
            first, second = self.episode(1), self.episode(2)
            window.play_url(first["url"], playlist=[first, second])
            window.player.audio_get_track_description.return_value = [(3, b"Track 1 - French")]
            window.player.video_get_spu_description.return_value = [(-1, b"Disable"), (5, b"French")]
            window._select_audio_track(3)
            window._set_selected_track("subtitles", -1)
            window.player.audio_set_track.reset_mock()
            window.player.video_set_spu.reset_mock()
            window.next()
            window.player.audio_get_track_description.return_value = []
            window.player.video_get_spu_description.return_value = []
            window._restore_selected_tracks()
            window.player.audio_set_track.assert_not_called()
            window.player.video_set_spu.assert_not_called()
            window.player.audio_get_track_description.return_value = [
                (3, b"Track 1 - English"), (7, b"Track 2 - French"),
            ]
            window.player.video_get_spu_description.return_value = [(-1, b"Disable"), (9, b"French")]
            window._restore_selected_tracks()
            window.player.audio_set_track.assert_called_once_with(7)
            window.player.video_set_spu.assert_called_once_with(-1)

    def test_reconnect_restores_track_on_same_input(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(directory)
            episode = self.episode(1)
            window.play_url(episode["url"], playlist=[episode])
            window.player.video_get_spu_description.return_value = [(-1, b"Disable"), (5, b"Track 1")]
            window._set_selected_track("subtitles", 5)
            window.player.video_set_spu.reset_mock()
            window._reconnect_vod(45000)
            window._restore_selected_tracks()
            window.player.video_set_spu.assert_called_once_with(5)

    def test_unrelated_series_discards_session_choices(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(directory)
            first, other = self.episode(1), self.episode(2, series="2")
            window.play_url(first["url"], playlist=[first, other])
            window.player.audio_get_track_description.return_value = [(3, b"French")]
            window._select_audio_track(3)
            window.player.audio_set_track.reset_mock()
            window.next()
            window._restore_selected_tracks()
            window.player.audio_set_track.assert_not_called()

    def test_different_season_discards_session_choices(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(directory)
            first, other = self.episode(1), self.episode(2, season="2")
            window.play_url(first["url"], playlist=[first, other])
            window.player.audio_get_track_description.return_value = [(3, b"French")]
            window._select_audio_track(3)
            window.player.audio_set_track.reset_mock()
            window.next()
            window._restore_selected_tracks()
            window.player.audio_set_track.assert_not_called()

    def test_live_reconnect_restores_tracks_but_channel_change_does_not(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(directory)
            window.player.audio_get_track_description.return_value = [(3, b"French")]
            window.player.video_get_spu_description.return_value = [(-1, b"Disable"), (5, b"French")]
            window._select_audio_track(3)
            window._set_selected_track("subtitles", 5)
            window.player.audio_set_track.reset_mock()
            window.player.video_set_spu.reset_mock()
            window.player.get_state.return_value = "State.Ended"
            window.player.is_playing.return_value = False
            controller = window._live_reconnect
            controller.ended(window._media_generation)
            controller.timer.stop()
            controller._reopen()
            window.player.get_state.return_value = "State.Playing"
            window.player.is_playing.return_value = True
            window._restore_selected_tracks()
            window.player.audio_set_track.assert_called_once_with(3)
            window.player.video_set_spu.assert_called_once_with(5)

            window.player.audio_set_track.reset_mock()
            window.player.video_set_spu.reset_mock()
            window.previous()
            window._restore_selected_tracks()
            window.player.audio_set_track.assert_not_called()
            window.player.video_set_spu.assert_not_called()
