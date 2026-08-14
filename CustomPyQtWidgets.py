from PyQt5.QtGui import QIcon, QFont, QImage, QPixmap, QColor, QDesktopServices, QPalette
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize, QObject, pyqtSignal,
    QRunnable, pyqtSlot, QThreadPool, QModelIndex, QAbstractItemModel, QVariant, QUrl
)
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QLineEdit, QLabel, QPushButton,
    QListWidget, QWidget, QFileDialog, QCheckBox, QSizePolicy, QHBoxLayout,
    QDialog, QFormLayout, QDialogButtonBox, QTabWidget, QListWidgetItem,
    QSpinBox, QMenu, QAction, QTextEdit, QGridLayout, QMessageBox, QListView,
    QTreeWidget, QTreeWidgetItem, QTreeView, QScrollArea, QSlider, QFrame
)

import os
from os import path
import sys
import configparser
import json

class LiveInfoBox(QWidget):
    def __init__(self, parent=None):
        super().__init__()

        self.parent = parent

        #Create LIVE TV info box layout
        self.live_EPG_info_box_layout = QVBoxLayout(self)

        #Create Live TV Channel name label
        self.EPG_box_label = QLabel("Select channel to view Live TV info")
        self.EPG_box_label.setFont(QFont('Segoe UI', 14, QFont.Bold))

        #Enable wordwrap for TV channel name
        self.EPG_box_label.setWordWrap(True)

        self.maxCoverHeight = 200

        #Create cover image
        self.cover          = QLabel()
        self.cover_img      = QPixmap(self.parent.path_to_no_img)
        self.cover.setAlignment(Qt.AlignTop)
        self.cover.setPixmap(self.cover_img.scaledToHeight(self.maxCoverHeight))
        self.cover.setMaximumHeight(self.maxCoverHeight)

        #Create entry info window
        self.live_EPG_info = QTreeWidget()
        self.live_EPG_info.setColumnCount(2)
        self.live_EPG_info.setHeaderLabels(["Date", "From", "To", "Name"])

        #Set column widths of EPG info window
        self.live_EPG_info.setColumnWidth(0, 120)
        self.live_EPG_info.setColumnWidth(1, 50)
        self.live_EPG_info.setColumnWidth(2, 50)

        #Create stream status indicator
        self.stream_status = QLabel()
        self.stream_status_img = QPixmap(self.parent.path_to_unknown_status_icon)
        self.stream_status.setPixmap(self.stream_status_img.scaledToWidth(24))
        self.stream_status.setFixedWidth(25)

        #Create favorites button — wider + larger icon so it sits clearly next
        #to the channel name/logo and isn't clipped (issue #17).
        self.fav_button = QPushButton("")
        self.fav_button.setStyleSheet("text-align: left; padding: 2px;")
        self.fav_button.setFixedSize(32, 32)
        self.fav_button.setIconSize(QSize(24, 24))
        self.fav_button.setFlat(True)
        self.fav_button.setToolTip("Toggle favorite")
        self.fav_button.setIcon(self.parent.favorites_icon)
        self.fav_button.clicked.connect(lambda: self.parent.favButtonPressed("LIVE", self))

        #Create title layout with favorites button
        self.title_layout = QHBoxLayout()
        self.title_layout.addWidget(self.fav_button)
        self.title_layout.addWidget(self.stream_status)
        self.title_layout.addWidget(self.EPG_box_label)

        #Add TV channel label and EPG data to info box
        self.live_EPG_info_box_layout.addLayout(self.title_layout)
        self.live_EPG_info_box_layout.addWidget(self.cover)
        self.live_EPG_info_box_layout.addWidget(self.live_EPG_info)

    def setFavorite(self, is_fav):
        if is_fav:
            #If favorite, set coloured icon
            self.fav_button.setIcon(self.parent.favorites_icon_colour)
        else:
            #If not favorite, set normal icon
            self.fav_button.setIcon(self.parent.favorites_icon)

class MovieInfoBox(QScrollArea):
    def __init__(self, parent=None):
        super().__init__()

        self.parent = parent

        self.yt_code    = None
        self.tmdb_code  = None

        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignTop)

        self.widget = QWidget()

        self.layout = QGridLayout(self.widget)
        self.layout.setAlignment(Qt.AlignTop)

        self.maxCoverWidth = 200

        #Create cover image
        self.cover          = QLabel()
        self.cover_img      = QPixmap(self.parent.path_to_no_img)
        self.cover.setAlignment(Qt.AlignTop)
        self.cover.setPixmap(self.cover_img.scaledToWidth(self.maxCoverWidth))
        self.cover.setFixedWidth(self.maxCoverWidth)

        #Create favorites button — wider + larger icon (issue #17).
        self.fav_button = QPushButton("")
        self.fav_button.setStyleSheet("padding: 2px;")
        self.fav_button.setFixedSize(32, 32)
        self.fav_button.setIconSize(QSize(24, 24))
        self.fav_button.setFlat(True)
        self.fav_button.setToolTip("Toggle favorite")
        self.fav_button.setIcon(self.parent.favorites_icon)
        self.fav_button.clicked.connect(lambda: self.parent.favButtonPressed("Movies", self))

        #Create information labels
        self.name           = QLabel("No movie selected...")
        self.release_date   = QLabel("Release date: —")
        self.country        = QLabel("Country: —")
        self.genre          = QLabel("Genre: —")
        self.duration       = QLabel("Duration: —")
        self.rating         = QLabel("Rating: —")
        self.director       = QLabel("Director: —")
        self.cast           = QLabel("Cast: —")
        self.description    = QLabel("Description: —")

        self.trailer = QLabel()
        self.trailer.setAlignment(Qt.AlignLeft)
        self.trailer.setFixedWidth(50)
        self.trailer.setEnabled(False)

        self.tmdb = QLabel()
        self.tmdb.setAlignment(Qt.AlignLeft)
        self.tmdb.setFixedWidth(50)
        self.tmdb.setEnabled(False)

        #Set YouTube icon
        self.yt_img = QPixmap(self.parent.path_to_yt_img)
        self.trailer.setPixmap(self.yt_img.scaledToHeight(30))

        #Set TMDB icon
        self.tmdb_img = QPixmap(self.parent.path_to_tmdb_img)
        self.tmdb.setPixmap(self.tmdb_img.scaledToHeight(30))

        self.trailer.mousePressEvent    = self.TrailerClicked
        self.tmdb.mousePressEvent       = self.TmdbClicked

        self.name.setFont(QFont('Segoe UI', 14, QFont.Bold))

        self.name.setWordWrap(True)
        self.release_date.setWordWrap(True)
        self.country.setWordWrap(True)
        self.genre.setWordWrap(True)
        self.duration.setWordWrap(True)
        self.rating.setWordWrap(True)
        self.director.setWordWrap(True)
        self.cast.setWordWrap(True)
        self.description.setWordWrap(True)

        #Create layout with title and favorite button
        self.title_layout = QHBoxLayout()
        self.title_layout.addWidget(self.fav_button)
        self.title_layout.addWidget(self.name)

        #Create layout with YouTube and TMDB icon next to each other
        self.links_layout = QHBoxLayout()
        self.links_layout.addWidget(self.trailer)
        self.links_layout.addWidget(self.tmdb)
        self.links_layout.addStretch(1)

        #Add widgets
        self.layout.addLayout(self.title_layout,    0, 0, 1, 2)
        self.layout.addWidget(self.cover,           1, 0, 10, 1)
        self.layout.addWidget(self.release_date,    1, 1)
        self.layout.addWidget(self.country,         2, 1)
        self.layout.addWidget(self.genre,           3, 1)
        self.layout.addWidget(self.duration,        4, 1)
        self.layout.addWidget(self.rating,          5, 1)
        self.layout.addWidget(self.director,        6, 1)
        self.layout.addWidget(self.cast,            7, 1)
        self.layout.addWidget(self.description,     8, 1)
        self.layout.addLayout(self.links_layout,    9, 1)

        self.setWidget(self.widget)

    def TrailerClicked(self, e):
        #Get youtube code from text and append to url
        yt_url = f"https://www.youtube.com/watch?v={self.yt_code}"

        #Open URL
        QDesktopServices.openUrl(QUrl(yt_url))

    def TmdbClicked(self, e):
        #Get TMDB code from text and append to url
        tmdb_url = f"https://www.themoviedb.org/movie/{self.tmdb_code}"

        #Open URL
        QDesktopServices.openUrl(QUrl(tmdb_url))

    def setFavorite(self, is_fav):
        if is_fav:
            #If favorite, set coloured icon
            self.fav_button.setIcon(self.parent.favorites_icon_colour)
        else:
            #If not favorite, set normal icon
            self.fav_button.setIcon(self.parent.favorites_icon)

class SeriesInfoBox(QScrollArea):
    def __init__(self, parent=None):
        super().__init__()

        self.parent = parent

        self.yt_code    = None
        self.tmdb_code  = None

        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignTop)

        self.widget = QWidget()

        self.layout = QGridLayout(self.widget)
        self.layout.setAlignment(Qt.AlignTop)

        self.maxCoverWidth = 200

        #Create cover image
        self.cover          = QLabel()
        self.cover_img      = QPixmap(self.parent.path_to_no_img)
        self.cover.setAlignment(Qt.AlignTop)
        self.cover.setPixmap(self.cover_img.scaledToWidth(self.maxCoverWidth))
        self.cover.setFixedWidth(self.maxCoverWidth)

        #Create favorites button — wider + larger icon (issue #17).
        self.fav_button = QPushButton("")
        self.fav_button.setStyleSheet("padding: 2px;")
        self.fav_button.setFixedSize(32, 32)
        self.fav_button.setIconSize(QSize(24, 24))
        self.fav_button.setFlat(True)
        self.fav_button.setToolTip("Toggle favorite")
        self.fav_button.setIcon(self.parent.favorites_icon)
        self.fav_button.clicked.connect(lambda: self.parent.favButtonPressed("Series", self))

        #Create information labels
        self.name           = QLabel("No series selected...")
        self.release_date   = QLabel("Release date: —")
        self.genre          = QLabel("Genre: —")
        self.num_seasons    = QLabel("Seasons: —")
        self.duration       = QLabel("Episode duration: —")
        self.rating         = QLabel("Rating: —")
        self.director       = QLabel("Director: —")
        self.cast           = QLabel("Cast: —")
        self.description    = QLabel("Description: —")

        self.trailer = QLabel()
        self.trailer.setAlignment(Qt.AlignLeft)
        self.trailer.setFixedWidth(50)
        self.trailer.setEnabled(False)

        self.tmdb = QLabel()
        self.tmdb.setAlignment(Qt.AlignLeft)
        self.tmdb.setFixedWidth(50)
        self.tmdb.setEnabled(False)

        #Set YouTube icon
        self.yt_img = QPixmap(self.parent.path_to_yt_img)
        self.trailer.setPixmap(self.yt_img.scaledToHeight(30))

        #Set TMDB icon
        self.tmdb_img = QPixmap(self.parent.path_to_tmdb_img)
        self.tmdb.setPixmap(self.tmdb_img.scaledToHeight(30))

        self.trailer.mousePressEvent    = self.TrailerClicked
        self.tmdb.mousePressEvent       = self.TmdbClicked

        self.name.setFont(QFont('Segoe UI', 14, QFont.Bold))

        #Enable wordwrap for all labels
        self.name.setWordWrap(True)
        self.release_date.setWordWrap(True)
        self.genre.setWordWrap(True)
        self.num_seasons.setWordWrap(True)
        self.duration.setWordWrap(True)
        self.rating.setWordWrap(True)
        self.director.setWordWrap(True)
        self.cast.setWordWrap(True)
        self.description.setWordWrap(True)

        #Create layout with title and favorite button
        self.title_layout = QHBoxLayout()
        self.title_layout.addWidget(self.fav_button)
        self.title_layout.addWidget(self.name)

        #Create layout with YouTube and TMDB icon next to each other
        self.links_layout = QHBoxLayout()
        self.links_layout.addWidget(self.trailer)
        self.links_layout.addWidget(self.tmdb)
        self.links_layout.addStretch(1)

        #Add widgets
        self.layout.addLayout(self.title_layout,    0, 0, 1, 2)
        self.layout.addWidget(self.cover,           1, 0, 10, 1)
        self.layout.addWidget(self.release_date,    1, 1)
        self.layout.addWidget(self.genre,           2, 1)
        self.layout.addWidget(self.num_seasons,     3, 1)
        self.layout.addWidget(self.duration,        4, 1)
        self.layout.addWidget(self.rating,          5, 1)
        self.layout.addWidget(self.director,        6, 1)
        self.layout.addWidget(self.cast,            7, 1)
        self.layout.addWidget(self.description,     8, 1)
        self.layout.addLayout(self.links_layout,    9, 1)

        #Add widget with all items to the scrollarea (self)
        self.setWidget(self.widget)

    def TrailerClicked(self, e):
        #Get youtube code from text and append to url
        yt_url = f"https://www.youtube.com/watch?v={self.yt_code}"

        #Open URL
        QDesktopServices.openUrl(QUrl(yt_url))

    def TmdbClicked(self, e):
        #Get TMDB code from text and append to url
        tmdb_url = f"https://www.themoviedb.org/tv/{self.tmdb_code}"

        #Open URL
        QDesktopServices.openUrl(QUrl(tmdb_url))

    def setFavorite(self, is_fav):
        if is_fav:
            #If favorite, set coloured icon
            self.fav_button.setIcon(self.parent.favorites_icon_colour)
        else:
            #If not favorite, set normal icon
            self.fav_button.setIcon(self.parent.favorites_icon)


_BTN_STYLE = """
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

_OVERLAY_STYLE = """
QWidget#playerOverlay {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 rgba(0,0,0,60), stop:1 rgba(0,0,0,200));
}
QWidget#playerTopBar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 rgba(0,0,0,200), stop:1 rgba(0,0,0,40));
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

_SIDEBAR_STYLE = """
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


class _ClickableSlider(QSlider):
    """QSlider variant where clicking the track jumps to that position (instead of
    paging in the default ±10% step). Emits sliderPressed/Released around the
    click so the parent's seek logic still gets fired."""

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.maximum() != self.minimum():
            # Compute the position under the click as a value in [minimum, maximum].
            if self.orientation() == Qt.Horizontal:
                ratio = max(0.0, min(1.0, event.x() / max(1, self.width())))
            else:
                ratio = max(0.0, min(1.0, 1.0 - event.y() / max(1, self.height())))
            val = self.minimum() + ratio * (self.maximum() - self.minimum())
            self.setValue(int(val))
            self.sliderPressed.emit()
            self.sliderReleased.emit()
            event.accept()
            return
        super().mousePressEvent(event)


def _find_vlc_plugin_path():
    env_plugin_path = os.environ.get("VLC_PLUGIN_PATH", "").strip()
    if env_plugin_path and path.isdir(env_plugin_path):
        return env_plugin_path

    candidates = []
    if sys.platform.startswith("win"):
        for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
            base_dir = os.environ.get(env_name, "").strip()
            if base_dir:
                candidates.append(path.join(base_dir, "VideoLAN", "VLC", "plugins"))
    elif sys.platform == "darwin":
        candidates.extend([
            "/Applications/VLC.app/Contents/MacOS/plugins",
            path.expanduser("~/Applications/VLC.app/Contents/MacOS/plugins"),
        ])
    else:
        candidates.extend([
            "/usr/lib/vlc/plugins",
            "/usr/lib64/vlc/plugins",
            "/usr/local/lib/vlc/plugins",
            "/snap/vlc/current/usr/lib/vlc/plugins",
        ])

    for candidate in candidates:
        if candidate and path.isdir(candidate):
            return candidate

    return ""


def _find_vlc_executable():
    candidates = []
    if sys.platform.startswith("win"):
        for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
            base_dir = os.environ.get(env_name, "").strip()
            if base_dir:
                candidates.append(path.join(base_dir, "VideoLAN", "VLC", "vlc.exe"))
    elif sys.platform == "darwin":
        candidates.extend([
            "/Applications/VLC.app/Contents/MacOS/VLC",
            path.expanduser("~/Applications/VLC.app/Contents/MacOS/VLC"),
        ])
    else:
        candidates.extend([
            "/usr/bin/vlc",
            "/usr/local/bin/vlc",
            "/snap/bin/vlc",
        ])

    for candidate in candidates:
        if candidate and path.isfile(candidate):
            return candidate

    return ""


class EmbeddedPlayerWindow(QMainWindow):
    """Floating libvlc-backed player window with a nebula-iptv-style UX:

    - Bottom control overlay with emoji icons (⏮ ⏯ ⏭ ⏪ ⏩ 🔊 ⛶ CC)
    - Top overlay with the stream title
    - Auto-hide controls 3s after the last mouse/keyboard event while playing
    - Left-edge sidebar with the current playlist + a live filter; click to play
    - Next/Previous walk the visible playlist, disabled at the edges (no wrap)
    - Subtitle button shows up only when libvlc reports >1 SPU track
    - Keyboard: Space=play/pause, F=fullscreen, S=cycle subs, [/]=prev/next,
      Left/Right=seek ±10s, Up/Down=volume, M=mute

    The whole thing is a single QMainWindow so multi-monitor + window
    management Just Works; the caller provides a `playlist` list-of-dicts
    (each with at least `name` and `url`) plus a starting index.
    """

    playback_failed = pyqtSignal(str, str)

    def __init__(self, parent=None, user_agent=""):
        super().__init__(parent)
        self.setWindowTitle("Internal Player")
        self.resize(1080, 640)

        import vlc
        self._vlc = vlc

        vlc_args = ["--quiet"]
        self._plugin_path = _find_vlc_plugin_path()
        if self._plugin_path:
            os.environ["VLC_PLUGIN_PATH"] = self._plugin_path
            vlc_args.append(f"--plugin-path={self._plugin_path}")
        ua = (user_agent or "").strip()
        if ua:
            vlc_args.append(f"--http-user-agent={ua}")

        self.instance = vlc.Instance(vlc_args)
        self.player = self.instance.media_player_new()
        self._bound = False
        self._current_url = ""
        self._playback_failed_emitted = False

        self._playlist = []   # list of {'name': str, 'url': str, ...}
        self._current_idx = 0
        self._sidebar_visible = False
        self._pinned_sidebar = False
        self._is_fullscreen = False
        self._volume = self._load_volume_pref()
        self.player.audio_set_volume(self._volume)
        self._app_parent = parent  # IPTVPlayerApp, used to access favorites/user-agent

        # ---------- Central widgets ----------
        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("background-color: black;")
        self.video_frame.setMinimumSize(640, 360)
        # Capture mouse moves on the video to wake the controls.
        self.video_frame.setMouseTracking(True)
        self.video_frame.installEventFilter(self)

        # ---------- Top overlay (title + sidebar toggle) ----------
        self.top_bar = QWidget(self)
        self.top_bar.setObjectName("playerTopBar")
        self.top_bar.setFixedHeight(44)
        self.title_label = QLabel("")
        self.title_label.setObjectName("titleLabel")
        self.title_label.setMinimumWidth(200)
        self.btn_sidebar = QPushButton("☰")  # hamburger
        self.btn_sidebar.setToolTip("Show/hide playlist (L)")
        self.btn_sidebar.clicked.connect(self.toggle_sidebar)
        top_lay = QHBoxLayout(self.top_bar)
        top_lay.setContentsMargins(12, 6, 12, 6)
        top_lay.addWidget(self.btn_sidebar)
        top_lay.addWidget(self.title_label, 1)

        # ---------- Bottom overlay (seek + buttons + volume) ----------
        self.overlay = QWidget(self)
        self.overlay.setObjectName("playerOverlay")
        self.overlay.setFixedHeight(110)

        # Custom slider that jumps to clicked position. The previous QSlider only
        # supported drag-to-seek; clicking the track did a +10% page-step which
        # made seeking through long movies/episodes infuriating.
        self.seek_slider = _ClickableSlider(Qt.Horizontal)
        self.seek_slider.setObjectName("seekSlider")
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.setCursor(Qt.PointingHandCursor)
        self.seek_slider.sliderPressed.connect(self._seek_pressed)
        self.seek_slider.sliderMoved.connect(self._seek_moved)
        self.seek_slider.sliderReleased.connect(self._seek_released)
        self._seeking = False

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("timeLabel")

        # Buttons — unicode emoji per nebula's style.
        self.btn_prev   = QPushButton("⏮")        # ⏮
        self.btn_rewind = QPushButton("⏪")        # ⏪
        self.btn_play   = QPushButton("⏸")        # ⏸
        self.btn_ffwd   = QPushButton("⏩")        # ⏩
        self.btn_next   = QPushButton("⏭")        # ⏭
        self.btn_slow   = QPushButton("\U0001f422")    # 🐢
        self.btn_fast   = QPushButton("\U0001f407")    # 🐇
        self.rate_label = QLabel("1.00x")
        self.rate_label.setStyleSheet("color: white; padding: 0 8px;")
        self.btn_mute   = QPushButton("\U0001f50a")    # 🔊
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(self._volume)
        self.vol_slider.setFixedWidth(120)
        self.btn_subs   = QPushButton("CC")
        self.btn_subs.setEnabled(False)
        self.btn_fs     = QPushButton("⛶")        # ⛶
        self.pl_pos     = QLabel("")
        self.pl_pos.setStyleSheet("color: #ccc; padding: 0 8px;")

        for b in (self.btn_prev, self.btn_rewind, self.btn_play, self.btn_ffwd,
                  self.btn_next, self.btn_slow, self.btn_fast, self.btn_mute,
                  self.btn_subs, self.btn_fs, self.btn_sidebar):
            b.setStyleSheet(_BTN_STYLE)
            b.setFixedHeight(34)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)

        self.btn_prev.setToolTip("Previous (])")
        self.btn_rewind.setToolTip("Rewind 10s (←)")
        self.btn_play.setToolTip("Play / Pause (Space)")
        self.btn_ffwd.setToolTip("Forward 10s (→)")
        self.btn_next.setToolTip("Next ([)")
        self.btn_slow.setToolTip("Slower")
        self.btn_fast.setToolTip("Faster")
        self.btn_mute.setToolTip("Mute (M)")
        self.btn_subs.setToolTip("Subtitles (S)")
        self.btn_fs.setToolTip("Fullscreen (F)")

        self.btn_prev.clicked.connect(self.previous)
        self.btn_rewind.clicked.connect(lambda: self.seek_by(-10000))
        self.btn_play.clicked.connect(self.toggle_play_pause)
        self.btn_ffwd.clicked.connect(lambda: self.seek_by(10000))
        self.btn_next.clicked.connect(self.next)
        self.btn_slow.clicked.connect(lambda: self._adjust_rate(-0.25))
        self.btn_fast.clicked.connect(lambda: self._adjust_rate(0.25))
        self.btn_mute.clicked.connect(self.toggle_mute)
        self.vol_slider.valueChanged.connect(self.set_volume)
        self.btn_subs.clicked.connect(self._show_subs_menu)
        self.btn_fs.clicked.connect(self.toggle_fullscreen)

        seek_row = QHBoxLayout()
        seek_row.setContentsMargins(12, 4, 12, 0)
        seek_row.addWidget(self.seek_slider, 1)
        seek_row.addSpacing(8)
        seek_row.addWidget(self.time_label)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 0, 12, 8)
        btn_row.setSpacing(4)
        btn_row.addWidget(self.btn_prev)
        btn_row.addWidget(self.btn_rewind)
        btn_row.addWidget(self.btn_play)
        btn_row.addWidget(self.btn_ffwd)
        btn_row.addWidget(self.btn_next)
        btn_row.addSpacing(12)
        btn_row.addWidget(self.btn_slow)
        btn_row.addWidget(self.rate_label)
        btn_row.addWidget(self.btn_fast)
        btn_row.addStretch(1)
        btn_row.addWidget(self.pl_pos)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_mute)
        btn_row.addWidget(self.vol_slider)
        btn_row.addSpacing(8)
        btn_row.addWidget(self.btn_subs)
        btn_row.addWidget(self.btn_fs)

        overlay_lay = QVBoxLayout(self.overlay)
        overlay_lay.setContentsMargins(0, 0, 0, 0)
        overlay_lay.setSpacing(2)
        overlay_lay.addLayout(seek_row)
        overlay_lay.addLayout(btn_row)

        self.overlay.setStyleSheet(_OVERLAY_STYLE)
        self.top_bar.setStyleSheet(_OVERLAY_STYLE)

        # Cursor policy: the controls and top bar always show the normal arrow,
        # the video frame is the only thing that ever shows the blank cursor.
        # Buttons get PointingHandCursor (set per-button above).
        self.overlay.setCursor(Qt.ArrowCursor)
        self.top_bar.setCursor(Qt.ArrowCursor)
        self.vol_slider.setCursor(Qt.PointingHandCursor)

        # ---------- Sidebar (playlist) ----------
        self.sidebar = QWidget(self)
        self.sidebar.setObjectName("sidebarRoot")
        self.sidebar.setStyleSheet(_SIDEBAR_STYLE)
        self.sidebar.setFixedWidth(320)
        self.sidebar.setCursor(Qt.ArrowCursor)
        self.sidebar.hide()

        self.sidebar_search = QLineEdit()
        self.sidebar_search.setObjectName("sidebarSearch")
        self.sidebar_search.setPlaceholderText("Filter…")
        self.sidebar_search.textChanged.connect(self._refresh_sidebar)

        self.playlist_list = QListWidget()
        self.playlist_list.setObjectName("playlistList")
        self.playlist_list.setCursor(Qt.PointingHandCursor)
        self.playlist_list.itemActivated.connect(self._playlist_item_activated)
        self.playlist_list.itemClicked.connect(self._playlist_item_activated)

        sidebar_lay = QVBoxLayout(self.sidebar)
        sidebar_lay.setContentsMargins(8, 8, 8, 8)
        sidebar_lay.setSpacing(6)
        sidebar_lay.addWidget(self.sidebar_search)
        sidebar_lay.addWidget(self.playlist_list, 1)

        # ---------- Compose ----------
        central = QWidget()
        central.setMouseTracking(True)
        central.installEventFilter(self)
        # The video frame fills the entire central widget; overlays are absolute-positioned.
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.video_frame, 1)
        self.setCentralWidget(central)

        # Reparent overlays to centralWidget so they sit above the video.
        self.overlay.setParent(central)
        self.overlay.raise_()
        self.top_bar.setParent(central)
        self.top_bar.raise_()
        self.sidebar.setParent(central)
        self.sidebar.raise_()

        # ---------- Auto-hide timer ----------
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_controls)

        self.setMouseTracking(True)
        self.installEventFilter(self)

        # Catch mouse activity at the application level too — libvlc's child HWND
        # swallows mouse-move events on Windows even after `video_set_mouse_input(False)`
        # under some renderers, so this is the belt-and-braces wake path.
        try:
            QApplication.instance().installEventFilter(self)
        except Exception:
            pass

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(500)
        self._poll_timer.timeout.connect(self._poll_state)
        self._poll_timer.start()

        # Periodically check the cursor's global position; if it's inside the
        # player window and we're hidden, wake. This catches any mouse-move that
        # neither Qt's eventFilter nor libvlc's forwarding picked up.
        self._cursor_watch = QTimer(self)
        self._cursor_watch.setInterval(250)
        self._cursor_watch.timeout.connect(self._cursor_watch_tick)
        self._cursor_watch.start()
        self._last_cursor_pos = None

        # Global key shortcuts (work whenever the player window has focus).
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence
        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self.toggle_play_pause)
        QShortcut(QKeySequence(Qt.Key_F),     self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key_S),     self, activated=self._cycle_subs)
        QShortcut(QKeySequence(Qt.Key_M),     self, activated=self.toggle_mute)
        QShortcut(QKeySequence(Qt.Key_BracketLeft),  self, activated=self.next)      # nebula uses ]
        QShortcut(QKeySequence(Qt.Key_BracketRight), self, activated=self.previous)
        QShortcut(QKeySequence(Qt.Key_Left),  self, activated=lambda: self.seek_by(-10000))
        QShortcut(QKeySequence(Qt.Key_Right), self, activated=lambda: self.seek_by(10000))
        QShortcut(QKeySequence(Qt.Key_Up),    self, activated=lambda: self._step_volume(5))
        QShortcut(QKeySequence(Qt.Key_Down),  self, activated=lambda: self._step_volume(-5))
        QShortcut(QKeySequence(Qt.Key_L),     self, activated=self.toggle_sidebar)
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self._exit_fullscreen_if_needed)

        self._wake_controls()
        self._attach_vlc_events()

    # ---------- public API ----------
    @staticmethod
    def is_available():
        try:
            import vlc  # noqa: F401
            vlc_args = ["--quiet"]
            plugin_path = _find_vlc_plugin_path()
            if plugin_path:
                os.environ["VLC_PLUGIN_PATH"] = plugin_path
                vlc_args.append(f"--plugin-path={plugin_path}")
            vlc.Instance(vlc_args)
            return True
        except Exception:
            return False

    @staticmethod
    def find_vlc_executable():
        return _find_vlc_executable()

    def play_url(self, url, title="", playlist=None, index=0):
        if playlist is not None:
            self._playlist = list(playlist)
            self._current_idx = max(0, min(index, len(self._playlist) - 1)) if self._playlist else 0
            self._refresh_sidebar()
        elif not self._playlist:
            # Single-item playlist so next/prev are gracefully disabled.
            self._playlist = [{'name': title or url, 'url': url}]
            self._current_idx = 0

        title = title or (self._playlist[self._current_idx].get('name') if self._playlist else url)
        self.setWindowTitle(f"Internal Player — {title}")
        self.title_label.setText(title)

        media = self.instance.media_new(url)
        self.player.set_media(media)
        self._current_url = url or ""
        self._playback_failed_emitted = False
        self.show()
        self.raise_()
        self.activateWindow()
        self._bind_video_output()
        play_result = self.player.play()
        if play_result == -1:
            self._emit_playback_failed("libVLC rejected the stream before playback could start.")
        self.btn_play.setText("⏸")  # pause icon
        self._update_pl_pos()
        self._wake_controls()

    # ---------- video output binding ----------
    def _bind_video_output(self):
        if self._bound:
            return
        win_id = int(self.video_frame.winId())
        if sys.platform.startswith("win"):
            self.player.set_hwnd(win_id)
        elif sys.platform == "darwin":
            self.player.set_nsobject(win_id)
        else:
            self.player.set_xwindow(win_id)
        # Crucial on Windows: libvlc creates a child HWND inside our QFrame and by
        # default captures every mouse / key event there, which means Qt never sees
        # mouse-move events over the video and the auto-hide chrome can't wake back
        # up. Turning libvlc's own input handling off forwards those events to the
        # parent window so Qt's eventFilter picks them up.
        try:
            self.player.video_set_mouse_input(False)
            self.player.video_set_key_input(False)
        except Exception:
            pass
        self._bound = True

    # ---------- transport ----------
    def toggle_play_pause(self):
        if self.player.is_playing():
            self.player.pause()
            self.btn_play.setText("▶")  # ▶
        else:
            self.player.play()
            self.btn_play.setText("⏸")
        self._wake_controls()

    def stop(self):
        self.player.stop()
        self.btn_play.setText("▶")

    def seek_by(self, ms):
        cur = self.player.get_time()
        if cur < 0:
            return
        new = max(0, cur + ms)
        self.player.set_time(int(new))
        self._wake_controls()

    def set_volume(self, value):
        self._volume = int(value)
        self.player.audio_set_volume(self._volume)
        self.btn_mute.setText("\U0001f508" if self._volume == 0 else "\U0001f50a")  # 🔈 vs 🔊
        self._save_volume_pref()

    def _step_volume(self, delta):
        self.vol_slider.setValue(max(0, min(100, self._volume + delta)))
        self._wake_controls()

    def toggle_mute(self):
        self.player.audio_toggle_mute()
        muted = self.player.audio_get_mute() == 1
        self.btn_mute.setText("\U0001f507" if muted else "\U0001f50a")  # 🔇 vs 🔊
        self._wake_controls()

    def _adjust_rate(self, delta):
        try:
            rate = max(0.25, min(4.0, self.player.get_rate() + delta))
        except Exception:
            rate = 1.0
        self.player.set_rate(rate)
        self.rate_label.setText(f"{rate:.2f}x")
        self._wake_controls()

    # ---------- next / previous ----------
    def next(self):
        if self._current_idx + 1 >= len(self._playlist):
            return
        self._current_idx += 1
        self._play_current()

    def previous(self):
        if self._current_idx <= 0:
            return
        self._current_idx -= 1
        self._play_current()

    def _play_current(self):
        if not self._playlist:
            return
        entry = self._playlist[self._current_idx]
        url = entry.get('url')
        if not url:
            # Skip ahead if the entry has no playable URL (e.g. series-level item).
            return
        self.play_url(url, title=entry.get('name', ''), playlist=self._playlist, index=self._current_idx)

    def _update_pl_pos(self):
        n = len(self._playlist)
        if n <= 1:
            self.pl_pos.setText("")
        else:
            self.pl_pos.setText(f"{self._current_idx + 1} / {n}")
        self.btn_prev.setEnabled(self._current_idx > 0)
        self.btn_next.setEnabled(self._current_idx + 1 < n)

    # ---------- subtitles ----------
    def _subs_tracks(self):
        try:
            descs = self.player.video_get_spu_description() or []
            # Format: [(id, b'Name'), ...]
            return [(int(i), n.decode("utf-8", errors="replace") if isinstance(n, bytes) else str(n))
                    for i, n in descs]
        except Exception:
            return []

    def _update_subs_button(self):
        tracks = self._subs_tracks()
        # The first track is always "Disable", so >1 means real tracks exist.
        self.btn_subs.setEnabled(len(tracks) > 1)

    def _show_subs_menu(self):
        tracks = self._subs_tracks()
        if not tracks:
            return
        menu = QMenu(self)
        try:
            current = self.player.video_get_spu()
        except Exception:
            current = -1
        for tid, name in tracks:
            act = QAction(name, self)
            act.setCheckable(True)
            act.setChecked(tid == current)
            act.triggered.connect(lambda _, t=tid: self.player.video_set_spu(t))
            menu.addAction(act)
        menu.exec_(self.btn_subs.mapToGlobal(self.btn_subs.rect().bottomLeft()))

    def _cycle_subs(self):
        tracks = self._subs_tracks()
        if len(tracks) <= 1:
            return
        try:
            current = self.player.video_get_spu()
        except Exception:
            current = -1
        ids = [t[0] for t in tracks]
        try:
            i = ids.index(current)
            nxt = ids[(i + 1) % len(ids)]
        except ValueError:
            nxt = ids[0]
        self.player.video_set_spu(nxt)
        self._wake_controls()

    # ---------- fullscreen ----------
    def toggle_fullscreen(self):
        if self._is_fullscreen:
            self.showNormal()
            self._is_fullscreen = False
        else:
            self.showFullScreen()
            self._is_fullscreen = True
        self._reposition_overlays()

    def _exit_fullscreen_if_needed(self):
        if self._is_fullscreen:
            self.toggle_fullscreen()

    # ---------- sidebar ----------
    def toggle_sidebar(self):
        self._sidebar_visible = not self._sidebar_visible
        if self._sidebar_visible:
            self._refresh_sidebar()
            self.sidebar.show()
            self.sidebar.raise_()
            self._reposition_overlays()
        else:
            self.sidebar.hide()

    def _refresh_sidebar(self):
        needle = self.sidebar_search.text().strip().lower()
        self.playlist_list.clear()
        for i, entry in enumerate(self._playlist):
            name = entry.get('name', '')
            if needle and needle not in name.lower():
                continue
            item = QListWidgetItem(f"{i + 1:>3}.  {name}")
            item.setData(Qt.UserRole, i)
            self.playlist_list.addItem(item)
            if i == self._current_idx:
                self.playlist_list.setCurrentItem(item)

    def _playlist_item_activated(self, item):
        idx = item.data(Qt.UserRole)
        if not isinstance(idx, int) or idx < 0 or idx >= len(self._playlist):
            return
        self._current_idx = idx
        self._play_current()
        if not self._pinned_sidebar:
            QTimer.singleShot(800, lambda: self.sidebar.hide())
            self._sidebar_visible = False

    # ---------- show / hide the player controls ----------
    def _wake_controls(self):
        self.overlay.show()
        self.top_bar.show()
        # Restore the normal cursor on the video frame; the overlay and top bar
        # have their own ArrowCursor set in _init_cursors so they never blank.
        self.video_frame.unsetCursor()
        self._reposition_overlays()
        # 3s timeout matches nebula; only auto-hides while actually playing.
        if self.player.is_playing():
            self._hide_timer.start(3000)
        else:
            self._hide_timer.stop()

    def _hide_controls(self):
        if self._sidebar_visible:
            return
        if not self.player.is_playing():
            return
        self.overlay.hide()
        self.top_bar.hide()
        # Hide the cursor only over the video frame, NOT over the controls or
        # the overall window. The overlay/top_bar/sidebar all have their own
        # cursor set (ArrowCursor / PointingHandCursor on buttons) so they
        # remain visible regardless.
        self.video_frame.setCursor(Qt.BlankCursor)

    def _cursor_watch_tick(self):
        # Wake the chrome whenever the global cursor moves while it's inside our
        # window — covers the libvlc-child-window blind spot on Windows.
        if not self.isVisible():
            return
        try:
            from PyQt5.QtGui import QCursor
            pos = QCursor.pos()
        except Exception:
            return
        if self._last_cursor_pos is None:
            self._last_cursor_pos = pos
            return
        if pos == self._last_cursor_pos:
            return
        self._last_cursor_pos = pos
        if self.frameGeometry().contains(pos):
            self._wake_controls()

    def _reposition_overlays(self):
        if not self.centralWidget():
            return
        w = self.centralWidget().width()
        h = self.centralWidget().height()
        self.top_bar.setGeometry(0, 0, w, self.top_bar.height())
        self.overlay.setGeometry(0, h - self.overlay.height(), w, self.overlay.height())
        if self._sidebar_visible:
            self.sidebar.setGeometry(0, self.top_bar.height(),
                                     self.sidebar.width(),
                                     h - self.top_bar.height())

    # ---------- VLC poll ----------
    def _poll_state(self):
        try:
            state = self.player.get_state()
            if state == self._vlc.State.Error:
                self._emit_playback_failed("libVLC reported a playback error for this stream.")
                return
            length = self.player.get_length()
            cur    = self.player.get_time()
            if length > 0 and not self._seeking:
                self.seek_slider.setEnabled(True)
                self.seek_slider.setValue(int(cur / length * 1000))
                self.time_label.setText(f"{self._fmt_ms(cur)} / {self._fmt_ms(length)}")
            else:
                # Live stream — disable scrubbing, show LIVE label.
                self.seek_slider.setEnabled(False)
                self.seek_slider.setValue(0)
                self.time_label.setText("LIVE")
            self._update_subs_button()
        except Exception:
            pass

    def _attach_vlc_events(self):
        try:
            self._event_manager = self.player.event_manager()
            self._event_manager.event_attach(
                self._vlc.EventType.MediaPlayerEncounteredError,
                self._on_vlc_error,
            )
        except Exception:
            self._event_manager = None

    def _on_vlc_error(self, event):
        self._emit_playback_failed("libVLC encountered an error while opening the stream.")

    def _emit_playback_failed(self, message):
        if not self._current_url or self._playback_failed_emitted:
            return
        self._playback_failed_emitted = True
        self.playback_failed.emit(self._current_url, message)

    def _seek_pressed(self):
        # Set the seeking flag the moment the user grabs (or clicks) the slider,
        # so the 500 ms poll timer doesn't yank the handle back while they drag.
        self._seeking = True

    def _seek_moved(self, value):
        self._seeking = True

    def _seek_released(self):
        try:
            length = self.player.get_length()
            if length > 0:
                self.player.set_time(int(self.seek_slider.value() / 1000 * length))
        finally:
            self._seeking = False
            self._wake_controls()

    @staticmethod
    def _fmt_ms(ms):
        if ms is None or ms < 0:
            return "00:00"
        s = int(ms // 1000)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    # ---------- volume persistence ----------
    def _volume_pref_path(self):
        try:
            return path.join(path.dirname(path.abspath(self._app_parent.user_data_file)),
                             ".embedded_player_volume")
        except Exception:
            return None

    def _load_volume_pref(self):
        p = self._volume_pref_path()
        if not p or not path.isfile(p):
            return 80
        try:
            with open(p, "r") as f:
                return max(0, min(100, int(f.read().strip())))
        except (OSError, ValueError):
            return 80

    def _save_volume_pref(self):
        p = self._volume_pref_path()
        if not p:
            return
        try:
            with open(p, "w") as f:
                f.write(str(self._volume))
        except OSError:
            pass

    # ---------- events ----------
    def _obj_is_in_player(self, obj):
        # Walk the parent chain to see if `obj` is a descendant of this window.
        # Used so the QApplication-wide filter doesn't react to events on the
        # main window when the player isn't the active window.
        w = obj
        while w is not None:
            if w is self:
                return True
            try:
                w = w.parent()
            except Exception:
                return False
        return False

    def _obj_is_on_controls(self, obj):
        # True when `obj` is the overlay, top bar, sidebar, or any of their
        # descendants. We use this to suppress double-click-fullscreen and
        # play/pause when the click was on a control button or playlist row.
        for root in (self.overlay, self.top_bar, self.sidebar):
            w = obj
            while w is not None:
                if w is root:
                    return True
                try:
                    w = w.parent()
                except Exception:
                    break
        return False

    def eventFilter(self, obj, event):
        from PyQt5.QtCore import QEvent
        et = event.type()

        # An eventFilter installed on QApplication is invoked with the RECEIVING
        # widget as `obj` — not QApplication itself. So the only reliable way
        # to scope our handling to the player window is to walk the parent
        # chain and bail out for any event whose target sits outside our tree.
        # Otherwise a double-click on the main window's central widget would
        # fire the player's toggle_fullscreen().
        if not self._obj_is_in_player(obj):
            return False

        if et in (QEvent.MouseMove, QEvent.MouseButtonPress, QEvent.MouseButtonDblClick,
                  QEvent.KeyPress, QEvent.Wheel):
            self._wake_controls()

        if et == QEvent.Wheel:
            # Mouse wheel anywhere on the video = volume up/down (nebula-style).
            try:
                delta = event.angleDelta().y()
            except Exception:
                delta = 0
            if delta > 0:
                self._step_volume(5)
            elif delta < 0:
                self._step_volume(-5)
            return True

        # Don't fire video-area shortcuts (middle-click pause, double-click
        # fullscreen) when the user clicked on a control button or a playlist row.
        on_controls = self._obj_is_on_controls(obj)

        if et == QEvent.MouseButtonPress and not on_controls:
            try:
                btn = event.button()
            except Exception:
                btn = None
            if btn == Qt.MidButton:
                # Middle-click toggles play/pause (matches the muscle memory of
                # users coming from MPC-HC, mpv, etc.).
                self.toggle_play_pause()
                return True

        if et == QEvent.MouseButtonDblClick and not on_controls:
            # Double-click toggles fullscreen (matches most video players).
            self.toggle_fullscreen()
            return True

        return False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_overlays()

    def closeEvent(self, event):
        try:
            self._save_volume_pref()
            self.player.stop()
        except Exception:
            pass
        super().closeEvent(event)
