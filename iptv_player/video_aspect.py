"""Read display proportions through the documented libVLC 3 track ABI."""
import ctypes
import math
import logging

from iptv_player.config.internal_player import VIDEO_ASPECT_RATIOS


class _VideoTrackPrefix(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint) for name in
                ('height', 'width', 'sar_num', 'sar_den', 'fps_num', 'fps_den')] + [('orientation', ctypes.c_int)]


class _TrackPrefix(ctypes.Structure):
    # libvlc_media_track_t has ONE anonymous pointer union, not three sequential
    # pointers as exposed by some python-vlc releases. Only read the stable prefix.
    _fields_ = [('codec', ctypes.c_uint32), ('fourcc', ctypes.c_uint32),
                ('id', ctypes.c_int), ('type', ctypes.c_int),
                ('profile', ctypes.c_int), ('level', ctypes.c_int),
                ('video', ctypes.POINTER(_VideoTrackPrefix))]


def _report_aspect(player, reason, details):
    """Log metadata changes only, without media URLs or provider credentials."""
    signature = (reason, details)
    if getattr(player, '_window_aspect_diagnostic', None) != signature:
        player._window_aspect_diagnostic = signature
        logging.debug('Window aspect metadata: reason=%s; %s', reason, details)


def display_aspect_ratio(vlc, player, selected='Auto'):
    """Return a forced ratio or native display ratio, never guessing square pixels."""
    forced = VIDEO_ASPECT_RATIOS.get(selected, '')
    if forced:
        numerator, denominator = forced.split(':')
        return float(numerator) / float(denominator)
    buffer = ctypes.c_void_p()
    count = 0
    media = None
    try:
        version = vlc.libvlc_get_version()
        if not isinstance(version, (str, bytes)) or not version.startswith(('3.',) if isinstance(version, str) else (b'3.',)):
            _report_aspect(player, 'unsupported-libvlc-version', repr(version))
            return None
        width, height = player.video_get_size(0)
        media = player.get_media()
        if media is None:
            _report_aspect(player, 'no-media', f'legacy_size={width}x{height}')
            return None
        # The wrapper's parameter type is opaque here: libVLC writes an allocated
        # array of pointers. Cast it only after allocation, then always release it.
        out_type = ctypes.POINTER(ctypes.POINTER(vlc.MediaTrack))
        count = vlc.libvlc_media_tracks_get(media, ctypes.cast(ctypes.byref(buffer), out_type))
        tracks = ctypes.cast(buffer, ctypes.POINTER(ctypes.POINTER(_TrackPrefix)))
        active = player.video_get_track()
        videos = []
        result = None
        reason = 'no-matching-video-track'
        video_tracks = [tracks[index].contents for index in range(count)
                        if tracks[index].contents.type == 1 and tracks[index].contents.video]
        sole_video = len(video_tracks) == 1
        for index in range(count):
            track = tracks[index].contents
            if track.type != 1 or not track.video:
                continue
            video = track.video.contents
            videos.append((track.id, video.width, video.height, video.sar_num,
                           video.sar_den, video.orientation))
            # Live ES IDs and media metadata IDs can differ (e.g. 256 vs 0).
            # A single video track is unambiguous. With several tracks, require
            # the selected ID rather than borrowing another track's format.
            if active >= 0 and track.id != active and not sole_video:
                continue
            if not video.width or not video.height or not video.sar_num or not video.sar_den:
                reason = 'incomplete-video-metadata'
                continue
            ratio = video.width * video.sar_num / (video.height * video.sar_den)
            if video.orientation in (4, 5, 6, 7):
                ratio = 1 / ratio
            result = ratio if math.isfinite(ratio) and 0.05 <= ratio <= 20 else None
            reason = ('resolved-single-video-track' if active >= 0 and track.id != active
                      else 'resolved') if result is not None else 'invalid-ratio'
            break
        if not width or not height:
            result = None
            reason = 'legacy-video-size-unavailable'
        details = (f'legacy_size={width}x{height}; selected_track={active}; '
                   f'track_count={count}; videos(id,width,height,SAR_num,SAR_den,orientation)={videos}; '
                   f'display_ratio={result}')
        _report_aspect(player, reason, details)
        return result
    except (AttributeError, OSError, TypeError, ValueError, ZeroDivisionError) as error:
        _report_aspect(player, 'metadata-read-error', type(error).__name__)
        return None
    finally:
        if count and buffer.value:
            vlc.libvlc_media_tracks_release(ctypes.cast(buffer, ctypes.POINTER(ctypes.POINTER(vlc.MediaTrack))), count)
        if media is not None:
            # get_media() retains a native reference on every call.
            media.release()
