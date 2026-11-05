"""Window aspect constraints preserve references, chrome and independent modes."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import QSize, QRect, Qt
from PyQt5.QtWidgets import QApplication
from iptv_player.ui.player import EmbeddedPlayerWindow
from iptv_player.ui.window_aspect import aspect_size
from iptv_player.config.internal_player import (load_window_aspect_lock, save_window_aspect_lock,
    save_internal_player_preferences, InternalPlayerPreferences)


class WindowAspectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self, filename):
        player = Mock()
        player.is_playing.return_value = False
        vlc = SimpleNamespace(Instance=Mock(return_value=SimpleNamespace(media_player_new=lambda: player)),
                              EventType=SimpleNamespace(MediaPlayerEndReached=object()))
        with patch.dict('sys.modules', {'vlc': vlc}):
            window = EmbeddedPlayerWindow(settings_path=filename)
        window.screen = lambda: SimpleNamespace(availableGeometry=lambda: QRect(0, 0, 2400, 1400))
        window._aspect_controller.timer.stop()
        window._poll_timer.stop()
        window.show()
        self.app.processEvents()
        return window

    def settle(self):
        for _ in range(3):
            self.app.processEvents()

    def assert_ratio(self, window, ratio):
        chrome = window._aspect_controller.chrome()
        self.assertLessEqual(abs((window.width() - chrome.width()) / ratio - (window.height() - chrome.height())), 1.5)

    def test_geometry_preserves_longest_dimension_across_formats(self):
        chrome = QSize(0, 100)
        minimum, maximum = QSize(100, 100), QSize(2000, 1500)
        wide = aspect_size(16/9, 960, chrome, minimum, maximum)
        square = aspect_size(4/3, 960, chrome, minimum, maximum)
        restored = aspect_size(16/9, 960, chrome, minimum, maximum)
        self.assertEqual(wide, QSize(960, 640))
        self.assertEqual(square, QSize(960, 820))
        self.assertEqual(restored, wide)
        fitted = aspect_size(4/3, 960, chrome, minimum, QSize(800, 700))
        self.assertLessEqual(fitted.width(), 800)
        self.assertLessEqual(fitted.height(), 700)

    def test_lock_defaults_and_survives_saving_advanced_player_options(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory)/'userdata.ini'
            self.assertTrue(load_window_aspect_lock(filename))
            save_window_aspect_lock(filename, False)
            save_internal_player_preferences(filename, InternalPlayerPreferences())
            self.assertFalse(load_window_aspect_lock(filename))

    def test_side_and_corner_resizes_keep_ratio_then_unlock_allows_free_size(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.make_window(str(Path(directory)/'userdata.ini'))
            controller = window._aspect_controller
            controller.ratio_provider = lambda: 16/9
            controller.refresh_ratio()
            self.settle()
            self.assert_ratio(window, 16/9)
            for width, height in ((1200, window.height()), (window.width(), 850), (1150, 800)):
                window.resize(width, height)
                self.settle()
                self.assert_ratio(window, 16/9)
            window.btn_aspect_lock.click()
            window.resize(1150, 850)
            self.settle()
            self.assertEqual(window.size(), QSize(1150, 850))
            window.close()

    def test_ratio_changes_restore_size_and_sidebar_does_not_resize_window(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.make_window(str(Path(directory)/'userdata.ini'))
            controller = window._aspect_controller
            ratio = [16/9]
            controller.ratio_provider = lambda: ratio[0]
            controller.refresh_ratio()
            self.settle()
            initial = window.size()
            ratio[0] = 4/3
            controller.refresh_ratio()
            self.settle()
            self.assert_ratio(window, 4/3)
            ratio[0] = 16/9
            controller.refresh_ratio()
            self.settle()
            self.assertEqual(window.size(), initial)
            window.toggle_sidebar()
            self.settle()
            self.assertEqual(window.size(), initial)
            window.resize(initial.width() + 30, initial.height() + 20)
            self.settle()
            resized = window.size()
            window.toggle_sidebar()
            self.settle()
            self.assertEqual(window.size(), resized)
            window.close()

    def test_fullscreen_preserves_reference_and_restores_windowed_ratio(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.make_window(str(Path(directory)/'userdata.ini'))
            controller = window._aspect_controller
            controller.ratio_provider = lambda: 16/9
            controller.refresh_ratio()
            self.settle()
            reference = controller.reference
            window.toggle_fullscreen()
            self.settle()
            self.assertFalse(window.btn_aspect_lock.isEnabled())
            self.assertEqual(controller.reference, reference)
            window.toggle_fullscreen()
            self.settle()
            self.assertTrue(window.btn_aspect_lock.isEnabled())
            self.assert_ratio(window, 16/9)
            window.close()

    def test_drag_defers_ratio_correction_and_resumes_only_previous_playback(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.make_window(str(Path(directory)/'userdata.ini'))
            controller = window._aspect_controller
            controller.ratio_provider = lambda: 16/9
            controller.refresh_ratio()
            self.settle()
            window._current_url = 'test://video'
            window._vlc.State = SimpleNamespace(Paused=4)
            window.player.get_state.return_value = 4
            window.player.is_playing.return_value = True
            window._pause_playback = Mock()
            window._resume_playback = Mock()
            controller.native_size_move(True)
            window.resize(1200, 850)
            self.settle()
            self.assertEqual(window.size(), QSize(1200, 850))
            window._pause_playback.assert_called_once()
            window._resume_playback.assert_not_called()
            window.resize(1250, 880)
            self.settle()
            self.assertEqual(window.size(), QSize(1250, 880))
            window._pause_playback.assert_called_once()
            controller.native_size_move(False)
            self.settle()
            self.assert_ratio(window, 16/9)
            window._resume_playback.assert_called_once()
            window._pause_playback.reset_mock()
            window._resume_playback.reset_mock()
            window.player.is_playing.return_value = False
            controller.native_size_move(True)
            window.resize(1200, 850)
            self.settle()
            controller.native_size_move(False)
            self.settle()
            window._pause_playback.assert_not_called()
            window._resume_playback.assert_not_called()
            window.close()

    def test_qt_mouse_release_path_without_windows_native_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.make_window(str(Path(directory)/'userdata.ini'))
            controller = window._aspect_controller
            controller.ratio_provider = lambda: 16/9
            controller.refresh_ratio()
            self.settle()
            with patch('iptv_player.ui.window_aspect.QApplication.mouseButtons', return_value=Qt.LeftButton):
                window.resize(1200, 850)
                self.settle()
                controller._check_release()
                self.assertTrue(controller.interactive_resize)
                self.assertEqual(window.size(), QSize(1200, 850))
            with patch('iptv_player.ui.window_aspect.QApplication.mouseButtons', return_value=Qt.NoButton):
                controller._check_release()
            self.settle()
            self.assertFalse(controller.interactive_resize)
            self.assert_ratio(window, 16/9)
            window.close()

    def test_auto_movie_series_live_transitions_restore_window_ratio(self):
        with tempfile.TemporaryDirectory() as directory:
            window = self.make_window(str(Path(directory)/'userdata.ini'))
            controller = window._aspect_controller
            ratio = [16/9]
            controller.ratio_provider = lambda: ratio[0]
            controller.refresh_ratio()
            self.settle()
            initial = window.size()
            for next_ratio in (4/3, 16/9):
                controller.reset_media()
                ratio[0] = None
                controller.refresh_ratio()
                ratio[0] = next_ratio
                controller.refresh_ratio()
                self.settle()
                self.assert_ratio(window, next_ratio)
            self.assertEqual(window.size(), initial)
            window.close()
