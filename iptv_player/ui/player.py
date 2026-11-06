"""Embedded VLC player window and controls."""

import configparser
import ctypes
import ctypes.util
import logging
from os import path
import sys
import time
import uuid
from urllib.parse import urlsplit

from PyQt5.QtCore import QByteArray, QEvent, QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QCursor,
    QIcon,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QPolygon,
)
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QSlider,
    QStyle,
    QStyleOption,
    QToolTip,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from iptv_player.config.internal_player import VIDEO_ASPECT_RATIOS, load_video_format, save_video_format, load_window_aspect_lock, save_window_aspect_lock
from iptv_player.video_aspect import display_aspect_ratio
from iptv_player.ui.window_aspect import WindowAspectController
from iptv_player.config import write_config_file
from iptv_player.constants import DEFAULT_RESUME_BEHAVIOR, RESUME_BEHAVIORS
from iptv_player.storage.history import resume_position
from iptv_player.ui.info_panel_layout import information_panel_size
from iptv_player.programme_info import programme_html, EpgRefreshState
from iptv_player.stream_info import collect_stream_information
from iptv_player.ui.theme import (
    application_palette_is_dark,
    apply_windows_title_bar_theme,
)
from iptv_player.vlc_diagnostics import describe_vlc_load_failure
from iptv_player.linux_vlc_runtime import configure_linux_vlc_plugins
from iptv_player.ui.widgets import KeyboardNavigableListWidget
from iptv_player.ui.player_theme import (
    DARK_BUTTON_STYLE,
    DARK_OVERLAY_STYLE,
    DARK_SIDEBAR_STYLE,
    LIGHT_BUTTON_STYLE,
    LIGHT_OVERLAY_STYLE,
    LIGHT_SIDEBAR_STYLE,
)
from iptv_player.utils.search import normalize_search_text, title_matches_search


def set_macos_activation_policy(visible):
    """Show or hide the isolated player process in the macOS Dock."""
    if sys.platform != "darwin":
        return
    try:
        appkit_path = ctypes.util.find_library("AppKit")
        objc_path = ctypes.util.find_library("objc")
        if not appkit_path or not objc_path:
            return
        ctypes.CDLL(appkit_path)
        objc = ctypes.CDLL(objc_path)
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]

        send = objc.objc_msgSend
        send.restype = ctypes.c_void_p
        application = send(
            ctypes.c_void_p(objc.objc_getClass(b"NSApplication")),
            ctypes.c_void_p(objc.sel_registerName(b"sharedApplication")),
        )
        if not application:
            return

        # NSApplicationActivationPolicyRegular = 0, Accessory = 1.
        send.restype = None
        send(
            ctypes.c_void_p(application),
            ctypes.c_void_p(objc.sel_registerName(b"setActivationPolicy:")),
            ctypes.c_long(0 if visible else 1),
        )
        if visible:
            send(
                ctypes.c_void_p(application),
                ctypes.c_void_p(objc.sel_registerName(b"activateIgnoringOtherApps:")),
                ctypes.c_bool(True),
            )
    except (AttributeError, OSError, TypeError, ValueError):
        pass


VOD_PAUSE_RECONNECT_SECONDS = 30.0


def _pause_blocks_navigation(window):
    """Share the pause/recovery guard between end events and credits skipping."""
    return (getattr(window, '_pause_started_at', None) is not None
            or getattr(window, '_recovering_after_pause', False)
            or getattr(window, '_pause_recovery_failed', False))


class _PlaylistSidebar(QWidget):
    """Prefer a content-based width without imposing it on the player window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._preferred_width = 0

    def sizeHint(self):
        size = super().sizeHint()
        size.setWidth(self._preferred_width)
        return size

    def minimumSizeHint(self):
        size = super().minimumSizeHint()
        size.setWidth(0)
        return size

    def set_preferred_width(self, width):
        if self._preferred_width != width:
            self._preferred_width = width
            self.updateGeometry()
        self.setMaximumWidth(width)


class _ClickableSlider(QSlider):
    """Seek slider that previews a dragged position and applies it on release."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dragging = False

    def _value_at_event(self, event):
        """Map a pointer position to the slider range."""
        if self.orientation() == Qt.Horizontal:
            ratio = max(0.0, min(1.0, event.x() / max(1, self.width())))
        else:
            ratio = max(0.0, min(1.0, 1.0 - event.y() / max(1, self.height())))
        return int(self.minimum() + ratio * (self.maximum() - self.minimum()))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.maximum() != self.minimum():
            self._dragging = True
            self.setValue(self._value_at_event(event))
            self.grabMouse()
            self.sliderPressed.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and event.buttons() & Qt.LeftButton:
            value = self._value_at_event(event)
            self.setValue(value)
            self.sliderMoved.emit(value)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.LeftButton:
            value = self._value_at_event(event)
            self.setValue(value)
            self.sliderMoved.emit(value)
            self._dragging = False
            self.releaseMouse()
            self.sliderReleased.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class EmbeddedPlayerWindow(QMainWindow):
    """Floating libvlc-backed player window with a nebula-iptv-style UX:

    - Bottom control overlay with emoji icons (⏮ ⏯ ⏭ ⏪ ⏩ 🔊 ⛶ CC)
    - Top overlay with the stream title
    - Auto-hide controls 3s after the last mouse/keyboard event while playing
    - Left-edge sidebar with the current playlist + a live filter; click to play
    - Next/Previous walk the visible playlist, disabled at the edges (no wrap)
    - Completed on-demand items automatically advance to the next playlist item
    - Subtitle button shows up only when libvlc reports >1 SPU track
    - Keyboard: Space=play/pause, F=fullscreen, A/S=cycle audio/subtitles,
      Page Up/Page Down=previous/next,
      Left/Right=seek ±10s, Up/Down=volume, +/-=speed, M=mute

    The whole thing is a single QMainWindow so multi-monitor + window
    management Just Works; the caller provides a `playlist` list-of-dicts
    (each with at least `name` and `url`) plus a starting index.
    """

    media_ended = pyqtSignal(int)

    def __init__(
        self, parent=None, user_agent="", settings_path=None,
        seek_step_seconds=10, volume_step_percent=2, speed_step=0.25,
        audio_language="", subtitle_language="", resume_behavior="ask",
        auto_play_next=False, auto_advance_seconds=0, network_caching_ms=1000,
        progress_callback=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Internal Player")
        self.setWindowIcon(self._player_window_icon())
        self.resize(1080, 640)

        configure_linux_vlc_plugins()
        import vlc
        self._vlc = vlc

        vlc_args = ["--quiet"]
        self._user_agent = (user_agent or "").strip()
        ua = self._user_agent
        if ua:
            vlc_args.append(f"--http-user-agent={ua}")

        self.instance = vlc.Instance(vlc_args)
        self.player = self.instance.media_player_new()
        self._media_generation = 0
        self.media_ended.connect(self._advance_after_media_end)
        self._vlc_event_manager = self.player.event_manager()
        self._vlc_event_manager.event_attach(
            vlc.EventType.MediaPlayerEndReached,
            self._on_media_ended,
        )

        self._playlist = []   # list of {'name': str, 'url': str, ...}
        self._current_idx = 0
        self._sidebar_visible = False
        self._pinned_sidebar = False
        self._is_fullscreen = False
        self._muted = False
        self._last_wheel_event_id = None
        self._paused_by_minimize = False
        self._pause_started_at = None
        self._pause_position_ms = 0
        self._recovering_after_pause = False
        self._pause_recovery_failed = False
        self._pause_recovery_deadline = 0.0
        self._current_url = ""
        self._seek_osd_total_ms = 0
        self._seek_target_ms = 0
        self._seek_sequence_origin_ms = 0
        self._seek_osd_active = False
        self._pending_playback_rate_attempts = 0
        # Start from safe values; set_control_steps performs defensive parsing
        # after every control has been created and can update its tooltip.
        self._seek_step_ms = 10000
        self._volume_step = 2
        self._speed_step = 0.25
        self._audio_language = ""
        self._subtitle_language = ""
        self._progress_callback = progress_callback
        self._current_history = None
        self._current_stream_protocol = ""
        self._pending_resume_ms = 0
        self._pending_resume_attempts = 0
        self._deferred_present = False
        self._deferred_present_polls = 0
        self._deferred_keep_topmost = False
        self._last_progress_report = 0.0
        self._resume_behavior = (
            resume_behavior if resume_behavior in RESUME_BEHAVIORS
            else DEFAULT_RESUME_BEHAVIOR
        )
        self._auto_play_next = bool(auto_play_next)
        self._auto_advance_seconds = max(0, min(int(auto_advance_seconds), 300))
        self._network_caching_ms = max(0, min(int(network_caching_ms), 60000))
        self._auto_advance_triggered = False
        self._app_parent = parent
        self._explicit_settings_path = settings_path
        self._volume = self._load_volume_pref()
        self._playback_rate = self._load_playback_rate_pref()
        self._video_format = load_video_format(self._settings_path())
        self._window_aspect_locked = load_window_aspect_lock(self._settings_path())
        self._volume_before_mute = self._volume if self._volume > 0 else 80
        self.player.audio_set_volume(self._volume)
        self.player.audio_set_mute(False)

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
        self.top_bar.setFixedHeight(40)
        self.title_label = QLabel("")
        self.title_label.setObjectName("titleLabel")
        self.title_label.setMinimumWidth(200)
        self.btn_sidebar = QPushButton()
        self.btn_sidebar.setToolTip("Show/hide playlist (L)")
        self.btn_sidebar.clicked.connect(self.toggle_sidebar)
        top_lay = QHBoxLayout(self.top_bar)
        top_lay.setContentsMargins(10, 4, 10, 4)
        top_lay.addWidget(self.btn_sidebar)
        top_lay.addWidget(self.title_label, 1)

        # ---------- Bottom overlay (seek + buttons + volume) ----------
        self.overlay = QWidget(self)
        self.overlay.setObjectName("playerOverlay")
        self.overlay.setFixedHeight(72)

        # Custom slider that jumps to clicked position. The previous QSlider only
        # supported drag-to-seek; clicking the track did a +10% page-step which
        # made seeking through long movies/episodes infuriating.
        self.seek_slider = _ClickableSlider(Qt.Horizontal)
        self.seek_slider.setObjectName("seekSlider")
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.setFixedHeight(14)
        self.seek_slider.setCursor(Qt.PointingHandCursor)
        self.seek_slider.sliderPressed.connect(self._seek_pressed)
        self.seek_slider.sliderMoved.connect(self._seek_moved)
        self.seek_slider.sliderReleased.connect(self._seek_released)
        self._seeking = False

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("timeLabel")

        # Native Qt media icons stay consistent across fonts and platforms.
        self.btn_prev   = QPushButton()
        self.btn_rewind = QPushButton()
        self.btn_play   = QPushButton()
        self.btn_ffwd   = QPushButton()
        self.btn_next   = QPushButton()
        self.btn_slow   = QPushButton()
        self.btn_fast   = QPushButton()
        self.rate_label = QLabel(f"{self._playback_rate:.2f}x")
        self.rate_controls = QWidget()
        self.rate_controls.setObjectName("rateControls")
        self.btn_programme = QPushButton()
        self.btn_programme.setCheckable(True)
        self.btn_programme.setEnabled(False)
        self.btn_programme.setAccessibleName("Programme information")
        self.btn_programme.setToolTip("Programme / movie / episode summary (P)")
        self.btn_programme.clicked.connect(self._toggle_programme_information)
        self._programme_payload = None
        self._programme_request_id = 0
        self._programme_request_pending = False
        self._programme_epg_refresh = EpgRefreshState()
        self._programme_last_html = None
        self._programme_timer = QTimer(self)
        self._programme_timer.setInterval(1000)
        self._programme_timer.timeout.connect(self._refresh_programme_information)
        self.btn_info   = QPushButton()
        self.btn_info.setEnabled(False)
        self.btn_info.setCheckable(True)
        self.btn_mute   = QPushButton()
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(self._volume)
        self.vol_slider.setFixedWidth(120)
        self.btn_audio  = QPushButton("Audio")
        self.btn_audio.setEnabled(False)
        self.audio_controls = QWidget()
        self.audio_controls.setObjectName("audioControls")
        self.btn_subs   = QPushButton("CC")
        self.btn_subs.setEnabled(False)
        self.btn_fs     = QPushButton()
        self.pl_pos     = QPushButton("")
        self.pl_pos.setFlat(True)
        self.pl_pos.setToolTip("Show/hide playlist (L)")
        self.pl_pos.setAccessibleName("Playlist position; show or hide playlist")
        self.pl_pos.clicked.connect(self.toggle_sidebar)
        self.btn_aspect_lock = QPushButton()
        self.btn_aspect_lock.setCheckable(True)
        self.btn_aspect_lock.setChecked(self._window_aspect_locked)
        self.btn_aspect_lock.setAccessibleName("Lock window proportions")
        self.btn_aspect_lock.setToolTip("Keep video proportions when resizing the window (K)")
        self.btn_aspect_lock.toggled.connect(self._toggle_window_aspect_lock)
        self.btn_format = QPushButton("Ratio")
        self.btn_format.setAccessibleName("Video aspect ratio")
        self.format_menu = QMenu(self.btn_format)
        self.format_actions = {}
        for label in VIDEO_ASPECT_RATIOS:
            action = self.format_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(label == self._video_format)
            action.triggered.connect(lambda _checked=False, value=label: self._select_video_format(value))
            self.format_actions[label] = action
        self.btn_format.clicked.connect(self._show_video_format_menu)
        self.btn_format.setToolTip(f"Video format: {self._video_format} (R cycles formats)")

        for b in (self.btn_prev, self.btn_rewind, self.btn_play, self.btn_ffwd,
                  self.btn_next, self.btn_slow, self.btn_fast, self.btn_info, self.btn_programme,
                  self.btn_mute, self.btn_audio, self.btn_subs, self.btn_fs,
                  self.btn_sidebar, self.btn_format, self.btn_aspect_lock, self.pl_pos):
            b.setFixedHeight(26)
            b.setIconSize(QSize(16, 16))
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)

        # Give icon-only buttons identical geometry regardless of native icon hints.
        for button in (self.btn_prev, self.btn_rewind, self.btn_play, self.btn_ffwd,
                       self.btn_next, self.btn_slow, self.btn_fast, self.btn_info, self.btn_programme,
                       self.btn_mute, self.btn_fs, self.btn_sidebar, self.btn_aspect_lock):
            button.setFixedSize(34, 26)

        self.btn_prev.setToolTip("Previous (Page Up)")
        self.btn_rewind.setToolTip("Rewind (Left arrow)")
        self.btn_play.setToolTip("Play / Pause (Space)")
        self.btn_ffwd.setToolTip("Forward (Right arrow)")
        self.btn_next.setToolTip("Next (Page Down)")
        self.btn_slow.setToolTip("Slower (-)")
        self.btn_fast.setToolTip("Faster (+)")
        self.rate_label.setToolTip("Change playback speed with the mouse wheel")
        self.btn_info.setToolTip("Stream information (I)")
        self.btn_mute.setToolTip("Mute (M)")
        self.btn_audio.setToolTip("Select audio track (A cycles tracks)")
        self.btn_subs.setToolTip("Subtitles (S)")
        self.btn_fs.setToolTip("Fullscreen (F)")

        self.btn_prev.clicked.connect(self.previous)
        self.btn_rewind.clicked.connect(lambda: self.seek_by(-self._seek_step_ms))
        self.btn_play.clicked.connect(self.toggle_play_pause)
        self.btn_ffwd.clicked.connect(lambda: self.seek_by(self._seek_step_ms))
        self.btn_next.clicked.connect(self.next)
        self.btn_slow.clicked.connect(lambda: self._adjust_rate(-self._speed_step))
        self.btn_fast.clicked.connect(lambda: self._adjust_rate(self._speed_step))
        self.btn_info.clicked.connect(self._toggle_stream_information)
        self.btn_mute.clicked.connect(self.toggle_mute)
        self.vol_slider.valueChanged.connect(self.set_volume)
        self.btn_audio.clicked.connect(self._show_audio_menu)
        self.btn_subs.clicked.connect(self._show_subs_menu)
        self.btn_fs.clicked.connect(self.toggle_fullscreen)

        seek_row = QHBoxLayout()
        seek_row.setContentsMargins(10, 2, 10, 0)
        seek_row.addWidget(self.seek_slider, 1)
        seek_row.addSpacing(8)
        seek_row.addWidget(self.time_label)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(10, 0, 10, 4)
        btn_row.setSpacing(4)
        btn_row.addWidget(self.btn_prev)
        btn_row.addWidget(self.btn_rewind)
        btn_row.addWidget(self.btn_play)
        btn_row.addWidget(self.btn_ffwd)
        btn_row.addWidget(self.btn_next)
        btn_row.addSpacing(12)
        rate_layout = QHBoxLayout(self.rate_controls)
        rate_layout.setContentsMargins(0, 0, 0, 0)
        rate_layout.setSpacing(4)
        rate_layout.addWidget(self.btn_slow)
        rate_layout.addWidget(self.rate_label)
        rate_layout.addWidget(self.btn_fast)
        self.rate_controls.setCursor(Qt.PointingHandCursor)
        btn_row.addWidget(self.rate_controls)
        btn_row.addStretch(1)
        btn_row.addWidget(self.pl_pos)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_programme)
        btn_row.addWidget(self.btn_info)
        btn_row.addSpacing(20)

        audio_layout = QHBoxLayout(self.audio_controls)
        audio_layout.setContentsMargins(0, 0, 0, 0)
        audio_layout.setSpacing(4)
        audio_layout.addWidget(self.btn_mute)
        audio_layout.addWidget(self.vol_slider)
        audio_layout.addSpacing(4)
        audio_layout.addWidget(self.btn_audio)
        btn_row.addWidget(self.audio_controls)
        btn_row.addWidget(self.btn_subs)
        btn_row.addWidget(self.btn_format)
        btn_row.addWidget(self.btn_aspect_lock)
        btn_row.addWidget(self.btn_fs)

        overlay_lay = QVBoxLayout(self.overlay)
        overlay_lay.setContentsMargins(0, 0, 0, 0)
        overlay_lay.setSpacing(0)
        overlay_lay.addLayout(seek_row)
        overlay_lay.addLayout(btn_row)

        # Cursor policy: the controls and top bar always show the normal arrow,
        # the video frame is the only thing that ever shows the blank cursor.
        # Buttons get PointingHandCursor (set per-button above).
        self.overlay.setCursor(Qt.ArrowCursor)
        self.top_bar.setCursor(Qt.ArrowCursor)
        self.vol_slider.setCursor(Qt.PointingHandCursor)

        # ---------- Sidebar (playlist) ----------
        self.sidebar = _PlaylistSidebar(self)
        self.sidebar.setObjectName("sidebarRoot")
        self._playlist_width_hint = 0
        self.sidebar.setCursor(Qt.ArrowCursor)
        self.sidebar.hide()

        self.sidebar_search = QLineEdit()
        self.sidebar_search.setObjectName("sidebarSearch")
        self.sidebar_search.setPlaceholderText("Filter…")
        self.sidebar_search.textChanged.connect(self._refresh_sidebar)

        self.playlist_list = KeyboardNavigableListWidget()
        self.playlist_list.setObjectName("playlistList")
        self.playlist_list.setCursor(Qt.PointingHandCursor)
        self.playlist_list.itemClicked.connect(self._playlist_item_activated)
        self.playlist_list.keyboardActivated.connect(self._playlist_item_activated)

        sidebar_lay = QVBoxLayout(self.sidebar)
        sidebar_lay.setContentsMargins(8, 8, 8, 8)
        sidebar_lay.setSpacing(6)
        sidebar_lay.addWidget(self.sidebar_search)
        sidebar_lay.addWidget(self.playlist_list, 1)

        # ---------- Compose ----------
        central = QWidget()
        central.setMouseTracking(True)
        central.installEventFilter(self)
        self._outer_layout = QVBoxLayout(central)
        self._outer_layout.setContentsMargins(0, 0, 0, 0)
        self._outer_layout.setSpacing(0)

        # In windowed mode every control has reserved layout space. This prevents
        # the controls from covering subtitles or any part of the video picture.
        self._content_widget = QWidget(central)
        self._content_layout = QHBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._content_layout.addWidget(self.sidebar)
        self._content_layout.addWidget(self.video_frame, 1)
        self._outer_layout.addWidget(self.top_bar)
        self._outer_layout.addWidget(self._content_widget, 1)
        self._outer_layout.addWidget(self.overlay)
        self.setCentralWidget(central)

        # Keyboard track changes use a short on-screen display instead of making
        # the user infer which audio or subtitle track is now active.
        self.track_osd = QLabel("", central)
        self.track_osd.setAlignment(Qt.AlignCenter)
        self.track_osd.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.track_osd.hide()
        self._track_osd_timer = QTimer(self)
        self._track_osd_timer.setSingleShot(True)
        self._track_osd_timer.timeout.connect(self._hide_track_osd)

        # A larger technical-information OSD stays separate from short seek,
        # volume, and track messages and is anchored to the video's top-right.
        self.stream_info_panel = QFrame(central)
        self.stream_info_panel.setObjectName("streamInfoPanel")
        stream_info_layout = QVBoxLayout(self.stream_info_panel)
        stream_info_layout.setContentsMargins(12, 10, 12, 10)
        stream_info_layout.setSpacing(6)
        stream_info_header = QHBoxLayout()
        self.stream_info_title = QLabel("Stream information")
        self.stream_info_title.setObjectName("streamInfoTitle")
        stream_info_header.addWidget(self.stream_info_title)
        stream_info_header.addStretch(1)
        stream_info_layout.addLayout(stream_info_header)
        self.stream_info_tree = QTreeWidget(self.stream_info_panel)
        self.stream_info_tree.setColumnCount(2)
        self.stream_info_tree.setHeaderLabels(("Property", "Value"))
        self.stream_info_tree.setRootIsDecorated(True)
        self.stream_info_tree.setAlternatingRowColors(True)
        self.stream_info_tree.header().setStretchLastSection(False)
        self.stream_info_tree.header().setSectionResizeMode(
            0, self.stream_info_tree.header().ResizeToContents
        )
        self.stream_info_tree.expanded.connect(self._reposition_stream_info_panel)
        self.stream_info_tree.collapsed.connect(self._reposition_stream_info_panel)
        stream_info_layout.addWidget(self.stream_info_tree, 1)
        self.programme_text = QTextBrowser(self.stream_info_panel)
        self.programme_text.setOpenExternalLinks(False)
        self.programme_text.setOpenLinks(False)
        self.programme_text.hide()
        stream_info_layout.addWidget(self.programme_text, 1)
        self.stream_info_panel.hide()
        self._info_layout_timer = QTimer(self)
        self._info_layout_timer.setSingleShot(True)
        self._info_layout_timer.timeout.connect(self._reposition_stream_info_panel)
        self.programme_text.document().documentLayout().documentSizeChanged.connect(
            self._information_content_resized)

        self._wheel_seek_timer = QTimer(self)
        self._wheel_seek_timer.setSingleShot(True)
        self._wheel_seek_timer.setInterval(1000)
        self._wheel_seek_timer.timeout.connect(self._commit_wheel_seek)

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

        # Native libVLC video surfaces can lag behind a Qt layout resize. Rebind
        # once resizing settles so the child surface receives the final geometry.
        self._video_resize_timer = QTimer(self)
        self._video_resize_timer.setSingleShot(True)
        self._video_resize_timer.timeout.connect(self._refresh_video_output_size)

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
        QShortcut(QKeySequence(Qt.Key_A),     self, activated=self._cycle_audio)
        QShortcut(QKeySequence(Qt.Key_S),     self, activated=self._cycle_subs)
        QShortcut(QKeySequence(Qt.Key_M),     self, activated=self.toggle_mute)
        QShortcut(QKeySequence(Qt.Key_I),     self, activated=self._toggle_stream_information_shortcut)
        # Route shortcuts through the buttons, preserving checked/disabled states.
        for key, action in ((Qt.Key_P, self.btn_programme.click),
                            (Qt.Key_R, self._cycle_video_format),
                            (Qt.Key_K, self.btn_aspect_lock.click)):
            shortcut = QShortcut(QKeySequence(key), self, activated=action)
            shortcut.setAutoRepeat(False)
        QShortcut(QKeySequence(Qt.Key_PageUp), self, activated=self.previous)
        QShortcut(QKeySequence(Qt.Key_PageDown), self, activated=self.next)
        QShortcut(QKeySequence(Qt.Key_Left),  self, activated=lambda: self.seek_by(-self._seek_step_ms))
        QShortcut(QKeySequence(Qt.Key_Right), self, activated=lambda: self.seek_by(self._seek_step_ms))
        QShortcut(QKeySequence(Qt.Key_Up),    self, activated=lambda: self._step_volume(self._volume_step))
        QShortcut(QKeySequence(Qt.Key_Down),  self, activated=lambda: self._step_volume(-self._volume_step))
        QShortcut(QKeySequence(Qt.Key_Minus), self, activated=lambda: self._adjust_rate(-self._speed_step))
        QShortcut(QKeySequence(Qt.Key_Plus),  self, activated=lambda: self._adjust_rate(self._speed_step))
        QShortcut(QKeySequence(Qt.Key_L),     self, activated=self.toggle_sidebar)
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self._exit_fullscreen_if_needed)

        self.set_control_steps(
            seek_step_seconds, volume_step_percent, speed_step
        )
        self.set_track_preferences(audio_language, subtitle_language)
        self._restore_window_geometry()
        self._aspect_controller = WindowAspectController(
            self, lambda: display_aspect_ratio(self._vlc, self.player, self._video_format),
            self._window_aspect_locked)
        self.apply_theme()
        self._wake_controls()

    # ---------- public API ----------
    def set_control_steps(self, seek_seconds, volume_percent, speed_step):
        """Apply bounded transport steps and refresh their user-facing hints."""
        try:
            self._seek_step_ms = max(1, min(int(seek_seconds), 300)) * 1000
        except (TypeError, ValueError):
            self._seek_step_ms = 10000
        try:
            self._volume_step = max(1, min(int(volume_percent), 25))
        except (TypeError, ValueError):
            self._volume_step = 2
        try:
            self._speed_step = max(0.05, min(float(speed_step), 1.0))
        except (TypeError, ValueError):
            self._speed_step = 0.25

        seek_seconds = self._seek_step_ms // 1000
        self.btn_rewind.setToolTip(f"Rewind {seek_seconds}s (Left arrow)")
        self.btn_ffwd.setToolTip(f"Forward {seek_seconds}s (Right arrow)")
        self.vol_slider.setToolTip(
            "Volume (Up/Down arrows or mouse wheel, "
            f"{self._volume_step}% steps)"
        )
        self.btn_slow.setToolTip(f"Slower by {self._speed_step:.2f}× (-)")
        self.btn_fast.setToolTip(f"Faster by {self._speed_step:.2f}× (+)")

    def set_track_preferences(self, audio_language, subtitle_language):
        """Store ISO 639 preferences that VLC will apply to newly opened media."""
        self._audio_language = str(audio_language or "").strip().lower()
        self._subtitle_language = str(subtitle_language or "").strip().lower()

    def _tinted_icon(self, source_icon, extent=72):
        """Tint an icon so it remains visible on the active theme."""
        source = source_icon.pixmap(96, 96)
        # Native icons have different transparent margins. Normalize their visible
        # bounds before tinting so mute, transport and fullscreen look consistent.
        image = source.toImage()
        pixels = [(x, y) for y in range(image.height()) for x in range(image.width())
                  if image.pixelColor(x, y).alpha()]
        if pixels:
            left = min(x for x, y in pixels)
            top = min(y for x, y in pixels)
            width = max(x for x, y in pixels) - left + 1
            height = max(y for x, y in pixels) - top + 1
            glyph = source.copy(left, top, width, height).scaled(
                extent, extent, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            glyph.setDevicePixelRatio(1)
            source = QPixmap(96, 96)
            source.fill(Qt.transparent)
            painter = QPainter(source)
            painter.drawPixmap((96 - glyph.width()) // 2, (96 - glyph.height()) // 2, glyph)
            painter.end()

        def tinted_pixmap(color):
            pixmap = QPixmap(source.size())
            pixmap.setDevicePixelRatio(source.devicePixelRatio())
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.drawPixmap(0, 0, source)
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(pixmap.rect(), color)
            painter.end()
            return pixmap

        icon = QIcon()
        icon.addPixmap(tinted_pixmap(self._icon_color), QIcon.Normal)
        icon.addPixmap(tinted_pixmap(self._disabled_icon_color), QIcon.Disabled)
        return icon

    def _tinted_standard_icon(self, standard_pixmap):
        """Tint a Qt standard icon so it remains visible on the active theme."""
        return self._tinted_icon(self.style().standardIcon(standard_pixmap))

    @staticmethod
    def _player_window_icon():
        """Create a compact player icon that remains clear in the native caption."""
        pixmap = QPixmap(96, 96)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#7c3aed"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(8, 8, 80, 80, 20, 20)
        painter.setBrush(Qt.white)
        painter.drawPolygon(QPolygon([
            QPoint(36, 28), QPoint(36, 68), QPoint(68, 48)
        ]))
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def _menu_icon(color):
        """Draw a crisp menu symbol without relying on a platform glyph font."""
        pixmap = QPixmap(96, 96)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(color, 8, Qt.SolidLine, Qt.RoundCap))
        for y in (28, 48, 68):
            painter.drawLine(24, y, 72, y)
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def _information_icon(color):
        """Draw a scalable outlined information symbol for the player."""
        pixmap = QPixmap(96, 96)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(color, 7, Qt.SolidLine, Qt.RoundCap))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(10, 10, 76, 76)
        painter.drawPoint(48, 31)
        painter.drawLine(48, 44, 48, 67)
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def _programme_icon(color):
        """Draw an outlined synopsis page with the same weight as the Info icon."""
        pixmap = QPixmap(96, 96)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(color, 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        painter.drawPolygon(QPolygon([QPoint(22, 12), QPoint(58, 12), QPoint(74, 28),
                                      QPoint(74, 84), QPoint(22, 84)]))
        painter.drawLine(58, 12, 58, 28)
        painter.drawLine(58, 28, 74, 28)
        for y in (43, 56, 69):
            painter.drawLine(34, y, 62, y)
        painter.end()
        return QIcon(pixmap)

    def _set_standard_icon(self, button, standard_pixmap):
        button.setIcon(self._tinted_standard_icon(standard_pixmap))

    @staticmethod
    def _aspect_lock_icon(color, locked):
        """Draw a scalable lock, matching the information icon's visual weight."""
        pixmap = QPixmap(96, 96)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(color, 7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(24, 43, 48, 39, 4, 4)
        painter.drawArc(QRect(33 if locked else 49, 12, 32, 48), 0, 180 * 16)
        painter.drawLine(33 if locked else 49, 36, 33 if locked else 49, 43)
        if locked:
            painter.drawLine(65, 36, 65, 43)
        painter.drawLine(48, 58, 48, 68)
        painter.end()
        return QIcon(pixmap)

    def _update_window_aspect_lock_button(self):
        self.btn_aspect_lock.setIcon(self._tinted_icon(
            self._aspect_lock_icon(self._icon_color, self._window_aspect_locked)))
        inactive = self._is_fullscreen or self.isMaximized()
        self.btn_aspect_lock.setEnabled(not inactive)
        self.btn_aspect_lock.setToolTip(
            ("Window proportions lock is inactive in fullscreen or maximized mode" if inactive
             else "Unlock window proportions" if self._window_aspect_locked
             else "Lock window proportions to the video format") + " (K)")

    def _toggle_window_aspect_lock(self, enabled):
        self._window_aspect_locked = bool(enabled)
        self._update_window_aspect_lock_button()
        controller = getattr(self, '_aspect_controller', None)
        if controller is not None:
            controller.set_enabled(enabled)
        try:
            save_window_aspect_lock(self._settings_path(), enabled)
        except (OSError, configparser.Error, UnicodeDecodeError):
            logging.warning("Could not save window aspect lock")
        self._wake_controls()

    def _spin_indicator_icon(self, primitive):
        """Use Qt's native plus/minus primitives rather than font-dependent glyphs."""
        pixmap = QPixmap(96, 96)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.scale(6, 6)
        option = QStyleOption()
        option.initFrom(self)
        option.rect = QRect(0, 0, 16, 16)
        option.state |= QStyle.State_Enabled
        self.style().drawPrimitive(primitive, option, painter, self)
        painter.end()
        # Use a slightly smaller symbol to match the transport icons' visual weight.
        return self._tinted_icon(QIcon(pixmap), extent=60)

    def _refresh_standard_icons(self):
        """Reload native icons after a palette or playback-state change."""
        self._set_standard_icon(self.btn_prev, QStyle.SP_MediaSkipBackward)
        self._set_standard_icon(self.btn_rewind, QStyle.SP_MediaSeekBackward)
        play_icon = QStyle.SP_MediaPause if self.player.is_playing() else QStyle.SP_MediaPlay
        self._set_standard_icon(self.btn_play, play_icon)
        self._set_standard_icon(self.btn_ffwd, QStyle.SP_MediaSeekForward)
        self._set_standard_icon(self.btn_next, QStyle.SP_MediaSkipForward)
        self.btn_slow.setIcon(self._spin_indicator_icon(QStyle.PE_IndicatorSpinMinus))
        self.btn_fast.setIcon(self._spin_indicator_icon(QStyle.PE_IndicatorSpinPlus))
        muted = self._muted or self._volume == 0
        volume_icon = QStyle.SP_MediaVolumeMuted if muted else QStyle.SP_MediaVolume
        self._set_standard_icon(self.btn_mute, volume_icon)
        self.btn_info.setIcon(self._tinted_icon(self._information_icon(self._icon_color)))
        self.btn_programme.setIcon(self._tinted_icon(
            self._programme_icon(self._icon_color)))
        self._update_window_aspect_lock_button()
        fullscreen_icon = (
            QStyle.SP_TitleBarNormalButton
            if self._is_fullscreen else QStyle.SP_TitleBarMaxButton
        )
        self._set_standard_icon(self.btn_fs, fullscreen_icon)

    def apply_theme(self):
        """Match custom player chrome to the active Qt application palette."""
        background = QApplication.instance().palette().color(QPalette.Window)
        luminance = (
            0.299 * background.red()
            + 0.587 * background.green()
            + 0.114 * background.blue()
        )
        dark = luminance < 128
        self._icon_color = QColor("#f2f2f2" if dark else "#202020")
        self._disabled_icon_color = QColor("#707075" if dark else "#a0a0a0")
        self.btn_sidebar.setIcon(self._menu_icon(self._icon_color))
        button_style = DARK_BUTTON_STYLE if dark else LIGHT_BUTTON_STYLE
        overlay_style = DARK_OVERLAY_STYLE if dark else LIGHT_OVERLAY_STYLE
        sidebar_style = DARK_SIDEBAR_STYLE if dark else LIGHT_SIDEBAR_STYLE
        label_color = "#ccc" if dark else "#303030"

        for button in (
            self.btn_prev, self.btn_rewind, self.btn_play, self.btn_ffwd,
            self.btn_next, self.btn_slow, self.btn_fast, self.btn_info, self.btn_programme,
            self.btn_mute, self.btn_audio, self.btn_subs, self.btn_fs,
            self.btn_sidebar, self.btn_format, self.btn_aspect_lock
        ):
            button.setStyleSheet(button_style)
        self.overlay.setStyleSheet(overlay_style)
        self.top_bar.setStyleSheet(overlay_style)
        self.sidebar.setStyleSheet(sidebar_style)
        self.rate_label.setStyleSheet(f"color: {label_color}; padding: 0 8px;")
        self.pl_pos.setStyleSheet(f"QPushButton {{ color: {label_color}; padding: 2px 6px; border: none; background: transparent; }} QPushButton:hover {{ background: palette(midlight); border-radius: 4px; }}")
        osd_background = "rgba(20,20,22,220)" if dark else "rgba(248,248,248,235)"
        self.track_osd.setStyleSheet(
            f"background: {osd_background}; color: {label_color}; "
            "border: 1px solid palette(mid); border-radius: 0; "
            "padding: 8px 14px; font-size: 13px; font-weight: bold;"
        )
        panel_background = (
            "rgba(20,20,22,235)" if dark else "rgba(248,248,248,245)"
        )
        panel_border = "#555" if dark else "#aaa"
        self.stream_info_panel.setStyleSheet(
            f"QFrame#streamInfoPanel {{ background: {panel_background}; "
            f"color: {label_color}; border: 1px solid {panel_border}; "
            "border-radius: 0; }"
            "QLabel#streamInfoTitle { border: none; font-weight: bold; "
            "font-size: 14px; }"
            "QTreeWidget, QTextBrowser { background: transparent; border: none; }"
            "QHeaderView::section { background: transparent; border: none; "
            "padding: 4px; font-weight: bold; }"
        )
        self._apply_native_title_bar_theme(dark)
        self._refresh_standard_icons()
        self._info_layout_timer.start(0)

    def _apply_native_title_bar_theme(self, dark):
        """Ask Windows to draw this native title bar using the active theme."""
        if not sys.platform.startswith("win"):
            return
        try:
            import ctypes
            enabled = ctypes.c_int(1 if dark else 0)
            hwnd = int(self.winId())
            # Attribute 20 is current; 19 supports older Windows 10 builds.
            for attribute in (20, 19):
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(enabled), ctypes.sizeof(enabled)
                )
                if result == 0:
                    break

            # Match the player's own header rather than the generic application
            # background so the native and Qt title areas form one visual strip.
            caption = QColor(20, 20, 22) if dark else QColor(245, 245, 245)
            caption_color = ctypes.c_uint(
                caption.red() | (caption.green() << 8) | (caption.blue() << 16)
            )
            text = QColor(242, 242, 242) if dark else QColor(32, 32, 32)
            text_color = ctypes.c_uint(
                text.red() | (text.green() << 8) | (text.blue() << 16)
            )
            for attribute, color in ((35, caption_color), (36, text_color)):
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(color), ctypes.sizeof(color)
                )
        except Exception:
            pass

    @staticmethod
    def availability():
        """Return whether libVLC loads and a meaningful failure explanation."""
        try:
            configure_linux_vlc_plugins()
            import vlc
            logging.debug("Internal VLC runtime: version=%r; library=%r; frozen=%s",
                          vlc.libvlc_get_version(), getattr(vlc.dll, '_name', None),
                          getattr(sys, 'frozen', False))
            instance = vlc.Instance()
            if instance is None:
                raise RuntimeError("libVLC did not create an instance")
            instance.release()
            return True, ""
        except (Exception, SystemExit) as error:
            logging.exception("Internal VLC initialization failed (frozen=%s)",
                              getattr(sys, 'frozen', False))
            return False, describe_vlc_load_failure(error)

    @staticmethod
    def is_available():
        available, _reason = EmbeddedPlayerWindow.availability()
        return available

    def set_user_agent(self, user_agent):
        """Apply the selected account header to subsequent media, including auto-next."""
        self._user_agent = str(user_agent or "").strip()

    def play_url(
        self, url, title="", playlist=None, index=0, resume_ms=0,
        keep_above_main=False
    ):
        was_visible = self.isVisible()
        self._current_url = url
        controller = getattr(self, "_aspect_controller", None)
        if controller is not None:
            controller.reset_media()
        self._pause_started_at = None
        self._paused_by_minimize = False
        self._recovering_after_pause = False
        self._pause_recovery_failed = False
        self._wheel_seek_timer.stop()
        self._track_osd_timer.stop()
        self._hide_track_osd()
        programme_open = self.btn_programme.isChecked()
        self._hide_stream_information()
        self._programme_payload = None
        self._programme_epg_refresh = EpgRefreshState()
        self._programme_request_pending = False
        self._programme_last_html = None
        self._report_progress(force=True)
        if playlist is not None:
            self._playlist = list(playlist)
            self._current_idx = max(0, min(index, len(self._playlist) - 1)) if self._playlist else 0
            self._refresh_sidebar()
        elif not self._playlist:
            # Single-item playlist so next/prev are gracefully disabled.
            self._playlist = [{'name': title or url, 'url': url}]
            self._current_idx = 0

        title = title or (self._playlist[self._current_idx].get('name') if self._playlist else url)
        # Keep the native title concise; the complete media title is shown below it.
        self.setWindowTitle("Internal Player")
        self.title_label.setText(title)

        media = self.instance.media_new(url)
        if self._user_agent:
            media.add_option(f":http-user-agent={self._user_agent}")
        self._current_stream_protocol = urlsplit(str(url)).scheme.upper()
        self.btn_info.setEnabled(True)
        self.btn_programme.setEnabled(True)
        media.add_option(f":network-caching={self._network_caching_ms}")
        # VLC accepts ISO 639 language codes as per-media options. Leaving a
        # preference empty preserves VLC's own default track-selection policy.
        if self._audio_language:
            media.add_option(f":audio-language={self._audio_language}")
        if self._subtitle_language == "disabled":
            media.add_option(":no-spu")
        elif self._subtitle_language:
            media.add_option(f":sub-language={self._subtitle_language}")
        if resume_ms:
            # Ask VLC to begin at the saved position before it decodes the first
            # visible frame. The polling seek below remains a precision fallback.
            media.add_option(f":start-time={max(0, int(resume_ms)) / 1000:.3f}")
        self.player.set_media(media)
        self._apply_video_format()
        self._media_generation += 1
        self._current_history = (
            dict(self._playlist[self._current_idx].get("history") or {})
            if self._playlist else None
        )
        self._update_playback_rate_controls()
        self._pending_playback_rate_attempts = 20
        self._auto_advance_triggered = False
        self._pending_resume_ms = max(0, int(resume_ms or 0))
        self._pending_resume_attempts = 20 if self._pending_resume_ms else 0
        # Hide a new window until its initial resume seek completes. Playlist
        # navigation reuses the visible window and must never make it disappear.
        self._deferred_present = bool(self._pending_resume_ms) and not was_visible
        self._deferred_present_polls = 12 if self._deferred_present else 0
        self._deferred_keep_topmost = bool(keep_above_main)
        if not sys.platform.startswith("win"):
            # Use Qt's portable window-manager hint on macOS and Linux. The
            # player remains an independent top-level window.
            self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(keep_above_main))
        if self._deferred_present:
            self.hide()
        self._bind_video_output()
        self.player.play()
        if not self._deferred_present and not was_visible:
            self._present_player(keep_above_main)
        self._last_progress_report = 0.0
        self._set_standard_icon(self.btn_play, QStyle.SP_MediaPause)
        self._update_pl_pos()
        self._wake_controls()
        if self._current_history and self._progress_callback is not None:
            try:
                self._progress_callback({'event': 'playback_started',
                                         'history': dict(self._current_history)})
            except (EOFError, OSError):
                pass

        if programme_open:
            self._toggle_programme_information(True)

    # ---------- video output binding ----------
    def _bind_video_output(self):
        # Always bind before playback. Closing this reusable window can make Qt
        # recreate the native video handle; retaining the previous binding sent
        # decoded video to a stale HWND and produced audio with a black picture.
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

    def _bring_to_front(self, keep_topmost=False):
        """Present the isolated player above the main window without keeping it topmost."""
        if sys.platform.startswith("win"):
            try:
                import ctypes

                hwnd = int(self.winId())
                user32 = ctypes.windll.user32
                # Mark the hidden native window topmost before Qt displays it so
                # there is no single frame underneath the main window.
                flags = 0x0001 | 0x0002  # NOSIZE | NOMOVE
                user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, flags)
            except Exception:
                pass
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if sys.platform.startswith("win"):
            try:
                ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
                if not keep_topmost:
                    QTimer.singleShot(500, self._release_temporary_topmost)
            except Exception:
                pass

    def _present_player(self, keep_topmost=False):
        """Show a prepared player and request foreground activation from its parent."""
        self._deferred_present = False
        set_macos_activation_policy(True)
        self._bring_to_front(keep_topmost=keep_topmost)
        # Apply native caption colors after the final HWND becomes visible.
        self.apply_theme()
        if self._progress_callback is None:
            return
        try:
            self._progress_callback({
                "event": "player_window_ready",
                "window_id": int(self.winId()),
                "keep_topmost": bool(keep_topmost),
            })
        except (EOFError, OSError, TypeError, ValueError):
            pass

    def _release_temporary_topmost(self):
        """Return the player to normal stacking after Windows has presented it."""
        if not sys.platform.startswith("win") or not self.isVisible():
            return
        try:
            import ctypes

            hwnd = int(self.winId())
            flags = 0x0001 | 0x0002 | 0x0040  # NOSIZE | NOMOVE | SHOWWINDOW
            ctypes.windll.user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, flags)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def _refresh_video_output_size(self):
        """Synchronize libVLC's native child surface with the final Qt geometry."""
        if not self.isVisible():
            return
        try:
            self.video_frame.updateGeometry()
            self._bind_video_output()
            self.player.video_set_scale(0)
        except Exception:
            pass

    # ---------- transport ----------
    def _pause_playback(self):
        """Remember a VOD pause before VLC can lose the connection or timestamp."""
        self._recovering_after_pause = False
        if not self._is_live_playback():
            self._pause_started_at = time.monotonic()
            self._pause_position_ms = max(0, int(self.player.get_time()))
            self._store_current_playlist_progress()
        self.player.pause()
        self._set_standard_icon(self.btn_play, QStyle.SP_MediaPlay)

    def _resume_playback(self):
        """Reopen VOD after a prolonged pause without asking the resume question."""
        if self._recovering_after_pause:
            return
        started = self._pause_started_at
        pause_seconds = max(0.0, time.monotonic() - started) if started is not None else 0.0
        recover = (
            not self._is_live_playback()
            and started is not None
            and pause_seconds >= VOD_PAUSE_RECONNECT_SECONDS
            and bool(self._current_url)
        )
        if started is not None:
            logging.debug("VOD resume after %.1f seconds paused; reconnect=%s", pause_seconds, recover)
        if recover:
            position = self._pause_position_ms
            url = self._current_url
            # Block both end-event navigation and credits skipping while replacing
            # the input. play_url bypasses the interactive playlist resume prompt.
            self._recovering_after_pause = True
            self.player.stop()
            try:
                self.play_url(url, self.title_label.text(), resume_ms=position,
                              keep_above_main=self._deferred_keep_topmost)
            except Exception:
                self._recovering_after_pause = True
                self._fail_pause_recovery()
                return
            self._recovering_after_pause = True
            self._pause_recovery_target_ms = position
            self._pause_recovery_deadline = time.monotonic() + 30.0
            logging.debug("Reopening paused VOD at %d ms", position)
        else:
            self._pause_started_at = None
            self.player.play()
        self._set_standard_icon(self.btn_play, QStyle.SP_MediaPause)

    def _check_pause_recovery(self, position_ms):
        """Unblock navigation only after playback reaches the saved position."""
        if not self._recovering_after_pause:
            return
        target = self._pause_recovery_target_ms
        if self.player.is_playing() and abs(position_ms - target) <= 500:
            self._recovering_after_pause = False
            self._pending_resume_ms = 0
            self._pending_resume_attempts = 0
            logging.debug("Paused VOD successfully resumed")
        elif time.monotonic() >= self._pause_recovery_deadline:
            self._fail_pause_recovery()

    def _fail_pause_recovery(self):
        """Keep the current episode selected after a bounded, unsuccessful retry."""
        self._pause_recovery_failed = True
        self._recovering_after_pause = False
        self._pending_resume_ms = 0
        self._pending_resume_attempts = 0
        self._pause_started_at = time.monotonic() - VOD_PAUSE_RECONNECT_SECONDS
        self.player.stop()
        self._set_standard_icon(self.btn_play, QStyle.SP_MediaPlay)
        self._show_track_osd("Could not resume playback. Press Play to retry.")
        logging.warning("Could not restore paused VOD playback position")

    def toggle_play_pause(self):
        if self.player.is_playing():
            self._pause_playback()
        else:
            self._resume_playback()
        self._wake_controls()

    def stop(self):
        self._pause_started_at = None
        self._recovering_after_pause = False
        self._pause_recovery_failed = False
        self.player.stop()
        self._set_standard_icon(self.btn_play, QStyle.SP_MediaPlay)

    def seek_by(self, ms):
        if self._wheel_seek_timer.isActive():
            self._commit_wheel_seek()
        cur = self.player.get_time()
        if cur < 0:
            return
        if self._track_osd_timer.isActive() and self._seek_osd_active:
            new = self._seek_target_ms + ms
        else:
            self._seek_sequence_origin_ms = cur
            new = cur + ms
        length = self.player.get_length()
        new = max(0, min(new, length if length > 0 else new))
        self._seek_target_ms = new
        self._seek_osd_total_ms = new - self._seek_sequence_origin_ms
        self.player.set_time(int(new))
        seconds = abs(self._seek_osd_total_ms) / 1000
        amount = f"{seconds:g}"
        direction = "+" if self._seek_osd_total_ms >= 0 else "−"
        unit = "second" if seconds == 1 else "seconds"
        self._show_track_osd(
            f"{direction}{amount} {unit}\n{self._fmt_ms(new)}",
            seek=True,
        )
        self._wake_controls()

    def preview_wheel_seek(self, ms):
        """Accumulate wheel steps and apply the target after a short idle delay."""
        if self._wheel_seek_timer.isActive():
            new = self._seek_target_ms + ms
        else:
            current = self.player.get_time()
            if current < 0:
                return
            self._seek_sequence_origin_ms = current
            new = current + ms
        length = self.player.get_length()
        new = max(0, min(new, length if length > 0 else new))
        self._seek_target_ms = new
        self._seek_osd_total_ms = new - self._seek_sequence_origin_ms
        if length > 0:
            self.seek_slider.setValue(int(new / length * 1000))

        seconds = abs(self._seek_osd_total_ms) / 1000
        direction = "+" if self._seek_osd_total_ms >= 0 else "−"
        unit = "second" if seconds == 1 else "seconds"
        self._show_track_osd(
            f"{direction}{seconds:g} {unit}\n{self._fmt_ms(new)}",
            seek=True,
        )
        self._wheel_seek_timer.start()
        self._wake_controls()

    def _commit_wheel_seek(self):
        """Apply the last wheel preview after wheel input has stopped."""
        self._wheel_seek_timer.stop()
        if self._seek_target_ms >= 0:
            self.player.set_time(int(self._seek_target_ms))

    def set_volume(self, value):
        self._volume = int(value)
        # Moving the volume slider is an explicit request to hear that level.
        if self._muted:
            self._muted = False
            self.player.audio_set_mute(False)
        self.player.audio_set_volume(self._volume)
        if self._volume > 0:
            self._volume_before_mute = self._volume
        icon = QStyle.SP_MediaVolumeMuted if self._volume == 0 else QStyle.SP_MediaVolume
        self._set_standard_icon(self.btn_mute, icon)
        self._save_volume_pref()

    def _step_volume(self, delta):
        self.vol_slider.setValue(max(0, min(100, self._volume + delta)))
        self._show_track_osd(f"Volume: {self.vol_slider.value()}%")
        self._wake_controls()

    def toggle_mute(self):
        # libVLC may report -1 briefly after opening media. Track the requested
        # state locally so the icon and audio state change together immediately.
        self._muted = not self._muted
        if self._muted:
            if self._volume > 0:
                self._volume_before_mute = self._volume
            self.player.audio_set_mute(True)
            self.vol_slider.blockSignals(True)
            self.vol_slider.setValue(0)
            self.vol_slider.blockSignals(False)
        else:
            if self._volume <= 0:
                self._volume = self._volume_before_mute
            self.player.audio_set_volume(self._volume)
            self.player.audio_set_mute(False)
            self.vol_slider.blockSignals(True)
            self.vol_slider.setValue(self._volume)
            self.vol_slider.blockSignals(False)
        icon = QStyle.SP_MediaVolumeMuted if self._muted else QStyle.SP_MediaVolume
        self._set_standard_icon(self.btn_mute, icon)
        self._wake_controls()

    def _adjust_rate(self, delta):
        if self._is_live_playback():
            self.player.set_rate(1.0)
            self.rate_label.setText("1.00x")
            self._wake_controls()
            return
        self._playback_rate = max(
            0.25, min(4.0, round(self._playback_rate + delta, 2))
        )
        self.player.set_rate(self._playback_rate)
        self.rate_label.setText(f"{self._playback_rate:.2f}x")
        self._show_track_osd(f"Speed: {self._playback_rate:.2f}×")
        self._save_playback_rate_pref()
        self._wake_controls()

    # ---------- next / previous ----------
    def next(self):
        if self._current_idx + 1 >= len(self._playlist):
            return
        self._store_current_playlist_progress()
        self._current_idx += 1
        self._play_current()

    def previous(self):
        if self._current_idx <= 0:
            return
        self._store_current_playlist_progress()
        self._current_idx -= 1
        self._play_current()

    def _on_media_ended(self, _event):
        """Move VLC's native end event onto the Qt GUI thread."""
        self.media_ended.emit(self._media_generation)

    def _advance_after_media_end(self, media_generation):
        """Start the next item after on-demand playback finishes naturally."""
        if media_generation != self._media_generation:
            return
        if _pause_blocks_navigation(self):
            return
        if not self._auto_play_next or self._auto_advance_triggered:
            return
        if not self.isVisible():
            return
        if (self._current_history or {}).get("type") == "LIVE":
            return
        self._auto_advance_triggered = True
        self.next()

    def set_auto_advance(self, enabled, seconds, network_caching_ms=None):
        """Update sequential playback and buffering preferences."""
        self._auto_play_next = bool(enabled)
        self._auto_advance_seconds = max(0, min(int(seconds), 300))
        if network_caching_ms is not None:
            self._network_caching_ms = max(
                0, min(int(network_caching_ms), 60000)
            )

    def _store_current_playlist_progress(self):
        """Refresh the local playlist copy before navigating to another item."""
        self._report_progress(force=True)
        if (
            self._current_history
            and 0 <= self._current_idx < len(self._playlist)
        ):
            self._playlist[self._current_idx]["history"] = dict(
                self._current_history
            )

    def _play_current(self):
        if not self._playlist:
            return
        entry = self._playlist[self._current_idx]
        url = entry.get('url')
        if not url:
            # Skip ahead if the entry has no playable URL (e.g. series-level item).
            return
        resume_ms = self._resume_for_playlist_entry(entry)
        if resume_ms is None:
            return
        self.play_url(
            url,
            title=entry.get('name', ''),
            playlist=self._playlist,
            index=self._current_idx,
            resume_ms=resume_ms,
        )

    def set_resume_behavior(self, behavior):
        """Update how previously started playlist entries are handled."""
        self._resume_behavior = (
            behavior if behavior in RESUME_BEHAVIORS else DEFAULT_RESUME_BEHAVIOR
        )

    def _resume_for_playlist_entry(self, entry):
        """Choose a resume position when navigating inside the player playlist."""
        history = entry.get("history") or {}
        position_ms = resume_position(history)
        if not position_ms or self._resume_behavior == "restart":
            return 0
        if self._resume_behavior == "resume":
            return position_ms
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Question)
        dialog.setWindowTitle("Resume playback")
        dialog.setText(
            f"Resume '{entry.get('name', '')}' from {self._fmt_ms(position_ms)}?"
        )
        dialog.setStandardButtons(
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
        )
        dialog.setDefaultButton(QMessageBox.Yes)
        dialog.setPalette(QApplication.instance().palette())
        apply_windows_title_bar_theme(
            dialog,
            application_palette_is_dark(QApplication.instance()),
        )
        answer = dialog.exec_()
        if answer == QMessageBox.Cancel:
            return None
        return position_ms if answer == QMessageBox.Yes else 0

    def _apply_video_format(self):
        """Use VLC's display-ratio override; an empty value restores stream defaults."""
        try:
            self.player.video_set_aspect_ratio(VIDEO_ASPECT_RATIOS[self._video_format])
            return True
        except (AttributeError, OSError, ValueError):
            logging.warning("Could not apply video aspect ratio")
            return False

    def _show_selection_menu(self, menu, button):
        """Use the same popup placement and dismissal state for all selectors."""
        self._wake_controls()
        try:
            menu.exec_(button.mapToGlobal(button.rect().bottomLeft()))
        finally:
            button.setDown(False)
            button.clearFocus()
            button.update()

    def _show_video_format_menu(self):
        """Show every format and mark the current choice, like Audio and CC."""
        self._show_selection_menu(self.format_menu, self.btn_format)

    def _cycle_video_format(self):
        """Select the next format through the shared persistent selection path."""
        formats = list(VIDEO_ASPECT_RATIOS)
        next_index = (formats.index(self._video_format) + 1) % len(formats)
        self._select_video_format(formats[next_index])

    def _update_video_format_actions(self):
        """Keep one checked box without Qt's exclusive-group radio indicator."""
        for label, action in self.format_actions.items():
            action.setChecked(label == self._video_format)

    def _select_video_format(self, value):
        """Apply and remember a toolbar choice without reopening the current media."""
        if value not in VIDEO_ASPECT_RATIOS:
            return
        previous = self._video_format
        self._video_format = value
        if not self._apply_video_format():
            self._video_format = previous
            self._update_video_format_actions()
            self._show_track_osd("Could not change video format")
            return
        self._update_video_format_actions()
        self.btn_format.setToolTip(f"Video format: {value} (R cycles formats)")
        try:
            save_video_format(self._settings_path(), value)
        except (OSError, configparser.Error, UnicodeDecodeError):
            logging.warning("Could not save video format preference")
        controller = getattr(self, '_aspect_controller', None)
        if controller is not None:
            controller.refresh_ratio()
        self._show_track_osd(f"Video format: {value}")
        self._wake_controls()

    def _update_pl_pos(self):
        n = len(self._playlist)
        self.pl_pos.setVisible(n > 1)
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

    # ---------- audio tracks ----------
    def _audio_tracks(self):
        """Return the audio tracks currently reported by libVLC."""
        try:
            descriptions = self.player.audio_get_track_description() or []
            return [
                (
                    int(track_id),
                    name.decode("utf-8", errors="replace")
                    if isinstance(name, bytes) else str(name)
                )
                for track_id, name in descriptions
            ]
        except Exception:
            return []

    def _update_audio_button(self):
        """Enable audio selection only when the media offers multiple tracks."""
        self.btn_audio.setEnabled(len(self._audio_tracks()) > 1)

    def _show_audio_menu(self):
        """Show every audio track and mark the one selected by libVLC."""
        tracks = self._audio_tracks()
        if not tracks:
            return
        menu = QMenu(self)
        try:
            current = self.player.audio_get_track()
        except Exception:
            current = -1
        for track_id, name in tracks:
            action = QAction(name, menu)
            action.setCheckable(True)
            action.setChecked(track_id == current)
            action.triggered.connect(
                lambda _, selected_id=track_id: self._select_audio_track(selected_id)
            )
            menu.addAction(action)
        self._show_selection_menu(menu, self.btn_audio)
        menu.deleteLater()

    def _select_audio_track(self, track_id):
        """Select one libVLC audio track from the popup menu."""
        self.player.audio_set_track(track_id)
        self._wake_controls()

    def _cycle_audio(self):
        """Select the next audio track and identify it on screen."""
        tracks = self._audio_tracks()
        if not tracks:
            self._show_track_osd("Audio: no track available")
            return
        track_ids = [track_id for track_id, _ in tracks]
        current = self.player.audio_get_track()
        try:
            next_index = (track_ids.index(current) + 1) % len(track_ids)
        except ValueError:
            next_index = 0
        track_id, name = tracks[next_index]
        self.player.audio_set_track(track_id)
        self._show_track_osd(f"Audio: {name}")
        self._wake_controls()

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
            act = QAction(name, menu)
            act.setCheckable(True)
            act.setChecked(tid == current)
            act.triggered.connect(lambda _, t=tid: self.player.video_set_spu(t))
            menu.addAction(act)
        self._show_selection_menu(menu, self.btn_subs)
        menu.deleteLater()

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
        selected_name = next(
            (name for track_id, name in tracks if track_id == nxt),
            "Unknown"
        )
        self._show_track_osd(f"Subtitles: {selected_name}")
        self._wake_controls()

    def _show_track_osd(self, text, seek=False):
        """Show a brief track-selection message over the video picture."""
        self._seek_osd_active = bool(seek)
        self.track_osd.setText(text)
        self.track_osd.adjustSize()
        self._reposition_track_osd()
        self.track_osd.show()
        self.track_osd.raise_()
        self._track_osd_timer.start(1800)

    def _hide_track_osd(self):
        """Hide the OSD and end any accumulated keyboard seek sequence."""
        self.track_osd.hide()
        self._seek_osd_active = False
        self._seek_osd_total_ms = 0
        self._seek_target_ms = 0
        self._seek_sequence_origin_ms = 0

    def _toggle_stream_information(self, checked):
        """Toggle the technical-information panel from the Info button."""
        if checked:
            self._show_stream_information()
        else:
            self._hide_stream_information()

    def _toggle_stream_information_shortcut(self):
        """Toggle technical stream information from the I shortcut."""
        self._toggle_stream_information(not self.btn_info.isChecked())

    def _show_stream_information(self):
        """Show technical details reported locally by libVLC."""
        self._programme_timer.stop()
        self.btn_programme.setChecked(False)
        self.programme_text.hide()
        self.stream_info_tree.show()
        self.stream_info_title.setText("Stream information")
        sections = collect_stream_information(
            self._vlc, self.player, self._current_stream_protocol
        )
        self.stream_info_tree.clear()
        for section_name, fields in sections:
            section_item = QTreeWidgetItem((section_name, ""))
            section_font = section_item.font(0)
            section_font.setBold(True)
            section_item.setFont(0, section_font)
            self.stream_info_tree.addTopLevelItem(section_item)
            section_item.setFirstColumnSpanned(True)
            for label, value in fields:
                section_item.addChild(QTreeWidgetItem((label, str(value))))
            section_item.setExpanded(True)
        self._reposition_stream_info_panel()
        self.stream_info_panel.show()
        self.stream_info_panel.raise_()
        self.btn_info.setChecked(True)
        self._info_layout_timer.start(0)
        self._wake_controls()

    def _hide_stream_information(self):
        """Hide the technical-information OSD."""
        self.stream_info_panel.hide()
        self.btn_info.setChecked(False)
        self.btn_programme.setChecked(False)
        self._programme_timer.stop()

    def _toggle_programme_information(self, checked):
        """Reuse the Info panel for provider descriptions, without touching playback."""
        if not checked:
            self._hide_stream_information()
            return
        self.btn_info.setChecked(False)
        self.btn_programme.setChecked(True)
        self.stream_info_tree.hide()
        self.programme_text.show()
        self.stream_info_title.setText("Programme information")
        self._reposition_stream_info_panel()
        self.stream_info_panel.show()
        self.stream_info_panel.raise_()
        self._programme_timer.start()
        self._info_layout_timer.start(0)
        if self._programme_payload is None or self._programme_payload.get("message"):
            self.programme_text.setPlainText("Loading programme information…")
            self._reposition_stream_info_panel()
            self._request_programme_information()
        else:
            self._refresh_programme_information()
        self._wake_controls()

    def _request_programme_information(self):
        if self._programme_request_pending:
            return
        if not self._current_history or self._progress_callback is None:
            self._programme_payload = {"message": "Programme information unavailable."}
            self._programme_epg_refresh.begin()
            self._programme_epg_refresh.received(self._programme_payload)
            self._refresh_programme_information()
            return
        self._programme_request_id = uuid.uuid4().hex
        self._programme_request_pending = True
        self._programme_epg_refresh.begin()
        try:
            self._progress_callback({"event": "programme_request",
                "generation": self._media_generation, "request_id": self._programme_request_id,
                "history": dict(self._current_history)})
        except (EOFError, OSError):
            self._programme_request_pending = False
            self._programme_payload = {"message": "Unable to load programme information."}
            self._programme_epg_refresh.received(self._programme_payload)

    def receive_programme_information(self, response):
        """Discard replies for an earlier stream or superseded request."""
        if (response.get("generation") != self._media_generation
                or response.get("request_id") != self._programme_request_id):
            return
        self._programme_request_pending = False
        payload = response.get("payload") or {}
        self._programme_epg_refresh.received(payload)
        if not payload.get('message') or self._programme_payload is None:
            self._programme_payload = payload
        self._refresh_programme_information()

    def _refresh_programme_information(self):
        if not self.btn_programme.isChecked():
            return
        if self._programme_payload is not None:
            markup = programme_html(self._programme_payload)
            if markup != self._programme_last_html:
                self.programme_text.setHtml(markup)
                self._programme_last_html = markup
                self._reposition_stream_info_panel()
                self._info_layout_timer.start(0)
        if (self._is_live_playback() and not self._programme_request_pending
                and self._programme_epg_refresh.due(self._programme_payload)):
            self._request_programme_information()

    # ---------- fullscreen ----------
    def toggle_fullscreen(self):
        if self._is_fullscreen:
            self.showNormal()
            self._is_fullscreen = False
            self._restore_windowed_layout()
        else:
            self._is_fullscreen = True
            self._use_fullscreen_overlays()
            self.showFullScreen()
        self._refresh_standard_icons()
        self._wake_controls()
        self._reposition_overlays()
        if not self._is_fullscreen:
            QTimer.singleShot(0, self._aspect_controller.apply)

    def _use_fullscreen_overlays(self):
        """Float player chrome over the video only while in fullscreen mode."""
        central = self.centralWidget()
        self._outer_layout.removeWidget(self.top_bar)
        self._outer_layout.removeWidget(self.overlay)
        self._content_layout.removeWidget(self.sidebar)
        self.top_bar.setParent(central)
        self.overlay.setParent(central)
        self.sidebar.setParent(central)
        self.top_bar.show()
        self.overlay.show()
        self.sidebar.setVisible(self._sidebar_visible)
        self.top_bar.raise_()
        self.overlay.raise_()
        self.sidebar.raise_()

    def _restore_windowed_layout(self):
        """Reserve permanent space for chrome so it cannot cover the picture."""
        self._hide_timer.stop()
        self.top_bar.hide()
        self.overlay.hide()
        self.sidebar.hide()
        self._outer_layout.insertWidget(0, self.top_bar)
        self._content_layout.insertWidget(0, self.sidebar)
        self._outer_layout.addWidget(self.overlay)
        self.top_bar.show()
        self.overlay.show()
        self.sidebar.setVisible(self._sidebar_visible)
        self.video_frame.unsetCursor()

    def _exit_fullscreen_if_needed(self):
        if self._is_fullscreen:
            self.toggle_fullscreen()

    # ---------- sidebar ----------
    def toggle_sidebar(self):
        self._sidebar_visible = not self._sidebar_visible
        self._aspect_controller.sidebar_changed()
        if self._sidebar_visible:
            self._refresh_sidebar()
            self.sidebar.show()
            if self._is_fullscreen:
                self.sidebar.raise_()
            self._reposition_overlays()
        else:
            self.sidebar.hide()
            # Closing the sidebar returns to normal overlay auto-hide behaviour.
            self._wake_controls()

    def _refresh_sidebar(self):
        # Use the same search rules as the main lists: ignore case, accents,
        # punctuation, and word order while allowing partial-word matches.
        search_terms = normalize_search_text(self.sidebar_search.text()).split()
        self.playlist_list.clear()
        for i, entry in enumerate(self._playlist):
            name = entry.get('name', '')
            if not title_matches_search(name, search_terms):
                continue
            item = QListWidgetItem(f"{i + 1:>3}.  {name}")
            item.setData(Qt.UserRole, i)
            self.playlist_list.addItem(item)
            if i == self._current_idx:
                self.playlist_list.setCurrentItem(item)
        # The delegate includes font metrics and theme padding in logical pixels.
        self._playlist_width_hint = self.playlist_list.sizeHintForColumn(0)
        self._update_sidebar_width()

    def _update_sidebar_width(self):
        """Fit playlist titles while reserving at least 40% of the window for video."""
        if not self.centralWidget():
            return
        margins = self.sidebar.layout().contentsMargins()
        chrome_width = (margins.left() + margins.right()
                        + 2 * self.playlist_list.frameWidth()
                        + self.playlist_list.verticalScrollBar().sizeHint().width())
        desired_width = max(1, self._playlist_width_hint + chrome_width)
        available_width = max(1, int(self.centralWidget().width() * 0.6))
        if not self._is_fullscreen:
            # The video has its own minimum width. A fixed sidebar wider than
            # the remaining space makes Qt grow the entire top-level window.
            margins = self._content_layout.contentsMargins()
            remaining_width = (self._content_widget.width() - self.video_frame.minimumWidth()
                               - margins.left() - margins.right()
                               - max(0, self._content_layout.spacing()))
            available_width = max(1, min(available_width, remaining_width))
        width = min(desired_width, available_width)
        self.sidebar.set_preferred_width(width)

    def _playlist_item_activated(self, item):
        idx = item.data(Qt.UserRole)
        if not isinstance(idx, int) or idx < 0 or idx >= len(self._playlist):
            return
        self._store_current_playlist_progress()
        self._current_idx = idx
        self._play_current()
        if not self._pinned_sidebar:
            QTimer.singleShot(800, lambda: self.sidebar.hide())
            self._sidebar_visible = False
            self._aspect_controller.sidebar_changed()

    # ---------- show / hide the player controls ----------
    def _wake_controls(self):
        self.overlay.show()
        self.top_bar.show()
        # Restore the normal cursor on the video frame; the overlay and top bar
        # have their own ArrowCursor set in _init_cursors so they never blank.
        self.video_frame.unsetCursor()
        self._reposition_overlays()
        # Windowed controls reserve their own space and remain permanently visible.
        if not self._is_fullscreen:
            self._hide_timer.stop()
        elif self.player.is_playing():
            self._hide_timer.start(3000)
        else:
            self._hide_timer.stop()

    def _hide_controls(self):
        if not self._is_fullscreen:
            return
        if self._sidebar_visible:
            return
        if self._seeking:
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
        self._update_sidebar_width()
        self._reposition_track_osd()
        self._reposition_stream_info_panel()
        if not self._is_fullscreen:
            return
        w = self.centralWidget().width()
        h = self.centralWidget().height()
        self.top_bar.setGeometry(0, 0, w, self.top_bar.height())
        self.overlay.setGeometry(0, h - self.overlay.height(), w, self.overlay.height())
        if self._sidebar_visible:
            self.sidebar.setGeometry(0, self.top_bar.height(),
                                     self.sidebar.width(),
                                     h - self.top_bar.height() - self.overlay.height())

    def _reposition_track_osd(self):
        """Keep the temporary track message centered near the top of the video."""
        if not hasattr(self, "track_osd") or not self.centralWidget():
            return
        origin = self.video_frame.mapTo(self.centralWidget(), QPoint(0, 0))
        x = origin.x() + max(0, (self.video_frame.width() - self.track_osd.width()) // 2)
        y = origin.y() + 20
        self.track_osd.move(x, y)

    def _information_content_resized(self, *_args):
        """Recalculate after Qt settles text layout or per-screen font metrics."""
        if not getattr(self, '_measuring_info_panel', False):
            self._info_layout_timer.start(0)

    def _reposition_stream_info_panel(self, *_args):
        """Fit the visible information content inside the video's top-right corner."""
        if (not hasattr(self, "stream_info_panel") or not self.centralWidget()
                or getattr(self, '_measuring_info_panel', False)):
            return
        self._measuring_info_panel = True
        try:
            body = self.programme_text if self.btn_programme.isChecked() else self.stream_info_tree
            available = QSize(self.video_frame.width() - 32, self.video_frame.height() - 32)
            # Measure without a stale scrollbar narrowing the text viewport.
            if body is self.programme_text:
                body.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.stream_info_panel.setFixedSize(information_panel_size(
                self.stream_info_panel, self.stream_info_title, body, available))
            self.stream_info_panel.layout().activate()
            if body is self.programme_text:
                body.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            origin = self.video_frame.mapTo(self.centralWidget(), QPoint(0, 0))
            x = origin.x() + max(8, self.video_frame.width() - self.stream_info_panel.width() - 16)
            self.stream_info_panel.move(x, origin.y() + 16)
        finally:
            self._measuring_info_panel = False

    # ---------- VLC poll ----------
    def _poll_state(self):
        """Synchronize controls with VLC and retry startup operations when ready.

        Opening media is asynchronous: duration and seeking may not be available
        yet. Deferred presentation is bounded so a failed seek cannot hide the
        player indefinitely. While dragging, the user owns the seek position.
        """
        try:
            # player.play() returns before libVLC reaches Playing. The initial
            # _wake_controls() call can therefore see is_playing() == False and
            # leave the controls visible forever. Start the timer once playback
            # is actually active, without restarting it on every polling cycle.
            if (
                self._is_fullscreen
                and
                self.player.is_playing()
                and self.overlay.isVisible()
                and not self._sidebar_visible
                and not self._hide_timer.isActive()
            ):
                self._hide_timer.start(3000)

            length = self._playback_length()
            cur    = self.player.get_time()
            resume_completed = False
            if self._pending_resume_ms and length > 0 and self.player.is_playing():
                target = min(self._pending_resume_ms, length)
                if cur >= target - 500:
                    self._pending_resume_ms = 0
                    self._pending_resume_attempts = 0
                    resume_completed = True
                elif self._pending_resume_attempts > 0:
                    # VLC can reject an early seek while media metadata is still
                    # opening. Retry briefly and confirm the reported position.
                    self.player.set_time(target)
                    self._pending_resume_attempts -= 1
                else:
                    self._pending_resume_ms = 0
                    resume_completed = True
                cur = self.player.get_time()
            if self._recovering_after_pause:
                self._check_pause_recovery(cur)
                if self._pause_recovery_failed:
                    return
            if self._deferred_present:
                self._deferred_present_polls -= 1
                if resume_completed or self._deferred_present_polls <= 0:
                    self._present_player(self._deferred_keep_topmost)
            is_live = (self._current_history or {}).get("type") == "LIVE"
            if is_live:
                self.seek_slider.setEnabled(False)
                self.seek_slider.setValue(0)
                self.time_label.setText("LIVE")
            elif length > 0:
                if self._maybe_auto_advance(cur, length):
                    return
                self.seek_slider.setEnabled(True)
                if not self._seeking and not self._wheel_seek_timer.isActive():
                    self.seek_slider.setValue(int(max(0, cur) / length * 1000))
                    self.time_label.setText(
                        f"{self._fmt_ms(cur)} / {self._fmt_ms(length)}"
                    )
            else:
                # VOD duration can be unavailable briefly while VLC opens media.
                self.seek_slider.setEnabled(False)
                self.seek_slider.setValue(0)
                self.time_label.setText("Loading...")
            self._update_subs_button()
            self._update_audio_button()
            self._apply_pending_playback_rate()
            self._report_progress()
        except Exception:
            pass

    def _maybe_auto_advance(self, position_ms, duration_ms):
        """Advance once playback enters the configured credits-skip window."""
        if _pause_blocks_navigation(self):
            return False
        if (
            not self._auto_play_next
            or self._auto_advance_triggered
            or self._auto_advance_seconds <= 0
            or self._current_idx + 1 >= len(self._playlist)
            or (self._current_history or {}).get("type") == "LIVE"
        ):
            return False
        threshold_ms = self._auto_advance_seconds * 1000
        if position_ms < 1000 or duration_ms - position_ms > threshold_ms:
            return False
        self._auto_advance_triggered = True
        self.next()
        return True

    def _report_progress(self, force=False):
        """Send playback progress to the main process at ten-second intervals."""
        if getattr(self, '_recovering_after_pause', False) or getattr(self, '_pause_recovery_failed', False):
            return
        if not self._current_history or self._progress_callback is None:
            return
        now = time.monotonic()
        if not force and now - self._last_progress_report < 10:
            return
        try:
            entry = dict(self._current_history)
            duration_ms = int(self.player.get_length())
            position_ms = int(self.player.get_time())
            if entry.get("type") != "LIVE" and duration_ms <= 0:
                # Never replace a valid resume point with VLC's transient opening
                # values while a movie or episode is still loading.
                return
            entry["position_ms"] = max(0, position_ms)
            entry["duration_ms"] = max(0, duration_ms)
            self._current_history = entry
            self._progress_callback({
                "event": "history_progress",
                "history": entry,
            })
            self._last_progress_report = now
        except (EOFError, OSError, TypeError, ValueError):
            pass

    def _seek_pressed(self):
        # Set the seeking flag the moment the user grabs (or clicks) the slider,
        # so the 500 ms poll timer doesn't yank the handle back while they drag.
        self._seeking = True
        self._hide_timer.stop()
        self.overlay.show()
        self._show_seek_preview(self.seek_slider.value())

    def _seek_moved(self, value):
        self._seeking = True
        self._show_seek_preview(value)

    def _seek_released(self):
        """Commit the preview position to VLC once, then resume normal polling."""
        try:
            length = self._playback_length()
            if length > 0:
                self.player.set_time(int(self.seek_slider.value() / 1000 * length))
        finally:
            self._seeking = False
            QToolTip.hideText()
            self._wake_controls()

    def _show_seek_preview(self, slider_value):
        """Show the timestamp represented by the seek handle while it is dragged."""
        length = self._playback_length()
        if length <= 0:
            return
        target = int(max(0, min(1000, slider_value)) / 1000 * length)
        handle_x = int(self.seek_slider.width() * slider_value / 1000)
        point = self.seek_slider.mapToGlobal(QPoint(handle_x, -28))
        QToolTip.showText(point, self._fmt_ms(target), self.seek_slider)

    def _playback_length(self):
        """Return VLC's duration or the last valid VOD duration during opening."""
        try:
            length = int(self.player.get_length())
        except (TypeError, ValueError):
            length = 0
        if length > 0:
            return length
        history = self._current_history or {}
        if history.get("type") == "LIVE":
            return 0
        try:
            return max(0, int(history.get("duration_ms", 0)))
        except (TypeError, ValueError):
            return 0

    def _apply_pending_playback_rate(self):
        """Apply the saved VOD rate or normal speed for a LIVE stream."""
        if not self._pending_playback_rate_attempts or not self.player.is_playing():
            return
        try:
            target_rate = self._effective_playback_rate()
            self.player.set_rate(target_rate)
            self.rate_label.setText(f"{target_rate:.2f}x")
            self._pending_playback_rate_attempts -= 1
            if abs(float(self.player.get_rate()) - target_rate) < 0.01:
                self._pending_playback_rate_attempts = 0
        except (TypeError, ValueError):
            self._pending_playback_rate_attempts = 0

    def _is_live_playback(self):
        """Return whether the current media is a LIVE stream."""
        return (self._current_history or {}).get("type") == "LIVE"

    def _effective_playback_rate(self):
        """Keep LIVE playback at normal speed without losing the VOD setting."""
        return 1.0 if self._is_live_playback() else self._playback_rate

    def _update_playback_rate_controls(self):
        """Reflect whether speed controls apply to the current media."""
        enabled = not self._is_live_playback()
        self.btn_slow.setEnabled(enabled)
        self.btn_fast.setEnabled(enabled)
        self.rate_label.setText(f"{self._effective_playback_rate():.2f}x")

    @staticmethod
    def _fmt_ms(ms):
        if ms is None or ms < 0:
            return "00:00"
        s = int(ms // 1000)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    # ---------- volume persistence ----------
    def _settings_path(self):
        if self._explicit_settings_path:
            return self._explicit_settings_path
        try:
            return path.abspath(self._app_parent.user_data_file)
        except Exception:
            return None

    def _load_volume_pref(self):
        settings_path = self._settings_path()
        if not settings_path or not path.isfile(settings_path):
            return 80
        try:
            config = configparser.ConfigParser()
            config.read(settings_path)
            return max(0, min(100, config.getint("InternalPlayer", "volume", fallback=80)))
        except (OSError, ValueError, configparser.Error, UnicodeDecodeError):
            return 80

    def _save_volume_pref(self):
        settings_path = self._settings_path()
        if not settings_path:
            return
        try:
            config = configparser.ConfigParser()
            config.read(settings_path)
            if not config.has_section("InternalPlayer"):
                config.add_section("InternalPlayer")
            config.set("InternalPlayer", "volume", str(self._volume))
            write_config_file(settings_path, config)
        except (OSError, configparser.Error, UnicodeDecodeError):
            pass

    def _restore_window_geometry(self):
        """Restore the player's last screen, position, dimensions, and window state."""
        settings_path = self._settings_path()
        if not settings_path or not path.isfile(settings_path):
            return
        try:
            config = configparser.ConfigParser()
            config.read(settings_path)
            encoded = config.get("InternalPlayerWindow", "geometry", fallback="")
            if encoded:
                self.restoreGeometry(QByteArray.fromBase64(encoded.encode("ascii")))
                visible = any(
                    screen.availableGeometry().intersects(self.frameGeometry())
                    for screen in QApplication.screens()
                )
                if not visible and QApplication.primaryScreen() is not None:
                    area = QApplication.primaryScreen().availableGeometry()
                    self.move(area.center() - self.rect().center())
        except (OSError, ValueError, configparser.Error, UnicodeDecodeError):
            pass

    def _save_window_geometry(self):
        """Persist the native player geometry for the next isolated process."""
        settings_path = self._settings_path()
        if not settings_path:
            return
        try:
            config = configparser.ConfigParser()
            config.read(settings_path)
            if not config.has_section("InternalPlayerWindow"):
                config.add_section("InternalPlayerWindow")
            encoded = bytes(self.saveGeometry().toBase64()).decode("ascii")
            config.set("InternalPlayerWindow", "geometry", encoded)
            write_config_file(settings_path, config)
        except (OSError, configparser.Error, UnicodeDecodeError):
            pass

    def _load_playback_rate_pref(self):
        settings_path = self._settings_path()
        if not settings_path or not path.isfile(settings_path):
            return 1.0
        try:
            config = configparser.ConfigParser()
            config.read(settings_path)
            rate = config.getfloat("InternalPlayer", "playback_rate", fallback=1.0)
            return max(0.25, min(4.0, round(rate, 2)))
        except (OSError, ValueError, configparser.Error, UnicodeDecodeError):
            return 1.0

    def _save_playback_rate_pref(self):
        settings_path = self._settings_path()
        if not settings_path:
            return
        try:
            config = configparser.ConfigParser()
            config.read(settings_path)
            if not config.has_section("InternalPlayer"):
                config.add_section("InternalPlayer")
            config.set("InternalPlayer", "playback_rate", str(self._playback_rate))
            write_config_file(settings_path, config)
        except (OSError, configparser.Error, UnicodeDecodeError):
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
        for root in (self.overlay, self.top_bar, self.sidebar, getattr(self, "stream_info_panel", None)):
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
        et = event.type()

        # Scrolling a description or the technical tree must not seek the video.
        if (et == QEvent.Wheel and hasattr(self, "stream_info_panel")
                and self.stream_info_panel.isAncestorOf(obj)):
            return False

        # An eventFilter installed on QApplication is invoked with the RECEIVING
        # widget as `obj` — not QApplication itself. So the only reliable way
        # to scope our handling to the player window is to walk the parent
        # chain and bail out for any event whose target sits outside our tree.
        # Otherwise a double-click on the main window's central widget would
        # fire the player's toggle_fullscreen().
        if not self._obj_is_in_player(obj):
            return False

        if et == QEvent.ToolTip and obj is self.btn_info:
            QToolTip.showText(
                event.globalPos(), self.btn_info.toolTip(), self.btn_info
            )
            return True

        if et in (QEvent.MouseMove, QEvent.MouseButtonPress, QEvent.MouseButtonDblClick,
                  QEvent.KeyPress, QEvent.Wheel):
            self._wake_controls()

        if et == QEvent.Wheel:
            # Qt can propagate an unhandled wheel event to the player window when
            # a short list, or a list already at an edge, cannot scroll further.
            # Use the pointer position so that propagation never turns the same
            # wheel movement into a volume command.
            if (self._event_is_over_widget(event, self.sidebar)
                    or self._event_is_over_widget(event, self.stream_info_panel)):
                return False
            # This filter is installed both globally and on player widgets. Ignore
            # duplicate delivery of the same event so one wheel notch is one step.
            wheel_event_id = id(event)
            if wheel_event_id == self._last_wheel_event_id:
                return True
            self._last_wheel_event_id = wheel_event_id
            QTimer.singleShot(
                0, lambda: setattr(self, '_last_wheel_event_id', None)
            )

            # Use a fixed application step instead of the OS scroll-line setting.
            try:
                delta = event.angleDelta().y()
            except Exception:
                delta = 0
            over_player_controls = self._event_is_over_widget(event, self.overlay)
            over_audio_controls = self._event_is_over_widget(event, self.audio_controls)
            over_rate_controls = self._event_is_over_widget(event, self.rate_controls)
            over_video = self._event_is_over_widget(event, self.video_frame)
            if over_rate_controls:
                if delta > 0:
                    self._adjust_rate(self._speed_step)
                elif delta < 0:
                    self._adjust_rate(-self._speed_step)
                return True
            # Fullscreen controls overlap the video rectangle. Audio controls
            # must win over the underlying video, just like the speed controls.
            if not over_audio_controls and (over_player_controls or over_video):
                if self.seek_slider.isEnabled():
                    if delta > 0:
                        self.preview_wheel_seek(self._seek_step_ms)
                    elif delta < 0:
                        self.preview_wheel_seek(-self._seek_step_ms)
                return True
            if delta > 0:
                self._step_volume(self._volume_step)
            elif delta < 0:
                self._step_volume(-self._volume_step)
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

    @staticmethod
    def _event_is_over_widget(event, widget):
        """Return whether a pointer event is physically over a visible widget."""
        if not widget.isVisible():
            return False
        try:
            global_position = event.globalPos()
        except (AttributeError, TypeError):
            global_position = QCursor.pos()
        return widget.rect().contains(widget.mapFromGlobal(global_position))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_overlays()
        if hasattr(self, "_video_resize_timer"):
            self._video_resize_timer.start(80)

    def nativeEvent(self, event_type, message):
        # Windows uses a native modal loop for window-border resizing. Qt mouse
        # release events alone cannot reliably identify the end of that loop.
        if sys.platform == 'win32':
            from ctypes.wintypes import MSG
            native = MSG.from_address(int(message))
            controller = getattr(self, '_aspect_controller', None)
            if controller is not None:
                if native.message == 0x0231:  # WM_ENTERSIZEMOVE
                    controller.native_size_move(True)
                elif native.message == 0x0232:  # WM_EXITSIZEMOVE
                    controller.native_size_move(False)
        return super().nativeEvent(event_type, message)

    def changeEvent(self, event):
        """Pause only for minimization and resume only when that pause was automatic."""
        super().changeEvent(event)
        if event.type() != QEvent.WindowStateChange:
            return
        if hasattr(self, 'btn_aspect_lock') and hasattr(self, '_icon_color'):
            self._update_window_aspect_lock_button()
        controller = getattr(self, '_aspect_controller', None)
        if controller is not None and not self.isMaximized() and not self.isMinimized() and not self._is_fullscreen:
            QTimer.singleShot(0, controller.apply)
        if self.isMinimized():
            if self.player.is_playing():
                self._pause_playback()
                self._paused_by_minimize = True
        elif self._paused_by_minimize:
            self._paused_by_minimize = False
            self._resume_playback()

    def closeEvent(self, event):
        self._programme_timer.stop()
        self._pause_started_at = None
        self._recovering_after_pause = False
        self._pause_recovery_failed = False
        try:
            self._wheel_seek_timer.stop()
            self._track_osd_timer.stop()
            self._hide_track_osd()
            self._report_progress(force=True)
            self._save_volume_pref()
            self._save_playback_rate_pref()
            self._save_window_geometry()
            self.player.stop()
        except Exception:
            pass
        super().closeEvent(event)
        set_macos_activation_policy(False)
