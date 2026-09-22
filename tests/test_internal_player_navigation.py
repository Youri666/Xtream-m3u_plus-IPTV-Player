import unittest

from iptv_player.ui.player import EmbeddedPlayerWindow


class _FakePlayerWindow:
    def __init__(self, *, enabled=True, seconds=20, content_type="SERIES"):
        self._auto_play_next = enabled
        self._auto_advance_triggered = False
        self._auto_advance_seconds = seconds
        self._current_idx = 0
        self._playlist = [{"name": "One"}, {"name": "Two"}]
        self._current_history = {"type": content_type}
        self.advance_count = 0

    def next(self):
        self.advance_count += 1


class _FakeTimer:
    def __init__(self):
        self.active = False

    def isActive(self):
        return self.active

    def start(self):
        self.active = True

    def stop(self):
        self.active = False


class _FakeMediaPlayer:
    def __init__(self, position, duration):
        self.position = position
        self.duration = duration

    def get_time(self):
        return self.position

    def get_length(self):
        return self.duration

    def set_time(self, position):
        self.position = position


class _FakeSlider:
    def __init__(self):
        self.value = 0

    def setValue(self, value):
        self.value = value


class _FakeSeekWindow:
    def __init__(self, position, duration):
        self.player = _FakeMediaPlayer(position, duration)
        self._wheel_seek_timer = _FakeTimer()
        self._track_osd_timer = _FakeTimer()
        self._seek_osd_active = False
        self._seek_osd_total_ms = 0
        self._seek_target_ms = 0
        self._seek_sequence_origin_ms = 0
        self.seek_slider = _FakeSlider()
        self.osd_text = ""

    def _show_track_osd(self, text, seek=False):
        self.osd_text = text
        self._seek_osd_active = seek
        self._track_osd_timer.start()

    def _wake_controls(self):
        pass

    def _fmt_ms(self, value):
        return EmbeddedPlayerWindow._fmt_ms(value)

    def _commit_wheel_seek(self):
        EmbeddedPlayerWindow._commit_wheel_seek(self)


class InternalPlayerNavigationTests(unittest.TestCase):
    def test_advances_once_inside_configured_end_window(self):
        player = _FakePlayerWindow(seconds=20)

        advanced = EmbeddedPlayerWindow._maybe_auto_advance(
            player, 101_000, 120_000
        )
        repeated = EmbeddedPlayerWindow._maybe_auto_advance(
            player, 102_000, 120_000
        )

        self.assertTrue(advanced)
        self.assertFalse(repeated)
        self.assertEqual(player.advance_count, 1)

    def test_does_not_advance_live_or_disabled_playback(self):
        live = _FakePlayerWindow(content_type="LIVE")
        disabled = _FakePlayerWindow(enabled=False)

        self.assertFalse(
            EmbeddedPlayerWindow._maybe_auto_advance(live, 119_000, 120_000)
        )
        self.assertFalse(
            EmbeddedPlayerWindow._maybe_auto_advance(disabled, 119_000, 120_000)
        )

    def test_keyboard_seek_stays_at_start_without_accumulating_extra_steps(self):
        player = _FakeSeekWindow(5_000, 120_000)

        EmbeddedPlayerWindow.seek_by(player, -10_000)
        EmbeddedPlayerWindow.seek_by(player, -10_000)

        self.assertEqual(player.player.position, 0)
        self.assertEqual(player._seek_osd_total_ms, -5_000)
        self.assertIn("−5 seconds", player.osd_text)

    def test_wheel_seek_is_deferred_and_clamped_to_media_end(self):
        player = _FakeSeekWindow(115_000, 120_000)

        EmbeddedPlayerWindow.preview_wheel_seek(player, 10_000)
        EmbeddedPlayerWindow.preview_wheel_seek(player, 10_000)

        self.assertEqual(player.player.position, 115_000)
        self.assertEqual(player._seek_target_ms, 120_000)
        self.assertEqual(player._seek_osd_total_ms, 5_000)
        EmbeddedPlayerWindow._commit_wheel_seek(player)
        self.assertEqual(player.player.position, 120_000)


if __name__ == "__main__":
    unittest.main()
