from types import SimpleNamespace
import unittest

from iptv_player.stream_info import collect_stream_information


class _Stats:
    input_bitrate = 0.625
    demux_bitrate = 0.5


class _VlcModule:
    MediaStats = _Stats


class _Media:
    @staticmethod
    def get_stats(stats):
        stats.input_bitrate = 0.625
        stats.demux_bitrate = 0.5
        return True


class _Player:
    @staticmethod
    def get_media():
        return _Media()

    @staticmethod
    def video_get_size(_track):
        return 1920, 1080

    @staticmethod
    def get_fps():
        return 25.0

    @staticmethod
    def video_get_track_description():
        return [(0, b"Video track")]

    @staticmethod
    def video_get_track():
        return 0

    @staticmethod
    def audio_get_track_description():
        return [(1, b"French"), (2, b"English")]

    @staticmethod
    def audio_get_track():
        return 1

    @staticmethod
    def video_get_spu_description():
        return [(-1, b"Disable"), (4, b"English")]

    @staticmethod
    def video_get_spu():
        return -1


class StreamInformationTests(unittest.TestCase):
    def test_collects_information_through_player_methods(self):
        sections = collect_stream_information(_VlcModule, _Player(), "HTTPS")
        by_name = {name: dict(fields) for name, fields in sections}

        self.assertEqual(by_name["General"]["Protocol"], "HTTPS")
        self.assertEqual(by_name["General"]["Input bitrate"], "5.00 Mbps")
        self.assertEqual(by_name["Video"]["Resolution"], "1920 × 1080")
        self.assertEqual(by_name["Video"]["Frame rate"], "25 fps")
        self.assertEqual(by_name["Video"]["Active track"], "Video track")
        self.assertEqual(by_name["Audio"]["Available tracks"], "2")
        self.assertEqual(by_name["Audio"]["Active track"], "French")
        self.assertEqual(by_name["Subtitles"]["Available tracks"], "1")
        self.assertEqual(by_name["Subtitles"]["Active track"], "Disabled")

    def test_uses_demux_bitrate_when_input_bitrate_is_missing(self):
        class DemuxOnlyStats:
            input_bitrate = 0
            demux_bitrate = 0.25

        class DemuxOnlyMedia:
            @staticmethod
            def get_stats(_stats):
                return True

        class DemuxOnlyPlayer(_Player):
            @staticmethod
            def get_media():
                return DemuxOnlyMedia()

        vlc_module = SimpleNamespace(MediaStats=DemuxOnlyStats)
        sections = collect_stream_information(
            vlc_module, DemuxOnlyPlayer(), "HTTP"
        )
        by_name = {name: dict(fields) for name, fields in sections}

        self.assertEqual(by_name["General"]["Input bitrate"], "2.00 Mbps")

    def test_handles_information_that_is_not_available_yet(self):
        player = SimpleNamespace(
            video_get_size=lambda _track: (0, 0),
            get_fps=lambda: 0,
            get_media=lambda: None,
            video_get_track_description=lambda: [],
            video_get_track=lambda: -1,
            audio_get_track_description=lambda: [],
            audio_get_track=lambda: -1,
            video_get_spu_description=lambda: [],
            video_get_spu=lambda: -1,
        )
        sections = collect_stream_information(SimpleNamespace(), player, "HTTP")
        by_name = {name: dict(fields) for name, fields in sections}

        self.assertEqual(by_name["Video"]["Resolution"], "Not available")
        self.assertEqual(by_name["Audio"]["Active track"], "Not available")
        self.assertEqual(by_name["Subtitles"]["Active track"], "Disabled")


if __name__ == "__main__":
    unittest.main()
