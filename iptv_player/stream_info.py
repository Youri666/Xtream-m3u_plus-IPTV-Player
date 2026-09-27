"""Extract technical stream details through stable libVLC player methods."""


NOT_AVAILABLE = "Not available"


def collect_stream_information(vlc_module, player, protocol=""):
    """Return display-ready sections without accessing native track pointers."""
    sections = [("General", [("Protocol", protocol or NOT_AVAILABLE)])]

    resolution = _player_resolution(player)
    frame_rate = _format_frame_rate(_safe_call(player, "get_fps"))
    video_tracks = _track_descriptions(player, "video_get_track_description")
    video_fields = [
        ("Resolution", resolution),
        ("Frame rate", frame_rate),
        ("Available tracks", _track_count(video_tracks)),
    ]
    active_video = _active_track_name(
        video_tracks, _safe_call(player, "video_get_track")
    )
    if active_video != NOT_AVAILABLE:
        video_fields.append(("Active track", active_video))
    sections.append(("Video", video_fields))

    audio_tracks = _track_descriptions(player, "audio_get_track_description")
    sections.append(("Audio", [
        ("Available tracks", _track_count(audio_tracks)),
        ("Active track", _active_track_name(
            audio_tracks, _safe_call(player, "audio_get_track")
        )),
    ]))

    subtitle_tracks = _track_descriptions(player, "video_get_spu_description")
    sections.append(("Subtitles", [
        ("Available tracks", _track_count(subtitle_tracks, ignore_disabled=True)),
        ("Active track", _active_track_name(
            subtitle_tracks, _safe_call(player, "video_get_spu"),
            disabled_label="Disabled",
        )),
    ]))

    bitrate = _input_bitrate(vlc_module, player)
    if bitrate != NOT_AVAILABLE:
        sections[0][1].append(("Input bitrate", bitrate))
    return sections


def _track_descriptions(player, method_name):
    try:
        descriptions = getattr(player, method_name)() or []
        return [
            (_integer(track_id), _decode_text(name))
            for track_id, name in descriptions
        ]
    except Exception:
        return []


def _track_count(tracks, ignore_disabled=False):
    if not tracks:
        return NOT_AVAILABLE
    count = sum(1 for track_id, _name in tracks if not ignore_disabled or track_id >= 0)
    return str(count)


def _active_track_name(tracks, active_id, disabled_label=None):
    active_id = _integer(active_id)
    if disabled_label is not None and active_id < 0:
        return disabled_label
    for track_id, name in tracks:
        if track_id == active_id:
            return name
    return NOT_AVAILABLE


def _input_bitrate(vlc_module, player):
    media = _safe_call(player, "get_media")
    stats_type = getattr(vlc_module, "MediaStats", None)
    if media is None or stats_type is None:
        return NOT_AVAILABLE
    try:
        stats = stats_type()
        if not media.get_stats(stats):
            return NOT_AVAILABLE
        # libVLC reports these rates in megabytes per second. Some inputs only
        # populate the demux rate, so use it when the input rate is unavailable.
        megabytes_per_second = float(stats.input_bitrate)
        if megabytes_per_second <= 0:
            megabytes_per_second = float(stats.demux_bitrate)
        bits_per_second = megabytes_per_second * 8_000_000
        return _format_bitrate(bits_per_second)
    except Exception:
        return NOT_AVAILABLE


def _decode_text(value):
    if value in (None, "", b""):
        return NOT_AVAILABLE
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace") or NOT_AVAILABLE
    return str(value)


def _integer(value):
    try:
        return int(getattr(value, "value", value))
    except (TypeError, ValueError):
        return -1


def _format_bitrate(value):
    try:
        bitrate = max(0.0, float(value))
    except (TypeError, ValueError):
        return NOT_AVAILABLE
    if bitrate <= 0:
        return NOT_AVAILABLE
    if bitrate >= 1_000_000:
        return f"{bitrate / 1_000_000:.2f} Mbps"
    return f"{bitrate / 1_000:.0f} kbps"


def _format_frame_rate(value):
    try:
        frame_rate = float(value)
    except (TypeError, ValueError):
        return NOT_AVAILABLE
    if frame_rate <= 0:
        return NOT_AVAILABLE
    return f"{frame_rate:.3f}".rstrip("0").rstrip(".") + " fps"


def _player_resolution(player):
    try:
        width, height = player.video_get_size(0)
        width = max(0, int(width))
        height = max(0, int(height))
        return f"{width} × {height}" if width and height else NOT_AVAILABLE
    except Exception:
        return NOT_AVAILABLE


def _safe_call(obj, method_name):
    try:
        return getattr(obj, method_name)()
    except Exception:
        return None
