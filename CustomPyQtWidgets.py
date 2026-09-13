"""Compatibility imports for media-related Qt widgets.

New code should import these widgets from ``iptv_player.ui.media_widgets``.
"""

from iptv_player.ui.media_widgets import (
    EmbeddedPlayerWindow,
    LiveInfoBox,
    MovieInfoBox,
    SeriesInfoBox,
)

__all__ = [
    "EmbeddedPlayerWindow",
    "LiveInfoBox",
    "MovieInfoBox",
    "SeriesInfoBox",
]
