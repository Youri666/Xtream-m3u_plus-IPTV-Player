"""Read the native pointer union safely and release every libVLC track allocation."""
import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from iptv_player.video_aspect import display_aspect_ratio, _VideoTrackPrefix, _TrackPrefix


class VideoAspectTests(unittest.TestCase):
    def fixture(self, sar_num=64, sar_den=45, orientation=0, video_ids=(7,)):
        video = _VideoTrackPrefix(576, 720, sar_num, sar_den, 25, 1, orientation)
        track_objects = [_TrackPrefix(0, 0, track_id, 1, 0, 0, ctypes.pointer(video))
                         for track_id in video_ids]
        array = (ctypes.POINTER(_TrackPrefix) * len(track_objects))(
            *(ctypes.pointer(track) for track in track_objects))
        def get_tracks(media, output):
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p)).contents.value = ctypes.addressof(array)
            return len(track_objects)
        vlc = SimpleNamespace(MediaTrack=_TrackPrefix,
            libvlc_get_version=lambda: b'3.0.24', libvlc_media_tracks_get=get_tracks,
            libvlc_media_tracks_release=Mock())
        player = SimpleNamespace(video_get_size=lambda index:(720,576),get_media=Mock(return_value=SimpleNamespace(release=Mock())),video_get_track=lambda:7)
        return vlc, player

    def test_anamorphic_and_rotated_video_use_display_ratio(self):
        vlc, player = self.fixture()
        self.assertAlmostEqual(display_aspect_ratio(vlc,player),16/9)
        vlc.libvlc_media_tracks_release.assert_called_once()
        player.get_media.return_value.release.assert_called_once()
        vlc, player = self.fixture(orientation=5)
        self.assertAlmostEqual(display_aspect_ratio(vlc,player),9/16)

    def test_unknown_pixel_ratio_is_not_assumed_square(self):
        vlc, player = self.fixture(0,0)
        self.assertIsNone(display_aspect_ratio(vlc,player))
        vlc.libvlc_media_tracks_release.assert_called_once()
        player.get_media.return_value.release.assert_called_once()

    def test_allocation_is_released_if_track_selection_fails(self):
        vlc, player = self.fixture()
        player.video_get_track=Mock(side_effect=ValueError('test failure'))
        self.assertIsNone(display_aspect_ratio(vlc,player))
        vlc.libvlc_media_tracks_release.assert_called_once()
        player.get_media.return_value.release.assert_called_once()

    def test_forced_format_needs_no_native_track_pointers(self):
        self.assertAlmostEqual(display_aspect_ratio(None,None,'2.39:1'),2.39)

    def test_unknown_libvlc_abi_is_not_dereferenced(self):
        vlc, player = self.fixture()
        vlc.libvlc_get_version=lambda:b'4.0.0'
        self.assertIsNone(display_aspect_ratio(vlc,player))
        vlc.libvlc_media_tracks_release.assert_not_called()

    def test_single_live_video_track_resolves_despite_different_es_id(self):
        vlc, player = self.fixture(video_ids=(0,))
        player.video_get_track = lambda: 256
        with self.assertLogs(level='DEBUG') as captured:
            self.assertAlmostEqual(display_aspect_ratio(vlc, player), 16/9)
        self.assertIn('resolved-single-video-track', captured.output[0])
        self.assertIn('selected_track=256', captured.output[0])
        player.get_media.return_value.release.assert_called_once()
        vlc.libvlc_media_tracks_release.assert_called_once()

    def test_multiple_video_tracks_still_require_selected_id(self):
        vlc, player = self.fixture(video_ids=(0, 1))
        player.video_get_track = lambda: 256
        with self.assertLogs(level='DEBUG') as captured:
            self.assertIsNone(display_aspect_ratio(vlc, player))
        self.assertIn('no-matching-video-track', captured.output[0])

    def test_single_video_track_with_missing_sar_is_still_unknown(self):
        vlc, player = self.fixture(0, 0, video_ids=(0,))
        player.video_get_track = lambda: 256
        self.assertIsNone(display_aspect_ratio(vlc, player))

    def test_missing_legacy_size_logs_track_metadata_without_changing_behavior(self):
        vlc, player = self.fixture()
        player.video_get_size = lambda index: (0, 0)
        with self.assertLogs(level='DEBUG') as captured:
            self.assertIsNone(display_aspect_ratio(vlc, player))
        self.assertIn('legacy-video-size-unavailable', captured.output[0])
        self.assertIn('(7, 720, 576, 64, 45, 0)', captured.output[0])

    def test_identical_diagnostics_are_not_repeated_on_each_poll(self):
        vlc, player = self.fixture(0, 0)
        with self.assertLogs(level='DEBUG') as captured:
            display_aspect_ratio(vlc, player)
            display_aspect_ratio(vlc, player)
        self.assertEqual(len(captured.output), 1)
        self.assertIn('incomplete-video-metadata', captured.output[0])
