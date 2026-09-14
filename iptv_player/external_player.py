"""Cross-platform external media player command construction and launching."""

import os
from os import path
import subprocess
import sys

from iptv_player.config.paths import macos_bundle_executable


class ExternalPlayerNotExecutableError(PermissionError):
    """Indicate that the selected Linux player cannot be executed."""


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
        elif player_lower.endswith(("mpv", "mpv.com")) and user_agent:
            command.append(f"--user-agent={user_agent}")
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
                " " + subprocess.list2cmdline([f"--meta-title={title}"])
                if title else ""
            )
            return (
                f"{quoted_player}{user_agent_argument}{title_argument} "
                f"{quoted_url}"
            )
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
    return subprocess.Popen(command)
