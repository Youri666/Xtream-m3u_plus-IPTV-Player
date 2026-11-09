"""One bounded LIVE reconnect attempt, rearmed after stable playback."""
import logging
import time

from PyQt5.QtCore import QObject, QTimer
from PyQt5.QtWidgets import QStyle


RECONNECTING_MESSAGE = 'Reconnecting…'
INTERRUPTED_MESSAGE = 'Stream interrupted. Press Play to retry.'


class LiveReconnectController(QObject):
    RETRY_DELAY_MS = 1000
    START_TIMEOUT_SECONDS = 30
    STABLE_SECONDS = 30

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._reopen)
        self.reopening = False
        self.reset()

    def reset(self):
        self.timer.stop()
        self.phase = None
        self.failed = False
        self.armed = True
        self.blocked = False
        self.paused = False
        self.generation = None
        self.stable_since = None
        self.last_position = None
        self.last_progress = None

    def media_requested(self):
        if not self.reopening:
            self.reset()

    def stop(self):
        self.timer.stop()
        self.phase = None
        self.blocked = True
        self.stable_since = None

    def pause(self):
        self.stop()
        self.paused = True

    def resume(self):
        if self.failed:
            self.reset()
            self.phase = 'waiting'
            self.armed = False
            self.generation = self.window._media_generation
            self._reopen()
            return True
        if self.phase is not None:
            return True
        self.paused = False
        self.blocked = False
        return False

    def status(self):
        if self.phase is not None:
            return RECONNECTING_MESSAGE
        return 'Interrupted' if self.failed else None

    def _eligible(self):
        w = self.window
        return (w._is_live_playback() and bool(w._current_url) and w.isVisible()
                and not w.isMinimized() and not self.paused and not self.blocked)

    def ended(self, generation):
        w = self.window
        if generation != w._media_generation or not self._eligible() or self.failed:
            return
        # An old native end callback can arrive after another media has opened.
        if str(w.player.get_state()) not in ('State.Ended', 'State.Error'):
            return
        if self.phase == 'opening':
            self._fail('input ended during reconnect')
        elif self.phase is None:
            if not self.armed:
                self._fail('input ended before stable playback')
                return
            self.armed = False
            self.phase = 'waiting'
            self.generation = generation
            self.stable_since = None
            w._update_live_indicator()
            w._show_track_osd(RECONNECTING_MESSAGE)
            logging.debug('LIVE reconnect scheduled: generation=%s', generation)
            self.timer.start(self.RETRY_DELAY_MS)

    def _reopen(self):
        w = self.window
        if self.phase != 'waiting':
            return
        if not self._eligible() or self.generation != w._media_generation:
            self.stop()
            return
        self.phase = 'opening'
        self.deadline = time.monotonic() + self.START_TIMEOUT_SECONDS
        self.reopening = True
        try:
            w.player.stop()
            w.play_url(w._current_url, w.title_label.text(), resume_ms=0,
                       keep_above_main=w._deferred_keep_topmost)
            self.generation = w._media_generation
            w._update_live_indicator()
            logging.debug('LIVE reconnect opening: generation=%s', self.generation)
        except Exception as error:
            self._fail(type(error).__name__)
        finally:
            self.reopening = False

    def poll(self, position_ms):
        if not self._eligible() or self.failed:
            return
        w = self.window
        state = str(w.player.get_state())
        now = time.monotonic()
        if self.phase == 'opening':
            if w.player.is_playing():
                self.phase = None
                self.stable_since = self.last_progress = now
                self.last_position = position_ms
                w._update_live_indicator()
                w._show_track_osd('LIVE')
                logging.debug('LIVE reconnect started: generation=%s', w._media_generation)
            elif state in ('State.Ended', 'State.Error') or now >= self.deadline:
                self._fail('input failed or startup timed out')
            return
        if self.phase == 'waiting':
            return
        if state in ('State.Ended', 'State.Error'):
            self.ended(w._media_generation)
        elif w.player.is_playing() and not self.armed:
            if self.stable_since is None:
                self.stable_since = self.last_progress = now
                self.last_position = position_ms
            if position_ms >= 0 and position_ms != self.last_position:
                self.last_progress, self.last_position = now, position_ms
            if now - self.last_progress > 5:
                self.stable_since = None
            elif now - self.stable_since >= self.STABLE_SECONDS:
                self.armed = True
                logging.debug('LIVE reconnect rearmed after stable playback')
        elif not w.player.is_playing():
            self.stable_since = None

    def _fail(self, reason):
        self.timer.stop()
        self.phase = None
        self.failed = True
        self.armed = False
        try:
            self.window.player.stop()
        except (AttributeError, OSError, RuntimeError):
            logging.debug('Could not stop interrupted LIVE input', exc_info=True)
        self.window._set_standard_icon(self.window.btn_play, QStyle.SP_MediaPlay)
        self.window._update_live_indicator()
        self.window._show_track_osd(INTERRUPTED_MESSAGE)
        logging.warning('LIVE reconnect failed: %s', reason)
