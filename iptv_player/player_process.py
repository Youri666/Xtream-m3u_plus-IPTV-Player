"""Entry point for the isolated embedded VLC player process."""

import os
import sys
import threading
from multiprocessing.connection import Client

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication

from iptv_player.bootstrap import configure_qt_application, install_logging
from iptv_player.constants import (
    DEFAULT_INTERNAL_AUTO_ADVANCE_SECONDS,
    DEFAULT_INTERNAL_AUTO_PLAY_NEXT,
    DEFAULT_INTERNAL_NETWORK_CACHING_MS,
    DEFAULT_INTERNAL_SEEK_STEP_SECONDS,
    DEFAULT_INTERNAL_SPEED_STEP,
    DEFAULT_INTERNAL_VOLUME_STEP_PERCENT,
)
from iptv_player.ui.player import EmbeddedPlayerWindow, set_macos_activation_policy
from iptv_player.ui.theme import apply_application_theme
from iptv_player.utils.environment import (
    bounded_float_environment,
    bounded_integer_environment,
)


class _PlayerCommandBridge(QObject):
    """Deliver commands received off the GUI thread to the player safely."""

    command_received = pyqtSignal(dict)
    connection_closed = pyqtSignal()


def run_embedded_player_process():
    """Run the libVLC window separately from the main application process."""
    install_logging(append=True, process_name="Internal player")
    address = os.environ.get("IPTV_PLAYER_IPC_ADDRESS", "")
    family = os.environ.get("IPTV_PLAYER_IPC_FAMILY", "")
    encoded_auth_key = os.environ.get("IPTV_PLAYER_IPC_AUTH", "")
    if not address or not family or not encoded_auth_key:
        return 1

    try:
        connection = Client(
            address=address,
            family=family,
            authkey=bytes.fromhex(encoded_auth_key),
        )
        first_command = connection.recv()
    except (EOFError, OSError, ValueError):
        return 1

    # Prevent Qt from promoting the warm player process into a foreground macOS
    # application before its first window is requested.
    if sys.platform == "darwin":
        os.environ.setdefault("QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM", "1")

    # Do not expose the private child-mode argument to Qt's option parser.
    app = QApplication([sys.argv[0]])
    # Keep the initialized VLC engine alive after the window is closed so the next
    # playback starts immediately in the same isolated process.
    app.setQuitOnLastWindowClosed(False)
    set_macos_activation_policy(False)
    configure_qt_application(app)
    apply_application_theme(app, os.environ.get("IPTV_PLAYER_THEME", "System"))

    # Parse defensively so a manually launched child receives safe values.
    seek_step = bounded_integer_environment(
        "IPTV_PLAYER_SEEK_STEP", DEFAULT_INTERNAL_SEEK_STEP_SECONDS, 1, 300
    )
    volume_step = bounded_integer_environment(
        "IPTV_PLAYER_VOLUME_STEP", DEFAULT_INTERNAL_VOLUME_STEP_PERCENT, 1, 25
    )
    speed_step = bounded_float_environment(
        "IPTV_PLAYER_SPEED_STEP", DEFAULT_INTERNAL_SPEED_STEP, 0.05, 1.0
    )
    auto_play_next = os.environ.get(
        "IPTV_PLAYER_AUTO_PLAY_NEXT",
        "1" if DEFAULT_INTERNAL_AUTO_PLAY_NEXT else "0",
    ) == "1"
    auto_advance_seconds = bounded_integer_environment(
        "IPTV_PLAYER_AUTO_ADVANCE_SECONDS",
        DEFAULT_INTERNAL_AUTO_ADVANCE_SECONDS,
        0,
        300,
    )
    network_caching_ms = bounded_integer_environment(
        "IPTV_PLAYER_NETWORK_CACHING_MS",
        DEFAULT_INTERNAL_NETWORK_CACHING_MS,
        0,
        60000,
    )

    player = EmbeddedPlayerWindow(
        None,
        user_agent=os.environ.get("IPTV_PLAYER_USER_AGENT", ""),
        settings_path=os.environ.get("IPTV_PLAYER_SETTINGS_FILE") or None,
        seek_step_seconds=seek_step,
        volume_step_percent=volume_step,
        speed_step=speed_step,
        audio_language=os.environ.get("IPTV_PLAYER_AUDIO_LANGUAGE", ""),
        subtitle_language=os.environ.get("IPTV_PLAYER_SUBTITLE_LANGUAGE", ""),
        resume_behavior=os.environ.get("IPTV_PLAYER_RESUME_BEHAVIOR", "ask"),
        auto_play_next=auto_play_next,
        auto_advance_seconds=auto_advance_seconds,
        network_caching_ms=network_caching_ms,
        progress_callback=lambda event: connection.send(event),
    )
    bridge = _PlayerCommandBridge()

    def handle_command(payload):
        """Apply commands on the GUI thread; warmup needs only initialization."""
        command = payload.get("command")
        if command == "play":
            player.play_url(
                payload.get("url", ""),
                payload.get("title", ""),
                payload.get("playlist") or [],
                payload.get("index", 0),
                payload.get("resume_ms", 0),
                payload.get("keep_above_main", False),
            )
        elif command == "quit":
            player.close()
            app.quit()
        elif command == "theme":
            apply_application_theme(app, payload.get("theme", "System"))
            player.apply_theme()
        elif command == "control_steps":
            player.set_control_steps(
                payload.get("seek_seconds", DEFAULT_INTERNAL_SEEK_STEP_SECONDS),
                payload.get("volume_percent", DEFAULT_INTERNAL_VOLUME_STEP_PERCENT),
                payload.get("speed_step", DEFAULT_INTERNAL_SPEED_STEP),
            )
            player.set_track_preferences(
                payload.get("audio_language", ""),
                payload.get("subtitle_language", ""),
            )
            player.set_resume_behavior(payload.get("resume_behavior", "ask"))
            player.set_auto_advance(
                payload.get("auto_play_next", DEFAULT_INTERNAL_AUTO_PLAY_NEXT),
                payload.get(
                    "auto_advance_seconds", DEFAULT_INTERNAL_AUTO_ADVANCE_SECONDS
                ),
                payload.get(
                    "network_caching_ms", DEFAULT_INTERNAL_NETWORK_CACHING_MS
                ),
            )

    bridge.command_received.connect(handle_command)
    bridge.connection_closed.connect(app.quit)

    def receive_commands():
        """Read blocking IPC off-thread and hand Qt operations to the signal bridge."""
        try:
            while True:
                payload = connection.recv()
                if not isinstance(payload, dict):
                    continue
                bridge.command_received.emit(payload)
                if payload.get("command") == "quit":
                    break
        except (EOFError, OSError):
            bridge.connection_closed.emit()

    receiver = threading.Thread(
        target=receive_commands,
        name="EmbeddedPlayerCommandReceiver",
        daemon=True,
    )
    receiver.start()
    handle_command(first_command)

    try:
        return app.exec_()
    finally:
        try:
            connection.close()
        except OSError:
            pass
