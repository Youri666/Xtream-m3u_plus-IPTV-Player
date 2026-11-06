"""The programme panel follows playback and ignores late asynchronous replies."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QApplication
from iptv_player.ui.player import EmbeddedPlayerWindow


class ProgrammePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def window(self, settings):
        player = Mock()
        player.is_playing.return_value = False
        player.get_time.return_value = 1000
        player.get_length.return_value = 100000
        vlc = SimpleNamespace(Instance=Mock(return_value=SimpleNamespace(media_player_new=lambda: player, media_new=Mock())),
                              EventType=SimpleNamespace(MediaPlayerEndReached=object()))
        with patch.dict('sys.modules', {'vlc': vlc}):
            window = EmbeddedPlayerWindow(settings_path=settings, progress_callback=Mock())
        window._aspect_controller.timer.stop()
        window._poll_timer.stop()
        window._current_history = dict(account_id='A', type='Movies', stream_id='1', title='Film')
        window.btn_programme.setEnabled(True)
        window.resize(1280, 800)
        window.show()
        self.app.processEvents()
        return window

    def test_button_requests_current_programme_and_late_replies_are_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            window.btn_programme.click()
            request = window._progress_callback.call_args.args[0]
            self.assertEqual(request['event'], 'programme_request')
            self.assertEqual(request['history']['stream_id'], '1')
            window.receive_programme_information(dict(request_id='old', generation=request['generation'],
                                                     payload={'summary': 'Wrong film'}))
            self.assertNotIn('Wrong film', window.programme_text.toPlainText())
            window.receive_programme_information(dict(request_id=request['request_id'], generation=request['generation'],
                                                     payload={'title': 'Film', 'summary': 'Correct summary'}))
            self.assertIn('Correct summary', window.programme_text.toPlainText())
            self.assertFalse(window.btn_info.isChecked())
            self.assertEqual(window.btn_programme.size(), QSize(34, 26))
            window._show_stream_information = Mock()
            window.btn_programme.click()
            self.assertFalse(window._programme_timer.isActive())
            window.close()

    def test_open_panel_follows_next_episode_without_showing_previous_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            window._bind_video_output = Mock()
            window._present_player = Mock()
            window.btn_programme.click()
            old = window._progress_callback.call_args.args[0]
            window.play_url('https://example.test/next', 'Episode two', playlist=[{
                'name': 'Episode two', 'url': 'https://example.test/next', 'history': {
                    'account_id': 'A', 'type': 'Series', 'series_id': '9', 'stream_id': '12'}}])
            request = window._progress_callback.call_args.args[0]
            self.assertEqual(request['event'], 'programme_request')
            self.assertEqual(request['history']['stream_id'], '12')
            self.assertNotEqual(request['request_id'], old['request_id'])
            window.receive_programme_information(dict(request_id=old['request_id'], generation=old['generation'],
                                                     payload={'summary': 'Old episode'}))
            self.assertNotIn('Old episode', window.programme_text.toPlainText())
            self.assertTrue(window.btn_programme.isChecked())
            window.close()

    def test_missing_metadata_and_disconnected_live_player_do_not_recurse(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            window._current_history = {'type': 'LIVE'}
            window._progress_callback = None
            window.btn_programme.click()
            self.assertIn('unavailable', window.programme_text.toPlainText())
            window.close()

    def test_small_video_panel_remains_inside_available_video_area(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            window._toggle_programme_information(True)
            window._toggle_window_aspect_lock(False)
            window.resize(1100, 600)
            self.app.processEvents()
            window._reposition_stream_info_panel()
            self.assertLessEqual(window.stream_info_panel.width(), window.video_frame.width())
            self.assertLessEqual(window.stream_info_panel.height(), window.video_frame.height())
            window.close()

    def test_info_and_programme_share_panel_in_fullscreen_without_mixing_content(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            window._programme_payload = {'title': 'Film', 'summary': 'Synopsis'}
            window._toggle_programme_information(True)
            window.toggle_fullscreen()
            self.app.processEvents()
            self.assertTrue(window.stream_info_panel.isVisible())
            self.assertIn('Synopsis', window.programme_text.toPlainText())
            with patch('iptv_player.ui.player.collect_stream_information', return_value=[]):
                window._show_stream_information()
            self.assertTrue(window.btn_info.isChecked())
            self.assertFalse(window.btn_programme.isChecked())
            self.assertFalse(window.programme_text.isVisible())
            self.assertFalse(window._programme_timer.isActive())
            window.toggle_fullscreen()
            window.close()

    def test_programme_panel_grows_and_shrinks_with_content_without_fixed_minimum(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            window._programme_payload = {'title': 'Film', 'summary': 'Short synopsis.'}
            window._toggle_programme_information(True)
            for _ in range(3):
                self.app.processEvents()
            short = window.stream_info_panel.size()
            self.assertLess(short.height(), 340)
            window._programme_payload = {'title': 'Film', 'summary': 'Long synopsis. ' * 500}
            window._refresh_programme_information()
            for _ in range(3):
                self.app.processEvents()
            self.assertGreater(window.stream_info_panel.height(), short.height())
            self.assertLessEqual(window.stream_info_panel.height(), window.video_frame.height() - 32)
            window._programme_payload = {'title': 'Film', 'summary': 'Short synopsis.'}
            window._refresh_programme_information()
            for _ in range(3):
                self.app.processEvents()
            self.assertEqual(window.stream_info_panel.size(), short)
            window.close()

    def test_technical_panel_grows_to_visible_rows_and_shrinks_on_collapse(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            with patch('iptv_player.ui.player.collect_stream_information', return_value=[
                    ('Video', [('Resolution', '1920 x 1080'), ('Frame rate', '25 fps')])]):
                window._show_stream_information()
            for _ in range(3):
                self.app.processEvents()
            small = window.stream_info_panel.size()
            self.assertLess(small.height(), 340)
            with patch('iptv_player.ui.player.collect_stream_information', return_value=[
                    ('Video', [('Property '+str(i), 'Value '+str(i)) for i in range(20)])]):
                window._show_stream_information()
            for _ in range(3):
                self.app.processEvents()
            expanded = window.stream_info_panel.height()
            self.assertGreater(expanded, small.height())
            window.stream_info_tree.topLevelItem(0).setExpanded(False)
            for _ in range(3):
                self.app.processEvents()
            self.assertLess(window.stream_info_panel.height(), expanded)
            window.close()

    def test_live_panel_left_open_advances_and_renews_only_at_programme_end(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.window(str(Path(directory)/'settings.ini'))
            window._current_history = {'account_id': 'A', 'type': 'LIVE', 'stream_id': '10'}
            window._programme_payload = {'kind': 'LIVE', 'entries': [
                {'start': 50, 'end': 100, 'title': 'First', 'summary': 'One'},
                {'start': 100, 'end': 200, 'title': 'Second', 'summary': 'Two'}]}
            window._programme_epg_refresh.received(window._programme_payload, 90)
            with patch('iptv_player.programme_info.time.time', return_value=90):
                window._toggle_programme_information(True)
                self.assertIn('First', window.programme_text.toPlainText())
                window._progress_callback.assert_not_called()
            with patch('iptv_player.programme_info.time.time', return_value=100):
                window._refresh_programme_information()
                self.assertIn('Second', window.programme_text.toPlainText())
                window._progress_callback.assert_called_once()
                window._refresh_programme_information()
                window._progress_callback.assert_called_once()
            window.close()
