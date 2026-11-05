"""Persistence and validation for internal-player preferences."""

import configparser
from dataclasses import dataclass

from iptv_player.config.ini import read_config_file, write_config_file
from iptv_player.constants import (
    DEFAULT_INTERNAL_AUTO_ADVANCE_SECONDS,
    DEFAULT_INTERNAL_AUTO_PLAY_NEXT,
    DEFAULT_INTERNAL_NETWORK_CACHING_MS,
    DEFAULT_RESUME_BEHAVIOR,
    DEFAULT_INTERNAL_SEEK_STEP_SECONDS,
    DEFAULT_INTERNAL_SPEED_STEP,
    DEFAULT_INTERNAL_VOLUME_STEP_PERCENT,
    MEDIA_LANGUAGE_OPTIONS,
    RESUME_BEHAVIORS,
)


VIDEO_ASPECT_RATIOS = {
    "Auto": "", "16:9": "16:9", "4:3": "4:3", "1:1": "1:1",
    "16:10": "16:10", "2.21:1": "221:100", "2.35:1": "235:100",
    "2.39:1": "239:100", "5:4": "5:4",
}


def load_video_format(filename):
    """Read the player toolbar's persistent aspect-ratio selection."""
    try:
        value = _load_config(filename).get("InternalPlayer", "video_format", fallback="Auto")
    except configparser.Error:
        value = "Auto"
    return value if value in VIDEO_ASPECT_RATIOS else "Auto"


def save_video_format(filename, value):
    """Preserve other settings when the isolated player changes video format."""
    if value not in VIDEO_ASPECT_RATIOS:
        raise ValueError("Unsupported video format")
    config = _load_config(filename)
    if not config.has_section("InternalPlayer"):
        config.add_section("InternalPlayer")
    config.set("InternalPlayer", "video_format", value)
    write_config_file(filename, config)


def load_window_aspect_lock(filename):
    """Default to a locked window without adding an Advanced-settings option."""
    return _boolean(_load_config(filename), "window_aspect_locked", True)


def save_window_aspect_lock(filename, enabled):
    """Persist the toolbar lock while retaining all other preferences."""
    config = _load_config(filename)
    if not config.has_section("InternalPlayer"):
        config.add_section("InternalPlayer")
    config.set("InternalPlayer", "window_aspect_locked", str(bool(enabled)))
    write_config_file(filename, config)


@dataclass(frozen=True)
class InternalPlayerPreferences:
    """Hold the user-adjustable controls passed to the player process."""

    seek_step_seconds: int = DEFAULT_INTERNAL_SEEK_STEP_SECONDS
    volume_step_percent: int = DEFAULT_INTERNAL_VOLUME_STEP_PERCENT
    speed_step: float = DEFAULT_INTERNAL_SPEED_STEP
    audio_language: str = ""
    subtitle_language: str = ""
    resume_behavior: str = DEFAULT_RESUME_BEHAVIOR
    auto_play_next: bool = DEFAULT_INTERNAL_AUTO_PLAY_NEXT
    auto_advance_seconds: int = DEFAULT_INTERNAL_AUTO_ADVANCE_SECONDS
    network_caching_ms: int = DEFAULT_INTERNAL_NETWORK_CACHING_MS


def load_internal_player_preferences(filename):
    """Load bounded player controls while tolerating manual INI edits."""
    config = _load_config(filename)
    valid_languages = {code for _, code in MEDIA_LANGUAGE_OPTIONS}
    audio_language = config.get("InternalPlayer", "audio_language", fallback="")
    subtitle_language = config.get(
        "InternalPlayer", "subtitle_language", fallback=""
    )
    return InternalPlayerPreferences(
        seek_step_seconds=_bounded_int(
            config, "seek_step_seconds", DEFAULT_INTERNAL_SEEK_STEP_SECONDS, 1, 300
        ),
        volume_step_percent=_bounded_int(
            config,
            "volume_step_percent",
            DEFAULT_INTERNAL_VOLUME_STEP_PERCENT,
            1,
            25,
        ),
        speed_step=_bounded_float(
            config, "speed_step", DEFAULT_INTERNAL_SPEED_STEP, 0.05, 1.0
        ),
        audio_language=(
            audio_language if audio_language in valid_languages else ""
        ),
        subtitle_language=(
            subtitle_language
            if subtitle_language in valid_languages | {"disabled"}
            else ""
        ),
        resume_behavior=_choice(
            config,
            "resume_behavior",
            DEFAULT_RESUME_BEHAVIOR,
            RESUME_BEHAVIORS,
        ),
        auto_play_next=_boolean(
            config, "auto_play_next", DEFAULT_INTERNAL_AUTO_PLAY_NEXT
        ),
        auto_advance_seconds=_bounded_int(
            config,
            "auto_advance_seconds",
            DEFAULT_INTERNAL_AUTO_ADVANCE_SECONDS,
            0,
            300,
        ),
        network_caching_ms=_bounded_int(
            config,
            "network_caching_ms",
            DEFAULT_INTERNAL_NETWORK_CACHING_MS,
            0,
            60000,
        ),
    )


def save_internal_player_preferences(filename, preferences):
    """Persist controls while preserving runtime volume and playback rate."""
    config = _load_config(filename)
    saved_volume = config.get("InternalPlayer", "volume", fallback="80")
    saved_rate = config.get("InternalPlayer", "playback_rate", fallback="1.0")
    saved_format = load_video_format(filename)
    config["InternalPlayer"] = {
        "seek_step_seconds": str(preferences.seek_step_seconds),
        "volume_step_percent": str(preferences.volume_step_percent),
        "speed_step": str(preferences.speed_step),
        "audio_language": preferences.audio_language,
        "subtitle_language": preferences.subtitle_language,
        "resume_behavior": preferences.resume_behavior,
        "auto_play_next": str(preferences.auto_play_next),
        "auto_advance_seconds": str(preferences.auto_advance_seconds),
        "network_caching_ms": str(preferences.network_caching_ms),
        "volume": saved_volume,
        "playback_rate": saved_rate,
        "video_format": saved_format,
        "window_aspect_locked": str(load_window_aspect_lock(filename)),
    }
    write_config_file(filename, config)


def _load_config(filename):
    """Load the shared configuration or return an empty parser on corruption."""
    try:
        return read_config_file(filename)
    except (configparser.Error, UnicodeDecodeError):
        return configparser.ConfigParser()


def _bounded_int(config, option, fallback, minimum, maximum):
    """Read and clamp one integer control."""
    try:
        value = config.getint("InternalPlayer", option, fallback=fallback)
    except (ValueError, configparser.Error):
        value = fallback
    return max(minimum, min(value, maximum))


def _bounded_float(config, option, fallback, minimum, maximum):
    """Read, round, and clamp one floating-point control."""
    try:
        value = config.getfloat("InternalPlayer", option, fallback=fallback)
    except (ValueError, configparser.Error):
        value = fallback
    return max(minimum, min(round(value, 2), maximum))


def _choice(config, option, fallback, allowed_values):
    """Read one string option and reject values outside its documented choices."""
    value = config.get("InternalPlayer", option, fallback=fallback)
    return value if value in allowed_values else fallback


def _boolean(config, option, fallback):
    """Read one boolean option while tolerating invalid manual edits."""
    try:
        return config.getboolean("InternalPlayer", option, fallback=fallback)
    except (ValueError, configparser.Error):
        return fallback
