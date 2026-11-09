"""VOD polling detects interrupted inputs and preserves the most recent position."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import test_live_timeshift as live_widgets


class VodInterruptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        live_widgets.LiveTimeshiftTests.setUpClass()

    def window(self, directory):
        helper = live_widgets.LiveTimeshiftTests()
        window = helper.window(str(Path(directory) / 'settings.ini'))
        self.addCleanup(helper.doCleanups)
        window.play_url('https://example.test/episode', 'Episode', playlist=[{
            'url': 'https://example.test/episode', 'name': 'Episode',
            'history': {'type': 'Series', 'stream_id': '3', 'duration_ms': 120000}}])
        window.next = Mock()
        window._auto_play_next = True
        window._auto_advance_seconds = 0
        window.player.is_playing.return_value = True
        window.player.get_state.return_value = 'State.Playing'
        window.player.get_length.return_value = 120000
        return window

    def test_poll_reopens_after_error_at_last_valid_position_and_rearms_after_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(directory)
            window.player.get_time.return_value = 45000
            window._poll_state()
            before = window.instance.media_new.call_count
            window.player.get_time.return_value = 0
            window.player.get_state.return_value = 'State.Error'
            window._poll_state()
            self.assertEqual(window.instance.media_new.call_count, before + 1)
            self.assertEqual(window._pause_recovery_target_ms, 45000)
            self.assertEqual(window.track_osd.text(), 'Reconnecting…')
            window.next.assert_not_called()
            window.player.get_state.return_value = 'State.Playing'
            window.player.get_time.return_value = 46000
            window._poll_state()
            self.assertFalse(window._recovering_after_pause)
            self.assertTrue(window._vod_retry_used)
            window.player.get_time.return_value = 76000
            window._poll_state()
            self.assertFalse(window._vod_retry_used)

    def test_poll_natural_end_advances_once_without_reopening(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(directory)
            window.player.get_time.return_value = 119000
            window._poll_state()
            before = window.instance.media_new.call_count
            window.player.get_state.return_value = 'State.Ended'
            window.player.is_playing.return_value = False
            window.player.get_time.return_value = -1
            window._poll_state()
            window._poll_state()
            window.next.assert_called_once()
            self.assertEqual(window.instance.media_new.call_count, before)

    def test_channel_change_clears_old_vod_failure_and_position(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(directory)
            window._vod_position_ms = 45000
            window._pause_recovery_target_ms = 45000
            window._fail_pause_recovery()
            window.play_url('https://example.test/new', 'New episode', playlist=[{
                'name': 'New episode', 'url': 'https://example.test/new',
                'history': {'type': 'Series', 'stream_id': '4'}}])
            self.assertFalse(window._pause_recovery_failed)
            self.assertFalse(window._vod_retry_used)
            self.assertEqual(window._vod_position_ms, 0)
