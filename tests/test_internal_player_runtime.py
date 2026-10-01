"""Verify Linux X11 embedding without changing other platforms or parent state."""

import unittest
from iptv_player.internal_player_runtime import internal_player_environment


class InternalPlayerRuntimeTests(unittest.TestCase):
    def test_wayland_session_uses_xwayland_for_isolated_player(self):
        original = {'DISPLAY': ':0', 'WAYLAND_DISPLAY': 'wayland-0',
                    'QT_QPA_PLATFORM': 'wayland', 'LD_LIBRARY_PATH': '/bundled'}
        result = internal_player_environment(original, platform='linux')
        self.assertEqual(result['QT_QPA_PLATFORM'], 'xcb')
        self.assertEqual(result['LD_LIBRARY_PATH'], '/bundled')
        self.assertEqual(original['QT_QPA_PLATFORM'], 'wayland')

    def test_no_x_display_does_not_force_an_unavailable_backend(self):
        original = {'WAYLAND_DISPLAY': 'wayland-0'}
        self.assertEqual(internal_player_environment(original, platform='linux'), original)

    def test_other_platforms_keep_their_environment(self):
        original = {'DISPLAY': ':0', 'QT_QPA_PLATFORM': 'offscreen'}
        for platform in ('win32', 'darwin'):
            self.assertEqual(internal_player_environment(original, platform=platform), original)
