"""A paused LIVE channel offers a simple return to live without guessing delay."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from PyQt5.QtCore import Qt, QEvent
import test_programme_panel as panels


class LiveTimeshiftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        panels.ProgrammePanelTests.setUpClass()
        cls.app = panels.ProgrammePanelTests.app

    def window(self, filename):
        window = panels.ProgrammePanelTests().window(filename)
        self.addCleanup(self.dispose, window)
        window._bind_video_output = lambda: None
        playlist = [{'name': 'Channel A', 'url': 'https://example.test/a',
                     'history': {'type': 'LIVE', 'stream_id': '1', 'account_id': 'A'}},
                    {'name': 'Channel B', 'url': 'https://example.test/b',
                     'history': {'type': 'LIVE', 'stream_id': '2', 'account_id': 'A'}}]
        window.play_url(playlist[1]['url'], 'Channel B', playlist=playlist, index=1)
        return window

    def dispose(self, window):
        window.close()
        window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

    def test_pause_and_resume_keep_delayed_indicator_until_explicit_return(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            self.assertEqual(window.time_label.text(), 'LIVE')
            window._pause_playback()
            self.assertTrue(window._live_delayed)
            self.assertIn('DELAYED', window.time_label.text())
            self.assertIn('Click to return to live', window.time_label.toolTip())
            self.assertTrue(window.time_label.textInteractionFlags() & Qt.LinksAccessibleByKeyboard)
            window._resume_playback()
            window._poll_state()
            self.assertIn('DELAYED', window.time_label.text())
            self.assertFalse(window.seek_slider.isEnabled())
            self.assertIsNone(window._pause_started_at)
            window.close()

    def test_click_reopens_same_channel_without_seek_and_keeps_playlist(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            window._pause_playback()
            playlist = window._playlist
            before = window.instance.media_new.call_count
            window.instance.media_new.return_value.add_option.reset_mock()
            window.time_label.linkActivated.emit('return-to-live')
            window.player.stop.assert_called_once()
            self.assertEqual(window.instance.media_new.call_count, before + 1)
            window.instance.media_new.assert_called_with('https://example.test/b')
            self.assertIs(window._playlist, playlist)
            self.assertEqual(window._current_idx, 1)
            self.assertEqual(window._current_history['stream_id'], '2')
            self.assertEqual(window._pending_resume_ms, 0)
            self.assertFalse(window._live_delayed)
            self.assertEqual(window.time_label.text(), 'LIVE')
            options = [call.args[0] for call in window.instance.media_new.return_value.add_option.call_args_list]
            self.assertFalse(any(option.startswith(':start-time=') for option in options))
            window.close()

    def test_new_channel_or_vod_clears_delayed_state_and_link(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            window._pause_playback()
            window.play_url('https://example.test/a', 'Channel A', index=0)
            self.assertFalse(window._live_delayed)
            self.assertEqual(window.time_label.text(), 'LIVE')
            window.play_url('https://example.test/movie', 'Film', playlist=[{
                'name': 'Film', 'url': 'https://example.test/movie',
                'history': {'type': 'Movies', 'stream_id': '3'}}])
            window._pause_playback()
            self.assertFalse(window._live_delayed)
            window._poll_state()
            self.assertIn('/', window.time_label.text())
            self.assertEqual(window.time_label.toolTip(), '')
            self.assertEqual(window.time_label.textInteractionFlags(), Qt.NoTextInteraction)
            before = window.instance.media_new.call_count
            window.time_label.linkActivated.emit('return-to-live')
            self.assertEqual(window.instance.media_new.call_count, before)
            window.close()

    def test_minimize_and_restore_share_the_live_pause_indicator(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            window.player.is_playing.return_value = True
            event = QEvent(QEvent.WindowStateChange)
            with patch.object(window, 'isMinimized', return_value=True):
                window.changeEvent(event)
            self.assertTrue(window._live_delayed)
            self.assertIn('DELAYED', window.time_label.text())
            with patch.object(window, 'isMinimized', return_value=False):
                window.changeEvent(event)
            self.assertTrue(window._live_delayed)
            window.close()

    def test_immediate_reopen_failure_keeps_return_link_for_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            window._pause_playback()
            window.instance.media_new.side_effect = ValueError('test failure')
            with self.assertLogs(level='WARNING'):
                window.time_label.linkActivated.emit('return-to-live')
            self.assertTrue(window._live_delayed)
            self.assertIn('DELAYED', window.time_label.text())
            self.assertIn('retry', window.track_osd.text())
            window.close()

    def test_delayed_link_reuses_theme_accent_without_underlining(self):
        from iptv_player.ui.theme import apply_application_theme
        from iptv_player.ui.player_theme import DARK_ACCENT_COLOR, LIGHT_ACCENT_COLOR
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            window._pause_playback()
            for theme, color in (('Light', LIGHT_ACCENT_COLOR), ('Dark', DARK_ACCENT_COLOR)):
                with self.subTest(theme=theme):
                    apply_application_theme(self.app, theme)
                    window.apply_theme()
                    markup = window.time_label.text()
                    self.assertIn('>DELAYED</a>', markup)
                    self.assertIn('text-decoration: none;', markup)
                    self.assertIn('font-weight: bold;', markup)
                    self.assertIn('color: '+color, markup)
                    self.assertIn(color, window.overlay.styleSheet())
                    self.assertTrue(window._live_delayed)
            window.time_label.linkActivated.emit('return-to-live')
            self.assertEqual(window.time_label.text(), 'LIVE')
            window.close()

    def test_live_rate_stays_one_without_overwriting_saved_vod_speed(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            window._playback_rate = 1.5
            window.player.get_rate.return_value = 1.0
            window.player.is_playing.return_value = True
            window._pending_playback_rate_attempts = 20
            window._apply_pending_playback_rate()
            window.player.set_rate.assert_called_with(1.0)
            self.assertEqual(window._playback_rate, 1.5)
            self.assertFalse(window.btn_fast.isEnabled())
            window._adjust_rate(0.25)
            self.assertEqual(window._playback_rate, 1.5)
            window._pause_playback()
            window._return_to_live()
            window._apply_pending_playback_rate()
            window.player.set_rate.assert_called_with(1.0)
            self.assertEqual(window.rate_label.text(), '1.00x')
            window.close()

    def test_resize_returns_only_previously_direct_live_to_direct(self):
        for delayed, playing in ((False, True), (True, True), (True, False)):
            with self.subTest(delayed=delayed, playing=playing), tempfile.TemporaryDirectory() as directory:
                window = self.window(str(Path(directory)/'settings.ini'))
                controller = window._aspect_controller
                window._live_delayed = delayed
                window.player.is_playing.return_value = playing
                before = window.instance.media_new.call_count
                with patch.object(window._vlc, 'State', SimpleNamespace(Paused='paused'), create=True):
                    controller._begin_interactive_resize()
                    window.player.get_state.return_value = 'paused'
                    controller._end_interactive_resize()
                self.assertEqual(window.instance.media_new.call_count,
                                 before + int(playing and not delayed))
                self.assertEqual(window._live_delayed, delayed)
                if playing and delayed:
                    window.player.play.assert_called()
                if not playing:
                    window.player.pause.assert_not_called()
                    window.player.play.assert_called_once()  # Initial channel opening only.
                self.assertFalse(controller.return_to_live_after_resize)
