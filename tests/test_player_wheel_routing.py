"""Route wheel input to foreground controls rather than overlapping video."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PyQt5.QtCore import QEvent, QPoint, QObject
from PyQt5.QtGui import QWindow
from PyQt5.QtWidgets import QApplication, QWidget
from iptv_player.ui.player import EmbeddedPlayerWindow


class PlayerWheelRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def dispatch(self, delta, *, audio=False, rate=False, video=True, overlay=True, panel=False):
        window = SimpleNamespace(sidebar=object(), overlay=object(), stream_info_panel=Mock(),
                                 audio_controls=object(), rate_controls=object(),
                                 video_frame=QWidget(), _last_wheel_event_id=None,
                                 _obj_is_in_player=lambda obj: True,
                                 _wake_controls=Mock(), _volume_step=2,
                                 _speed_step=0.25, _seek_step_ms=10000,
                                 _step_volume=Mock(), _adjust_rate=Mock(),
                                 preview_wheel_seek=Mock(), seek_slider=Mock())
        window.stream_info_panel.isAncestorOf.return_value = False
        window.seek_slider.isEnabled.return_value = True
        hits = {window.sidebar: False, window.overlay: overlay, window.stream_info_panel: panel,
                window.audio_controls: audio, window.rate_controls: rate,
                window.video_frame: video}
        window._event_is_over_widget = lambda event, widget: hits[widget]
        event = SimpleNamespace(type=lambda: QEvent.Wheel,
                                angleDelta=lambda: QPoint(0, delta))
        with patch("iptv_player.ui.player.QTimer.singleShot"):
            self.assertEqual(EmbeddedPlayerWindow.eventFilter(window, window.video_frame, event), not panel)
        return window

    def test_volume_controls_win_over_video_in_fullscreen(self):
        for delta, expected in ((120, 2), (-120, -2)):
            window = self.dispatch(delta, audio=True)
            window._step_volume.assert_called_once_with(expected)
            window.preview_wheel_seek.assert_not_called()
            window._adjust_rate.assert_not_called()

    def test_volume_controls_work_without_video_overlap(self):
        window = self.dispatch(120, audio=True, video=False)
        window._step_volume.assert_called_once_with(2)
        window.preview_wheel_seek.assert_not_called()

    def test_speed_controls_still_win_over_video(self):
        window = self.dispatch(-120, rate=True)
        window._adjust_rate.assert_called_once_with(-0.25)
        window.preview_wheel_seek.assert_not_called()
        window._step_volume.assert_not_called()

    def test_video_still_seeks_in_both_directions(self):
        for delta, expected in ((120, 10000), (-120, -10000)):
            window = self.dispatch(delta, overlay=False)
            window.preview_wheel_seek.assert_called_once_with(expected)
            window._step_volume.assert_not_called()

    def test_zero_delta_does_not_change_volume(self):
        window = self.dispatch(0, audio=True)
        window._step_volume.assert_not_called()
        window.preview_wheel_seek.assert_not_called()

    def test_description_panel_wheel_never_seeks_or_changes_volume(self):
        window = self.dispatch(120, panel=True)
        window._step_volume.assert_not_called()
        window.preview_wheel_seek.assert_not_called()
        window._adjust_rate.assert_not_called()

    def test_global_filter_ignores_native_windows_and_non_widget_objects(self):
        window = SimpleNamespace(stream_info_panel=Mock(), _obj_is_in_player=Mock(),
                                 _wake_controls=Mock())
        for receiver in (QWindow(), QObject()):
            with self.subTest(receiver=type(receiver).__name__):
                result = EmbeddedPlayerWindow.eventFilter(window, receiver, QEvent(QEvent.Wheel))
                self.assertFalse(result)
        window.stream_info_panel.isAncestorOf.assert_not_called()
        window._obj_is_in_player.assert_not_called()
        window._wake_controls.assert_not_called()
