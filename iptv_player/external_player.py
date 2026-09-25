"""Cross-platform external media player command construction and launching."""

import logging
import os
from os import path
import subprocess
import sys

from iptv_player.config.paths import macos_bundle_executable


class ExternalPlayerNotExecutableError(PermissionError):
    """Indicate that the selected Linux player cannot be executed."""


def external_player_display_name(player):
    """Return a concise display name for a selected external player."""
    filename = (player or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    filename_lower = filename.lower()
    if filename_lower in ("vlc", "vlc.exe"):
        return "VLC Player"
    if filename_lower in ("smplayer", "smplayer.exe"):
        return "SMPlayer"
    if filename_lower == "totem":
        return "Totem (GNOME Videos)"

    if filename_lower.endswith(".app"):
        filename = filename[:-4]
    elif "." in filename:
        filename = filename.rsplit(".", 1)[0]
    return filename or "External player"


def external_player_environment(environment=None, platform=None):
    """Return an environment isolated from this application's Qt runtime."""
    platform = platform or sys.platform
    child_environment = dict(os.environ if environment is None else environment)
    for variable in (
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
        "QT_QPA_PLATFORM",
        "QML2_IMPORT_PATH",
    ):
        child_environment.pop(variable, None)

    # Frozen applications may temporarily replace the system library search path.
    # Restore its original value before starting an independently installed player.
    library_path = None
    if platform.startswith("linux"):
        library_path = "LD_LIBRARY_PATH"
    elif platform.startswith("darwin"):
        library_path = "DYLD_LIBRARY_PATH"
    if library_path:
        original = child_environment.pop(f"{library_path}_ORIG", None)
        if original is not None:
            child_environment[library_path] = original

    return child_environment


def external_player_command(
    player, stream_url, user_agent="", title="", platform=None
):
    """Build the platform-specific command used to open a stream."""
    platform = platform or sys.platform
    user_agent = (user_agent or "").strip()
    title = (title or "").strip()
    player_lower = player.lower()

    if platform.startswith("linux"):
        if not os.access(player, os.X_OK):
            raise ExternalPlayerNotExecutableError(
                f"Selected player is not executable: {player}"
            )
        command = [player]
        if player_lower.endswith("vlc"):
            if user_agent:
                command.append(f"--http-user-agent={user_agent}")
            if title:
                command.append(f"--meta-title={title}")
                command.append(f"--input-title-format={title}")
        elif player_lower.endswith(("mpv", "mpv.com")) and user_agent:
            command.append(f"--user-agent={user_agent}")
        elif path.basename(player).lower() == "smplayer" and title:
            command.extend(["-media-title", title])
        command.append(stream_url)
        return command

    if platform.startswith("win"):
        quoted_player = f'"{player}"'
        quoted_url = f'"{stream_url}"'
        if "potplayermini64.exe" in player_lower or "potplayer" in player_lower:
            user_agent_argument = (
                f' /user_agent="{user_agent}"' if user_agent else ""
            )
            return f"{quoted_player} {quoted_url}{user_agent_argument}"
        if player_lower.endswith(("mpv.exe", "mpv.com")) or "\\mpv\\" in player_lower:
            user_agent_argument = (
                f' --user-agent="{user_agent}"' if user_agent else ""
            )
            return f"{quoted_player}{user_agent_argument} {quoted_url}"
        if player_lower.endswith("vlc.exe"):
            user_agent_argument = (
                f' --http-user-agent="{user_agent}"' if user_agent else ""
            )
            title_argument = (
                " " + subprocess.list2cmdline([
                    f"--meta-title={title}",
                    f"--input-title-format={title}",
                ])
                if title else ""
            )
            return (
                f"{quoted_player}{user_agent_argument}{title_argument} "
                f"{quoted_url}"
            )
        if player_lower.endswith("smplayer.exe"):
            arguments = [player]
            if title:
                arguments.extend(["-media-title", title])
            arguments.append(stream_url)
            return subprocess.list2cmdline(arguments)
        return f"{quoted_player} {quoted_url}"

    if platform.startswith("darwin"):
        executable = player
        if player_lower.endswith(".app") and path.isdir(player):
            executable = macos_bundle_executable(player)
        command = [executable]
        if path.basename(executable).lower() == "vlc":
            if user_agent:
                command.append(f"--http-user-agent={user_agent}")
            if title:
                command.append(f"--meta-title={title}")
                command.append(f"--input-title-format={title}")
        elif path.basename(executable).lower() == "smplayer" and title:
            command.extend(["-media-title", title])
        command.append(stream_url)
        return command

    return [player, stream_url]


def launch_external_player(
    player, stream_url, user_agent="", title="", platform=None
):
    """Launch an external media player and return its process handle."""
    command = external_player_command(
        player,
        stream_url,
        user_agent=user_agent,
        title=title,
        platform=platform,
    )
    logging.debug(
        "Launching external player: executable=%r; title=%r; platform=%s",
        player,
        title,
        platform or sys.platform,
    )
    return subprocess.Popen(
        command,
        env=external_player_environment(platform=platform),
    )
