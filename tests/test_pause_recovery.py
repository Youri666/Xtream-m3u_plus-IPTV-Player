"""VOD pause recovery is shared by manual and minimize paths; LIVE stays native."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PyQt5.QtCore import QEvent
from iptv_player.ui.player import EmbeddedPlayerWindow, _resume_position_reached


class PauseRecoveryTests(unittest.TestCase):
    def window(self, live=False):
        window = SimpleNamespace(player=Mock(), btn_play=object(), title_label=Mock(),
            _current_url="https://example.test/movie", _pause_started_at=None,
            _pause_position_ms=0, _recovering_after_pause=False, _pause_recovery_failed=False,
            _deferred_keep_topmost=False, _paused_by_minimize=False,
            _is_live_playback=lambda: live, _set_standard_icon=Mock(), _wake_controls=Mock(),
            _store_current_playlist_progress=Mock(), _show_track_osd=Mock(), _update_live_indicator=Mock(),
            play_url=Mock(), next=Mock(), isVisible=lambda: True,
            _auto_play_next=True, _auto_advance_triggered=False, _auto_advance_seconds=20,
            _current_idx=0, _playlist=[{}, {}], _current_history={"type": "LIVE" if live else "Series"})
        window.player.get_time.return_value=45000
        window.title_label.text.return_value="Episode"
        window._pause_playback=lambda: EmbeddedPlayerWindow._pause_playback(window)
        window._resume_playback=lambda: EmbeddedPlayerWindow._resume_playback(window)
        window._fail_pause_recovery=lambda: EmbeddedPlayerWindow._fail_pause_recovery(window)
        return window

    def test_long_pause_reopens_same_url_at_exact_position_without_prompt(self):
        window=self.window()
        with patch("iptv_player.ui.player.time.monotonic", return_value=100):
            window._pause_playback()
        with patch("iptv_player.ui.player.time.monotonic", return_value=130):
            window._resume_playback()
        window.player.stop.assert_called_once()
        window.play_url.assert_called_once_with("https://example.test/movie", "Episode", resume_ms=45000, keep_above_main=False)
        self.assertTrue(window._recovering_after_pause)
        self.assertEqual(window._pause_recovery_target_ms,45000)

    def test_short_pause_and_live_never_reopen_media(self):
        for live, elapsed in ((False,10),(False,29.9),(True,600)):
            window=self.window(live)
            with patch("iptv_player.ui.player.time.monotonic",return_value=100):
                window._pause_playback()
            with patch("iptv_player.ui.player.time.monotonic",return_value=100+elapsed):
                window._resume_playback()
            window.play_url.assert_not_called()
            window.player.stop.assert_not_called()
            window.player.play.assert_called_once()

    def test_reconnection_and_failure_cannot_advance_or_skip_credits(self):
        window=self.window()
        for recovering, failed in ((True,False),(False,True)):
            window._pause_started_at=None
            window._recovering_after_pause=recovering
            window._pause_recovery_failed=failed
            window._media_generation=3
            EmbeddedPlayerWindow._advance_after_media_end(window,3)
            self.assertFalse(EmbeddedPlayerWindow._maybe_auto_advance(window,119000,120000))
        window.next.assert_not_called()

    def test_resume_must_reach_saved_position_and_timeout_stays_on_episode(self):
        window=self.window()
        window._recovering_after_pause=True
        window._pause_recovery_target_ms=45000
        window._pause_recovery_deadline=200
        window.player.is_playing.return_value=True
        with patch("iptv_player.ui.player.time.monotonic",return_value=150):
            EmbeddedPlayerWindow._check_pause_recovery(window,0)
            self.assertTrue(window._recovering_after_pause)
            EmbeddedPlayerWindow._check_pause_recovery(window,45000)
            self.assertFalse(window._recovering_after_pause)
        window._recovering_after_pause=True
        with patch("iptv_player.ui.player.time.monotonic",return_value=201):
            EmbeddedPlayerWindow._check_pause_recovery(window,0)
        self.assertTrue(window._pause_recovery_failed)
        window.next.assert_not_called()
        window._show_track_osd.assert_called_once()

    def test_minimize_and_restore_use_the_shared_pause_and_resume_functions(self):
        from PyQt5.QtWidgets import QApplication, QMainWindow
        app=QApplication.instance() or QApplication([])
        window=EmbeddedPlayerWindow.__new__(EmbeddedPlayerWindow)
        QMainWindow.__init__(window)
        window.player=Mock()
        window.player.is_playing.return_value=True
        window._paused_by_minimize=False
        window._pause_playback=Mock()
        window._resume_playback=Mock()
        window.isMinimized=Mock(return_value=True)
        event=QEvent(QEvent.WindowStateChange)
        EmbeddedPlayerWindow.changeEvent(window,event)
        window._pause_playback.assert_called_once()
        self.assertTrue(window._paused_by_minimize)
        window.isMinimized.return_value=False
        EmbeddedPlayerWindow.changeEvent(window,event)
        window._resume_playback.assert_called_once()
        self.assertFalse(window._paused_by_minimize)
        # A manual pause must not be resumed merely by restoring the window.
        window.player.is_playing.return_value=False
        window.isMinimized.return_value=True
        EmbeddedPlayerWindow.changeEvent(window,event)
        window.isMinimized.return_value=False
        EmbeddedPlayerWindow.changeEvent(window,event)
        self.assertEqual(window._resume_playback.call_count,1)
        window.deleteLater()

    def test_recovery_accepts_playback_already_beyond_saved_position(self):
        for position in (45760, 75000):
            with self.subTest(position=position):
                window = self.window()
                window._recovering_after_pause = True
                window._pause_recovery_target_ms = 45000
                window._pause_recovery_deadline = 200
                window._pending_resume_ms = 45000
                window._pending_resume_attempts = 20
                window.player.is_playing.return_value = True
                with patch('iptv_player.ui.player.time.monotonic', return_value=201):
                    EmbeddedPlayerWindow._check_pause_recovery(window, position)
                self.assertFalse(window._recovering_after_pause)
                self.assertEqual(window._pending_resume_ms, 0)
                self.assertEqual(window._pending_resume_attempts, 0)
                window.player.stop.assert_not_called()
                window._show_track_osd.assert_not_called()

    def test_shared_resume_criterion_rejects_unavailable_or_too_early_positions(self):
        self.assertFalse(_resume_position_reached(-1, 100))
        self.assertFalse(_resume_position_reached(0, 45000))
        self.assertFalse(_resume_position_reached(44499, 45000))
        self.assertTrue(_resume_position_reached(44500, 45000))
        self.assertTrue(_resume_position_reached(45760, 45000))

    def test_pending_recovery_diagnostics_are_bounded_and_include_positions(self):
        window = self.window()
        window._recovering_after_pause = True
        window._pause_recovery_target_ms = 45000
        window._pause_recovery_deadline = 200
        window.player.is_playing.return_value = False
        with self.assertLogs(level='DEBUG') as captured:
            for now in (150, 151, 152, 156):
                with patch('iptv_player.ui.player.time.monotonic', return_value=now):
                    EmbeddedPlayerWindow._check_pause_recovery(window, 0)
        self.assertEqual(len(captured.output), 2)
        self.assertIn('target_ms=45000', captured.output[0])
        self.assertIn('position_ms=0', captured.output[0])
