"""Persistence for application preferences stored in userdata.ini."""

import configparser
from dataclasses import dataclass

from iptv_player.config.ini import read_config_file, write_config_file
from iptv_player.constants import REMEMBER_LIST_SORTING


INTERNAL_VLC_COMMAND = "<embedded-vlc>"
CONTENT_TYPES = ("LIVE", "Movies", "Series")
THEME_MODES = ("System", "Light", "Dark")
LEGACY_REMEMBER_SORTING = "Remember per category"


@dataclass(frozen=True)
class PlayerPreference:
    """Describe the active and most recently selected external player."""

    command: str = ""
    last_external_command: str = ""
    configured: bool = False


def load_player_preference(filename):
    """Load the media player selection with safe defaults."""
    try:
        config = read_config_file(filename)
    except (configparser.Error, UnicodeDecodeError):
        return PlayerPreference()
    if not config.has_option("ExternalPlayer", "Command"):
        return PlayerPreference()

    command = config.get("ExternalPlayer", "Command", fallback="")
    remembered = config.get(
        "ExternalPlayer", "LastExternalCommand", fallback=""
    )
    if command and command != INTERNAL_VLC_COMMAND:
        remembered = command
    return PlayerPreference(command, remembered, True)


def save_player_preference(filename, command, last_external_command=""):
    """Persist the active player and remembered external executable."""
    try:
        config = read_config_file(filename)
    except (configparser.Error, UnicodeDecodeError):
        config = configparser.ConfigParser()
    config["ExternalPlayer"] = {
        "Command": command,
        "LastExternalCommand": last_external_command,
    }
    write_config_file(filename, config)


def load_auto_update_preference(filename):
    """Return the saved automatic update choice, or None when absent."""
    try:
        config = read_config_file(filename)
    except (configparser.Error, UnicodeDecodeError):
        return None
    if not config.has_option("Updater", "auto-update-checker"):
        return None
    return config.get("Updater", "auto-update-checker") == "True"


def save_auto_update_preference(filename, enabled):
    """Persist whether IPTV Player checks for updates automatically."""
    try:
        config = read_config_file(filename)
    except (configparser.Error, UnicodeDecodeError):
        config = configparser.ConfigParser()
    config["Updater"] = {"auto-update-checker": bool(enabled)}
    write_config_file(filename, config)


def load_theme_preference(filename):
    """Load a supported theme mode, defaulting to the operating system theme."""
    config = _load_config(filename)
    mode = config.get("Theme", "mode", fallback="System")
    return mode if mode in THEME_MODES else "System"


def save_theme_preference(filename, mode):
    """Persist a validated application theme mode."""
    _save_section(
        filename, "Theme", {"mode": mode if mode in THEME_MODES else "System"}
    )


def load_content_preferences(filename):
    """Load independent content switches with the legacy VOD fallback."""
    config = _load_config(filename)
    if config.has_section("Content"):
        return {
            stream_type: _read_boolean(config, "Content", stream_type, True)
            for stream_type in CONTENT_TYPES
        }
    vod_enabled = _read_boolean(config, "VOD", "enabled", True)
    return {"LIVE": True, "Movies": vod_enabled, "Series": vod_enabled}


def save_content_preferences(filename, preferences):
    """Persist all content switches as one consistent snapshot."""
    _save_section(
        filename,
        "Content",
        {
            stream_type: bool(preferences.get(stream_type, True))
            for stream_type in CONTENT_TYPES
        },
    )


def load_sorting_preference(filename):
    """Load the global catalog sorting mode used by the Settings page."""
    config = _load_config(filename)
    value = config.get("Sorting order", "Order", fallback="")
    if value == LEGACY_REMEMBER_SORTING:
        return REMEMBER_LIST_SORTING
    return value or "Sorting disabled"


def save_sorting_preference(filename, sorting_order):
    """Persist global sorting and remove the obsolete global category section."""
    config = _load_config(filename)
    config["Sorting order"] = {"Order": sorting_order}
    config.remove_section("Category sorting")
    write_config_file(filename, config)


def load_stream_status_preference(filename):
    """Load whether live-stream availability probes are enabled."""
    return _read_boolean(_load_config(filename), "StreamStatus", "enabled", True)


def _load_config(filename):
    """Load user preferences while tolerating a malformed INI file."""
    try:
        return read_config_file(filename)
    except (configparser.Error, UnicodeDecodeError):
        return configparser.ConfigParser()


def _save_section(filename, section, values):
    """Replace one preference section while preserving unrelated settings."""
    config = _load_config(filename)
    config[section] = values
    write_config_file(filename, config)


def _read_boolean(config, section, option, fallback):
    """Read one boolean preference independently from malformed neighbours."""
    try:
        return config.getboolean(section, option, fallback=fallback)
    except (ValueError, configparser.Error):
        return fallback
