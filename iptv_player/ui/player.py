"""Embedded VLC player window and controls."""

import configparser
from os import path
import sys

from PyQt5.QtCore import QPoint, QSize, Qt, QTimer
from PyQt5.QtGui import (
    QColor,
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
    QPushButton,
    QSlider,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from iptv_player.config import write_config_file
from iptv_player.ui.player_theme import (
    DARK_BUTTON_STYLE,
    DARK_OVERLAY_STYLE,
    DARK_SIDEBAR_STYLE,
    LIGHT_BUTTON_STYLE,
    LIGHT_OVERLAY_STYLE,
    LIGHT_SIDEBAR_STYLE,
)
from iptv_player.utils.search import normalize_search_text, title_matches_search


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


class EmbeddedPlayerWindow(QMainWindow):
    """Floating libvlc-backed player window with a nebula-iptv-style UX:

    - Bottom control overlay with emoji icons (⏮ ⏯ ⏭ ⏪ ⏩ 🔊 ⛶ CC)
    - Top overlay with the stream title
    - Auto-hide controls 3s after the last mouse/keyboard event while playing
    - Left-edge sidebar with the current playlist + a live filter; click to play
    - Next/Previous walk the visible playlist, disabled at the edges (no wrap)
    - Subtitle button shows up only when libvlc reports >1 SPU track
    - Keyboard: Space=play/pause, F=fullscreen, A/S=cycle audio/subtitles,
      Page Up/Page Down=previous/next,
      Left/Right=seek ±10s, Up/Down=volume, +/-=speed, M=mute

    The whole thing is a single QMainWindow so multi-monitor + window
    management Just Works; the caller provides a `playlist` list-of-dicts
    (each with at least `name` and `url`) plus a starting index.
    """

    def __init__(
        self, parent=None, user_agent="", settings_path=None,
        seek_step_seconds=10, volume_step_percent=2, speed_step=0.25,
        audio_language="", subtitle_language=""
    ):
        super().__init__(parent)
        self.setWindowTitle("Internal Player")
        self.setWindowIcon(self._player_window_icon())
        self.resize(1080, 640)

        import vlc
        self._vlc = vlc

        vlc_args = ["--quiet"]
        ua = (user_agent or "").strip()
        if ua:
            vlc_args.append(f"--http-user-agent={ua}")

        self.instance = vlc.Instance(vlc_args)
        self.player = self.instance.media_player_new()

        self._playlist = []   # list of {'name': str, 'url': str, ...}
        self._current_idx = 0
        self._sidebar_visible = False
        self._pinned_sidebar = False
        self._is_fullscreen = False
        self._muted = False
        self._last_wheel_event_id = None
        # Start from safe values; set_control_steps performs defensive parsing
        # after every control has been created and can update its tooltip.
        self._seek_step_ms = 10000
        self._volume_step = 2
        self._speed_step = 0.25
        self._audio_language = ""
        self._subtitle_language = ""
        self._app_parent = parent
        self._explicit_settings_path = settings_path
        self._volume = self._load_volume_pref()
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
        self.btn_slow   = QPushButton("−")
        self.btn_fast   = QPushButton("+")
        self.rate_label = QLabel("1.00x")
        self.btn_mute   = QPushButton()
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(self._volume)
        self.vol_slider.setFixedWidth(120)
        self.btn_audio  = QPushButton("Audio")
        self.btn_audio.setEnabled(False)
        self.btn_subs   = QPushButton("CC")
        self.btn_subs.setEnabled(False)
        self.btn_fs     = QPushButton()
        self.pl_pos     = QLabel("")

        for b in (self.btn_prev, self.btn_rewind, self.btn_play, self.btn_ffwd,
                  self.btn_next, self.btn_slow, self.btn_fast, self.btn_mute,
                  self.btn_audio, self.btn_subs, self.btn_fs, self.btn_sidebar):
            b.setFixedHeight(30)
            b.setIconSize(QSize(18, 18))
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)

        # Play and pause use glyphs with different natural widths. A fixed button
        # width keeps every neighbouring control stationary when the icon changes.
        self.btn_play.setFixedWidth(40)

        self.btn_prev.setToolTip("Previous (Page Up)")
        self.btn_rewind.setToolTip("Rewind (Left arrow)")
        self.btn_play.setToolTip("Play / Pause (Space)")
        self.btn_ffwd.setToolTip("Forward (Right arrow)")
        self.btn_next.setToolTip("Next (Page Down)")
        self.btn_slow.setToolTip("Slower (-)")
        self.btn_fast.setToolTip("Faster (+)")
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
        btn_row.addWidget(self.btn_slow)
        btn_row.addWidget(self.rate_label)
        btn_row.addWidget(self.btn_fast)
        btn_row.addStretch(1)
        btn_row.addWidget(self.pl_pos)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_mute)
        btn_row.addWidget(self.vol_slider)
        btn_row.addSpacing(8)
        btn_row.addWidget(self.btn_audio)
        btn_row.addWidget(self.btn_subs)
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
        self.sidebar = QWidget(self)
        self.sidebar.setObjectName("sidebarRoot")
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
        self._track_osd_timer.timeout.connect(self.track_osd.hide)

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
        QShortcut(QKeySequence(Qt.Key_A),     self, activated=self._cycle_audio)
        QShortcut(QKeySequence(Qt.Key_S),     self, activated=self._cycle_subs)
        QShortcut(QKeySequence(Qt.Key_M),     self, activated=self.toggle_mute)
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

    def _tinted_standard_icon(self, standard_pixmap):
        """Tint a Qt standard icon so it remains visible on the active theme."""
        source = self.style().standardIcon(standard_pixmap).pixmap(24, 24)
        tinted = QPixmap(source.size())
        tinted.fill(Qt.transparent)
        painter = QPainter(tinted)
        painter.drawPixmap(0, 0, source)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), self._icon_color)
        painter.end()
        return QIcon(tinted)

    @staticmethod
    def _player_window_icon():
        """Create a compact player icon that remains clear in the native caption."""
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#7c3aed"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(2, 2, 20, 20, 5, 5)
        painter.setBrush(Qt.white)
        painter.drawPolygon(QPolygon([QPoint(9, 7), QPoint(9, 17), QPoint(17, 12)]))
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def _menu_icon(color):
        """Draw a crisp menu symbol without relying on a platform glyph font."""
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(color, 2, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        for y in (7, 12, 17):
            painter.drawLine(6, y, 18, y)
        painter.end()
        return QIcon(pixmap)

    def _set_standard_icon(self, button, standard_pixmap):
        button.setIcon(self._tinted_standard_icon(standard_pixmap))

    def _refresh_standard_icons(self):
        """Reload native icons after a palette or playback-state change."""
        self._set_standard_icon(self.btn_prev, QStyle.SP_MediaSkipBackward)
        self._set_standard_icon(self.btn_rewind, QStyle.SP_MediaSeekBackward)
        play_icon = QStyle.SP_MediaPause if self.player.is_playing() else QStyle.SP_MediaPlay
        self._set_standard_icon(self.btn_play, play_icon)
        self._set_standard_icon(self.btn_ffwd, QStyle.SP_MediaSeekForward)
        self._set_standard_icon(self.btn_next, QStyle.SP_MediaSkipForward)
        muted = self._muted or self._volume == 0
        volume_icon = QStyle.SP_MediaVolumeMuted if muted else QStyle.SP_MediaVolume
        self._set_standard_icon(self.btn_mute, volume_icon)
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
        self.btn_sidebar.setIcon(self._menu_icon(self._icon_color))
        button_style = DARK_BUTTON_STYLE if dark else LIGHT_BUTTON_STYLE
        overlay_style = DARK_OVERLAY_STYLE if dark else LIGHT_OVERLAY_STYLE
        sidebar_style = DARK_SIDEBAR_STYLE if dark else LIGHT_SIDEBAR_STYLE
        label_color = "#ccc" if dark else "#303030"

        for button in (
            self.btn_prev, self.btn_rewind, self.btn_play, self.btn_ffwd,
            self.btn_next, self.btn_slow, self.btn_fast, self.btn_mute,
            self.btn_audio, self.btn_subs, self.btn_fs, self.btn_sidebar
        ):
            button.setStyleSheet(button_style)
        self.overlay.setStyleSheet(overlay_style)
        self.top_bar.setStyleSheet(overlay_style)
        self.sidebar.setStyleSheet(sidebar_style)
        self.rate_label.setStyleSheet(f"color: {label_color}; padding: 0 8px;")
        self.pl_pos.setStyleSheet(f"color: {label_color}; padding: 0 8px;")
        osd_background = "rgba(20,20,22,220)" if dark else "rgba(248,248,248,235)"
        self.track_osd.setStyleSheet(
            f"background: {osd_background}; color: {label_color}; "
            "border: 1px solid palette(mid); border-radius: 6px; "
            "padding: 8px 14px; font-size: 13px; font-weight: bold;"
        )
        self._apply_native_title_bar_theme(dark)
        self._refresh_standard_icons()

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
    def is_available():
        try:
            import vlc  # noqa: F401
            vlc.Instance()
            return True
        except Exception:
            return False

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
        # Keep the native title concise; the complete media title is shown below it.
        self.setWindowTitle("Internal Player")
        self.title_label.setText(title)

        media = self.instance.media_new(url)
        # VLC accepts ISO 639 language codes as per-media options. Leaving a
        # preference empty preserves VLC's own default track-selection policy.
        if self._audio_language:
            media.add_option(f":audio-language={self._audio_language}")
        if self._subtitle_language == "disabled":
            media.add_option(":no-spu")
        elif self._subtitle_language:
            media.add_option(f":sub-language={self._subtitle_language}")
        self.player.set_media(media)
        self.show()
        # Apply native caption colors after the HWND is visible because Windows
        # may initialize its final non-client appearance during the first show.
        self.apply_theme()
        self.raise_()
        self.activateWindow()
        self._bind_video_output()
        self.player.play()
        self._set_standard_icon(self.btn_play, QStyle.SP_MediaPause)
        self._update_pl_pos()
        self._wake_controls()

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

    # ---------- transport ----------
    def toggle_play_pause(self):
        if self.player.is_playing():
            self.player.pause()
            self._set_standard_icon(self.btn_play, QStyle.SP_MediaPlay)
        else:
            self.player.play()
            self._set_standard_icon(self.btn_play, QStyle.SP_MediaPause)
        self._wake_controls()

    def stop(self):
        self.player.stop()
        self._set_standard_icon(self.btn_play, QStyle.SP_MediaPlay)

    def seek_by(self, ms):
        cur = self.player.get_time()
        if cur < 0:
            return
        new = max(0, cur + ms)
        self.player.set_time(int(new))
        seconds = abs(ms) / 1000
        amount = f"{seconds:g}"
        direction = "+" if ms >= 0 else "−"
        unit = "second" if seconds == 1 else "seconds"
        self._show_track_osd(f"{direction}{amount} {unit}")
        self._wake_controls()

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
            action = QAction(name, self)
            action.setCheckable(True)
            action.setChecked(track_id == current)
            action.triggered.connect(
                lambda _, selected_id=track_id: self._select_audio_track(selected_id)
            )
            menu.addAction(action)
        menu.exec_(self.btn_audio.mapToGlobal(self.btn_audio.rect().bottomLeft()))
        # A modal popup can leave its invoker focused after dismissal, which
        # resembles a selected state even when the user chose no track.
        self.btn_audio.setDown(False)
        self.btn_audio.clearFocus()
        self.btn_audio.update()

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
            act = QAction(name, self)
            act.setCheckable(True)
            act.setChecked(tid == current)
            act.triggered.connect(lambda _, t=tid: self.player.video_set_spu(t))
            menu.addAction(act)
        menu.exec_(self.btn_subs.mapToGlobal(self.btn_subs.rect().bottomLeft()))
        self.btn_subs.setDown(False)
        self.btn_subs.clearFocus()
        self.btn_subs.update()

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

    def _show_track_osd(self, text):
        """Show a brief track-selection message over the video picture."""
        self.track_osd.setText(text)
        self.track_osd.adjustSize()
        self._reposition_track_osd()
        self.track_osd.show()
        self.track_osd.raise_()
        self._track_osd_timer.start(1800)

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
        self._reposition_track_osd()
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

    # ---------- VLC poll ----------
    def _poll_state(self):
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
            self._update_audio_button()
        except Exception:
            pass

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
