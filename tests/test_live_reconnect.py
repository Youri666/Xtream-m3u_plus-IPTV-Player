"""Unexpected LIVE endings get one cancellable, bounded reconnect attempt."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import test_live_timeshift as live_widgets


class LiveReconnectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        live_widgets.LiveTimeshiftTests.setUpClass()

    def window(self, filename):
        helper = live_widgets.LiveTimeshiftTests()
        window = helper.window(filename)
        self.addCleanup(helper.doCleanups)
        window.next = Mock()
        return window

    def schedule(self, window):
        window.player.get_state.return_value = 'State.Ended'
        window.player.is_playing.return_value = False
        window._advance_after_media_end(window._media_generation)
        window._live_reconnect.timer.stop()
        return window._live_reconnect

    def reopen(self, window):
        window.player.get_state.return_value = 'State.Opening'
        window.player.is_playing.return_value = False
        with patch('iptv_player.ui.live_reconnect.time.monotonic', return_value=100):
            window._live_reconnect._reopen()

    def connect(self, window):
        window.player.get_state.return_value = 'State.Playing'
        window.player.is_playing.return_value = True
        with patch('iptv_player.ui.live_reconnect.time.monotonic', return_value=101):
            window._live_reconnect.poll(1000)

    def test_unexpected_end_reopens_same_channel_once_without_resume_or_next(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            playlist = window._playlist
            count = window.instance.media_new.call_count
            controller = self.schedule(window)
            self.assertEqual(controller.phase, 'waiting')
            self.assertIn('Reconnecting', window.time_label.text())
            controller.ended(window._media_generation)
            self.assertEqual(window.instance.media_new.call_count, count)
            window._resume_for_playlist_entry = Mock()
            self.reopen(window)
            self.assertEqual(window.instance.media_new.call_count, count + 1)
            self.assertIs(window._playlist, playlist)
            self.assertEqual(window._current_idx, 1)
            self.assertEqual(window._pending_resume_ms, 0)
            self.connect(window)
            self.assertEqual(window.time_label.text(), 'LIVE')
            self.assertFalse(controller.armed)
            window._resume_for_playlist_entry.assert_not_called()
            window.next.assert_not_called()

    def test_failed_start_times_out_and_play_explicitly_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            controller = self.schedule(window)
            self.reopen(window)
            with patch('iptv_player.ui.live_reconnect.time.monotonic', return_value=131), self.assertLogs(level='WARNING'):
                controller.poll(0)
            self.assertTrue(controller.failed)
            self.assertEqual(window.time_label.text(), 'Interrupted')
            self.assertEqual(window.track_osd.text(), 'Stream interrupted. Press Play to retry.')
            count = window.instance.media_new.call_count
            controller.poll(0)
            controller.ended(window._media_generation)
            self.assertEqual(window.instance.media_new.call_count, count)
            window.toggle_play_pause()
            self.assertEqual(window.instance.media_new.call_count, count + 1)
            self.assertFalse(controller.failed)
            self.assertEqual(controller.phase, 'opening')

    def test_early_repeat_ends_attempt_but_stable_playback_rearms_it(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            controller = self.schedule(window)
            self.reopen(window)
            self.connect(window)
            with self.assertLogs(level='WARNING'):
                self.schedule(window)
            self.assertTrue(controller.failed)
            window.toggle_play_pause()
            self.connect(window)
            for now, position in ((110, 10000), (120, 20000), (132, 32000)):
                with patch('iptv_player.ui.live_reconnect.time.monotonic', return_value=now):
                    controller.poll(position)
            self.assertTrue(controller.armed)
            self.schedule(window)
            self.assertEqual(controller.phase, 'waiting')

    def test_pause_close_and_channel_changes_cancel_scheduled_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            for action in ('pause', 'close', 'channel'):
                with self.subTest(action=action):
                    window = self.window(str(Path(directory)/(action+'.ini')))
                    controller = self.schedule(window)
                    if action == 'pause':
                        window._pause_playback()
                    elif action == 'close':
                        window.close()
                    else:
                        window.play_url('https://example.test/a', 'Channel A', index=0)
                    count = window.instance.media_new.call_count
                    controller._reopen()
                    self.assertEqual(window.instance.media_new.call_count, count)
                    self.assertIsNone(controller.phase)

    def test_deliberate_live_pause_and_stale_end_events_do_not_reconnect(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            window._pause_playback()
            window.player.get_state.return_value = 'State.Ended'
            window._advance_after_media_end(window._media_generation)
            self.assertIsNone(window._live_reconnect.phase)
            window._live_reconnect.resume()
            window._advance_after_media_end(window._media_generation - 1)
            self.assertIsNone(window._live_reconnect.phase)
            window.player.get_state.return_value = 'State.Playing'
            window._advance_after_media_end(window._media_generation)
            self.assertIsNone(window._live_reconnect.phase)

    def test_frozen_position_cannot_rearm_retry_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            controller = self.schedule(window)
            self.reopen(window)
            self.connect(window)
            for now in (110, 120, 140, 180):
                with patch('iptv_player.ui.live_reconnect.time.monotonic', return_value=now):
                    controller.poll(1000)
            self.assertFalse(controller.armed)
