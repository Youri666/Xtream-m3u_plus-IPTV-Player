"""Video format selection is persistent and independent of window geometry."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication
from iptv_player.config.internal_player import (VIDEO_ASPECT_RATIOS, load_video_format, save_video_format,
    save_internal_player_preferences, InternalPlayerPreferences)
from iptv_player.ui.player import EmbeddedPlayerWindow


class VideoFormatTests(unittest.TestCase):
    def test_preferences_default_validation_and_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / 'userdata.ini'
            self.assertEqual(load_video_format(filename), 'Auto')
            save_video_format(filename, '2.39:1')
            save_internal_player_preferences(filename, InternalPlayerPreferences())
            self.assertEqual(load_video_format(filename), '2.39:1')
            filename.write_text('[InternalPlayer]\nvideo_format=unsupported\n')
            self.assertEqual(load_video_format(filename), 'Auto')
            with self.assertRaises(ValueError):
                save_video_format(filename, 'unsupported')

    def test_api_receives_exact_ratios_and_auto_removes_override(self):
        window = SimpleNamespace(player=Mock())
        for label, expected in VIDEO_ASPECT_RATIOS.items():
            window._video_format = label
            self.assertTrue(EmbeddedPlayerWindow._apply_video_format(window))
            window.player.video_set_aspect_ratio.assert_called_with(expected)
        self.assertEqual(VIDEO_ASPECT_RATIOS['2.21:1'], '221:100')
        self.assertEqual(VIDEO_ASPECT_RATIOS['Auto'], '')

    def test_real_toolbar_counter_opens_existing_playlist_and_menu_persists(self):
        app = QApplication.instance() or QApplication([])
        player = Mock()
        player.is_playing.return_value = False
        vlc = SimpleNamespace(Instance=Mock(return_value=SimpleNamespace(media_player_new=lambda: player)),
                              EventType=SimpleNamespace(MediaPlayerEndReached=object()))
        with tempfile.TemporaryDirectory() as directory, patch.dict('sys.modules', {'vlc': vlc}):
            filename = str(Path(directory) / 'userdata.ini')
            window = EmbeddedPlayerWindow(settings_path=filename)
            window._playlist = [{'name': 'Episode One', 'url': 'https://example.test/1'},
                                {'name': 'Episode Two', 'url': 'https://example.test/2'}]
            window._current_idx = 0
            window._update_pl_pos()
            window.pl_pos.click()
            self.assertTrue(window._sidebar_visible)
            self.assertEqual(window.playlist_list.count(), 2)
            window.pl_pos.click()
            self.assertFalse(window._sidebar_visible)
            window.format_actions['4:3'].trigger()
            player.video_set_aspect_ratio.assert_called_with('4:3')
            self.assertEqual(load_video_format(filename), '4:3')
            window.format_actions['Auto'].trigger()
            player.video_set_aspect_ratio.assert_called_with('')
            self.assertEqual(load_video_format(filename), 'Auto')
            for button in (window.btn_prev, window.btn_rewind, window.btn_play,
                           window.btn_ffwd, window.btn_next, window.btn_slow,
                           window.btn_fast, window.btn_info, window.btn_mute, window.btn_fs):
                self.assertEqual(button.size(), window.btn_play.size())
            self.assertEqual(window.btn_play.height(), 26)
            self.assertEqual(window.btn_format.height(), 26)
            window.close()
            window.deleteLater()
