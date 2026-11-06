"""Window aspect locking with bounded geometry and a stable size reference."""
import math
import logging
from PyQt5.QtCore import QObject, QEvent, QRect, QSize, QTimer, Qt
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QMouseEvent
from iptv_player.ui.native_mouse import NativeMouseButton


def aspect_size(ratio, reference, chrome, minimum, maximum):
    """Fit a display ratio while preserving its longest video dimension when possible."""
    if not ratio or not math.isfinite(ratio) or ratio <= 0:
        return None
    height = reference / max(1.0, ratio)
    width = height * ratio
    min_width = max(1, minimum.width() - chrome.width())
    min_height = max(1, minimum.height() - chrome.height())
    max_width = max(1, maximum.width() - chrome.width())
    max_height = max(1, maximum.height() - chrome.height())
    lower = max(min_width / ratio, min_height)
    upper = min(max_width / ratio, max_height)
    if lower > upper:
        # A small monitor or an extreme portrait format may make a strict ratio
        # impossible with the toolbar minimum. Keep the window on screen instead.
        return QSize(min(maximum.width(), max(minimum.width(), round(width + chrome.width()))),
                     min(maximum.height(), max(minimum.height(), round(height + chrome.height()))))
    height = max(lower, min(height, upper))
    return QSize(round(height * ratio) + chrome.width(), round(height) + chrome.height())


class WindowAspectController(QObject):
    """Constrain the video area, leaving chrome, playlist and fullscreen independent."""
    def __init__(self, window, ratio_provider, enabled=True):
        super().__init__(window)
        self.window = window
        self.ratio_provider = ratio_provider
        self.enabled = enabled
        self.ratio = None
        self.reference = None
        self.adjusting = False
        self.pending = None
        self.native_drag = False
        self.interactive_resize = False
        self.resume_url = None
        self.mouse_state = NativeMouseButton()
        window.destroyed.connect(self.mouse_state.close)
        self.release_timer = QTimer(self)
        self.release_timer.setInterval(30)
        self.release_timer.timeout.connect(self._check_release)
        self.previous = QRect(window.geometry())
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh_ratio)
        self.timer.start()
        window.installEventFilter(self)

    def suspended(self):
        window = self.window
        return (window._is_fullscreen or window.isFullScreen() or window.isMaximized()
                or window.isMinimized() or window._sidebar_visible or window.sidebar.isVisible())

    def chrome(self):
        window = self.window
        outer = window._outer_layout.contentsMargins()
        inner = window._content_layout.contentsMargins()
        return QSize(outer.left() + outer.right() + inner.left() + inner.right(),
                     outer.top() + outer.bottom() + inner.top() + inner.bottom()
                     + window.top_bar.height() + window.overlay.height())

    def capture_reference(self):
        chrome = self.chrome()
        self.reference = max(1, self.window.width() - chrome.width(),
                             self.window.height() - chrome.height())

    def reset_media(self):
        self.ratio = None
        self.window.player._window_aspect_diagnostic = None
        self._diagnostic_state = None
        logging.debug('Window aspect: media reset; locked=%s; fullscreen=%s; playlist=%s',
                      self.enabled, self.window._is_fullscreen, self.window._sidebar_visible)

    def refresh_ratio(self):
        if not self.window.isVisible():
            return
        ratio = self.ratio_provider()
        state = (ratio, self.enabled, self.suspended(), self.interactive_resize)
        if getattr(self, '_diagnostic_state', None) != state:
            self._diagnostic_state = state
            logging.debug('Window aspect controller: ratio=%s; locked=%s; suspended=%s; dragging=%s',
                          *state)
        if ratio is None:
            return
        changed = self.ratio is None or abs(self.ratio - ratio) > 0.001
        self.ratio = ratio
        if changed and self.enabled and not self.suspended():
            if self.reference is None:
                self.capture_reference()
            self.apply()

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        self.pending = None
        if self.enabled and not self.suspended():
            self.capture_reference()
            self.refresh_ratio()
            self.apply()

    def sidebar_changed(self):
        # Merely opening/closing the playlist must never resize the outer window.
        self.pending = None
        self.previous = QRect(self.window.geometry())

    def apply(self, requested=None):
        window = self.window
        if not self.enabled or not window.isVisible() or self.suspended() or self.ratio is None or self.adjusting or self.interactive_resize:
            return
        if self.reference is None:
            self.capture_reference()
        chrome = self.chrome()
        minimum = window.minimumSizeHint().expandedTo(window.minimumSize())
        screen = window.screen()
        if screen is None:
            return
        area = screen.availableGeometry()
        frame = window.frameGeometry().size() - window.size()
        maximum = area.size() - frame
        target = aspect_size(self.ratio, self.reference, chrome, minimum, maximum)
        if target is None:
            return
        rect = QRect(window.geometry() if requested is None else requested)
        # Preserve the opposite edge when dragging the left or top window border.
        old = self.previous
        anchor_right = requested is not None and rect.x() != old.x()
        anchor_bottom = requested is not None and rect.y() != old.y()
        rect.setSize(target)
        if anchor_right:
            rect.moveRight(old.right())
        if anchor_bottom:
            rect.moveBottom(old.bottom())
        frame_left = window.geometry().left() - window.frameGeometry().left()
        frame_top = window.geometry().top() - window.frameGeometry().top()
        frame_right = window.frameGeometry().right() - window.geometry().right()
        frame_bottom = window.frameGeometry().bottom() - window.geometry().bottom()
        rect.moveLeft(max(area.left() + frame_left, min(rect.left(), area.right() - target.width() - frame_right + 1)))
        rect.moveTop(max(area.top() + frame_top, min(rect.top(), area.bottom() - target.height() - frame_bottom + 1)))
        self.adjusting = True
        try:
            if window.geometry() != rect:
                logging.debug('Window aspect resize: from=%sx%s; to=%sx%s; ratio=%s; reference=%s',
                              window.width(), window.height(), rect.width(), rect.height(),
                              self.ratio, self.reference)
                window.setGeometry(rect)
            self.previous = QRect(window.geometry())
        finally:
            self.adjusting = False

    def native_size_move(self, entering):
        """Windows owns border drags and reports their end outside Qt mouse events."""
        self.native_drag = entering
        if not entering:
            self._end_interactive_resize()

    def _begin_interactive_resize(self):
        if self.interactive_resize:
            return
        self.interactive_resize = True
        # Use the shared pause/resume path, including recovery after long pauses.
        if self.window.player.is_playing():
            self.resume_url = self.window._current_url
            self.window._pause_playback()
        self.release_timer.start()

    def _left_button_pressed(self):
        native = self.mouse_state.pressed()
        return bool(QApplication.mouseButtons() & Qt.LeftButton) if native is None else native

    def _check_release(self):
        if not self.native_drag and not self._left_button_pressed():
            self._end_interactive_resize()

    def _end_interactive_resize(self):
        if not self.interactive_resize:
            return
        self.release_timer.stop()
        self.mouse_state.close()
        self.interactive_resize = False
        self._finish_resize()
        url, self.resume_url = self.resume_url, None
        if (url is not None and url == self.window._current_url
                and self.window.isVisible() and not self.window.isMinimized()
                and self.window.player.get_state() == self.window._vlc.State.Paused):
            self.window._resume_playback()

    def _finish_resize(self):
        if self.interactive_resize:
            return
        pending, self.pending = self.pending, None
        if pending is None or self.suspended():
            return
        self.apply(pending)

    def eventFilter(self, obj, event):
        if self.adjusting:
            return False
        if event.type() in (QEvent.MouseButtonRelease, QEvent.NonClientAreaMouseButtonRelease):
            if isinstance(event, QMouseEvent):
                if event.button() == Qt.LeftButton and not self.native_drag:
                    self._end_interactive_resize()
            else:
                # Some native frame releases arrive as a base QEvent in PyQt.
                # It has no button() accessor; use the existing release check.
                self._check_release()
        elif event.type() == QEvent.Resize:
            if not self.enabled or self.suspended() or self.ratio is None:
                if self.enabled and not self.suspended():
                    self.capture_reference()
                self.previous = QRect(self.window.geometry())
                return False
            if self.native_drag or self._left_button_pressed():
                self._begin_interactive_resize()
            chrome = self.chrome()
            requested = QRect(self.window.geometry())
            old_size = event.oldSize()
            dx = abs(event.size().width() - old_size.width())
            dy = abs(event.size().height() - old_size.height())
            if dx >= dy * self.ratio:
                height = max(1, (event.size().width() - chrome.width()) / self.ratio)
                self.reference = max(height, height * self.ratio)
            else:
                height = max(1, event.size().height() - chrome.height())
                self.reference = max(height, height * self.ratio)
            first = self.pending is None
            self.pending = requested
            if first:
                QTimer.singleShot(0, self._finish_resize)
        elif event.type() == QEvent.Move:
            QTimer.singleShot(0, self._remember_move)
        return False

    def _remember_move(self):
        if self.pending is None:
            self.previous = QRect(self.window.geometry())
