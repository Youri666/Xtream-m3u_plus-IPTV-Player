"""Qt style sheets used by the embedded media player."""

DARK_BUTTON_STYLE = """
QPushButton {
    background: rgba(45, 45, 48, 130);
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 16px;
}
QPushButton:hover { background: rgba(91, 141, 239, 200); }
QPushButton:disabled { color: #888; background: rgba(45,45,48,80); }
"""

DARK_OVERLAY_STYLE = """
QWidget#playerOverlay {
    background: rgb(20, 20, 22);
}
QWidget#playerTopBar {
    background: rgb(20, 20, 22);
}
QLabel#titleLabel { color: white; font-size: 14px; font-weight: bold; }
QLabel#timeLabel  { color: #eee; font-size: 11px; }
QSlider#seekSlider::groove:horizontal { height: 6px; background: rgba(255,255,255,70); border-radius: 3px; }
QSlider#seekSlider::handle:horizontal { background: #7c3aed; width: 14px; height: 14px; margin: -4px 0; border-radius: 7px; }
QSlider#seekSlider::handle:horizontal:hover { background: #9b6dff; }
QSlider#seekSlider::sub-page:horizontal { background: #7c3aed; border-radius: 3px; }
QSlider::groove:horizontal { height: 4px; background: rgba(255,255,255,60); border-radius: 2px; }
QSlider::handle:horizontal { background: #7c3aed; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }
QSlider::sub-page:horizontal { background: #7c3aed; border-radius: 2px; }
"""

DARK_SIDEBAR_STYLE = """
QWidget#sidebarRoot { background: rgba(20, 20, 22, 240); }
QListWidget#playlistList {
    background: transparent;
    color: white;
    border: none;
    outline: 0;
    font-size: 13px;
}
QListWidget#playlistList::item { padding: 8px 10px; border-left: 3px solid transparent; }
QListWidget#playlistList::item:hover { background: rgba(91,141,239,40); }
QListWidget#playlistList::item:selected {
    background: rgba(91,141,239,80);
    border-left: 3px solid #7c3aed;
    color: white;
}
QLineEdit#sidebarSearch {
    background: rgba(255,255,255,15);
    color: white;
    border: 1px solid rgba(255,255,255,30);
    border-radius: 4px;
    padding: 6px 8px;
    font-size: 12px;
}
"""

LIGHT_BUTTON_STYLE = """
QPushButton {
    background: rgba(245, 245, 245, 220);
    color: #202020;
    border: 1px solid rgba(80, 80, 80, 90);
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 14px;
}
QPushButton:hover { background: rgba(91, 141, 239, 210); color: white; }
QPushButton:disabled { color: #999; background: rgba(225,225,225,180); }
"""

LIGHT_OVERLAY_STYLE = """
QWidget#playerOverlay {
    background: rgb(245, 245, 245);
}
QWidget#playerTopBar {
    background: rgb(245, 245, 245);
}
QLabel#titleLabel { color: #202020; font-size: 14px; font-weight: bold; }
QLabel#timeLabel  { color: #303030; font-size: 11px; }
QSlider#seekSlider::groove:horizontal { height: 6px; background: rgba(0,0,0,60); border-radius: 3px; }
QSlider#seekSlider::handle:horizontal { background: #5b8def; width: 14px; height: 14px; margin: -4px 0; border-radius: 7px; }
QSlider#seekSlider::handle:horizontal:hover { background: #376fd3; }
QSlider#seekSlider::sub-page:horizontal { background: #5b8def; border-radius: 3px; }
QSlider::groove:horizontal { height: 4px; background: rgba(0,0,0,55); border-radius: 2px; }
QSlider::handle:horizontal { background: #5b8def; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }
QSlider::sub-page:horizontal { background: #5b8def; border-radius: 2px; }
"""

LIGHT_SIDEBAR_STYLE = """
QWidget#sidebarRoot { background: rgba(248, 248, 248, 245); }
QListWidget#playlistList {
    background: transparent;
    color: #202020;
    border: none;
    outline: 0;
    font-size: 13px;
}
QListWidget#playlistList::item { padding: 8px 10px; border-left: 3px solid transparent; }
QListWidget#playlistList::item:hover { background: rgba(91,141,239,40); }
QListWidget#playlistList::item:selected {
    background: rgba(91,141,239,110);
    border-left: 3px solid #5b8def;
    color: #101010;
}
QLineEdit#sidebarSearch {
    background: white;
    color: #202020;
    border: 1px solid rgba(80,80,80,90);
    border-radius: 4px;
    padding: 6px 8px;
    font-size: 12px;
}
"""
