"""Native mouse state remains available during window-manager pointer grabs."""
import unittest
from unittest.mock import Mock, patch
from iptv_player.ui.native_mouse import NativeMouseButton


class NativeMouseTests(unittest.TestCase):
    def test_x11_reads_button_mask_and_closes_display_after_release(self):
        lib = Mock()
        lib.XOpenDisplay.return_value = 42
        lib.XScreenCount.return_value = 1
        lib.XRootWindow.return_value = 123
        held = [True]
        def query(*args):
            args[-1]._obj.value = (1 << 8) if held[0] else 0
            return 1
        lib.XQueryPointer.side_effect = query
        with patch('iptv_player.ui.native_mouse.sys.platform', 'linux'), patch(
                'iptv_player.ui.native_mouse.QApplication.platformName', return_value='xcb'), patch(
                'iptv_player.ui.native_mouse.ctypes.util.find_library', return_value='libX11.so.6'), patch(
                'iptv_player.ui.native_mouse.ctypes.CDLL', return_value=lib):
            reader = NativeMouseButton()
            self.assertTrue(reader.pressed())
            held[0] = False
            self.assertFalse(reader.pressed())
            lib.XOpenDisplay.assert_called_once()
            lib.XCloseDisplay.assert_called_once_with(42)
            reader.close()
            lib.XCloseDisplay.assert_called_once()

    def test_missing_native_library_falls_back_without_repeated_attempts(self):
        with patch('iptv_player.ui.native_mouse.sys.platform', 'linux'), patch(
                'iptv_player.ui.native_mouse.QApplication.platformName', return_value='xcb'), patch(
                'iptv_player.ui.native_mouse.ctypes.util.find_library', return_value=None) as find:
            reader = NativeMouseButton()
            self.assertIsNone(reader.pressed())
            self.assertIsNone(reader.pressed())
            find.assert_called_once()

    def test_macos_uses_session_left_button_state(self):
        lib = Mock()
        lib.CGEventSourceButtonState.return_value = True
        with patch('iptv_player.ui.native_mouse.sys.platform', 'darwin'), patch(
                'iptv_player.ui.native_mouse.ctypes.util.find_library', return_value='CoreGraphics'), patch(
                'iptv_player.ui.native_mouse.ctypes.CDLL', return_value=lib):
            reader = NativeMouseButton()
            self.assertTrue(reader.pressed())
            lib.CGEventSourceButtonState.assert_called_once_with(0, 0)

    def test_windows_leaves_existing_qt_and_native_resize_notifications_in_charge(self):
        with patch('iptv_player.ui.native_mouse.sys.platform', 'win32'), patch(
                'iptv_player.ui.native_mouse.ctypes.CDLL') as load:
            self.assertIsNone(NativeMouseButton().pressed())
            load.assert_not_called()
