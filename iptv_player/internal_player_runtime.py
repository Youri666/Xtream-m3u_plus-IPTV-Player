"""Configure the isolated internal player for its native embedding API."""

import os
import sys


def internal_player_environment(environment=None, platform=None):
    """Use X11 for Linux video embedding while leaving the main GUI unchanged."""
    result = dict(os.environ if environment is None else environment)
    platform = platform or sys.platform
    # libVLC 3 embeds into an X11 window through set_xwindow, not a Wayland surface.
    if platform.startswith('linux') and result.get('DISPLAY'):
        result['QT_QPA_PLATFORM'] = 'xcb'
    return result
