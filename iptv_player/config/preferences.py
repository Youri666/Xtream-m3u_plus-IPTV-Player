"""Persistence for application preferences stored in userdata.ini."""

import configparser
from dataclasses import dataclass

from iptv_player.config.ini import read_config_file, write_config_file


INTERNAL_VLC_COMMAND = "<embedded-vlc>"


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
