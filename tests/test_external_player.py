from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from iptv_player.external_player import (
    ExternalPlayerNotExecutableError,
    external_player_command,
    external_player_display_name,
    external_player_environment,
    launch_external_player,
)


class ExternalPlayerCommandTests(unittest.TestCase):
    def test_external_player_display_names_are_concise(self):
        self.assertEqual(
            external_player_display_name(r"C:\Program Files\VideoLAN\VLC\vlc.exe"),
            "VLC Player",
        )
        self.assertEqual(
            external_player_display_name(r"C:\Program Files\SMPlayer\smplayer.exe"),
            "SMPlayer",
        )
        self.assertEqual(
            external_player_display_name(r"C:\Players\custom-player.exe"),
            "custom-player",
        )
        self.assertEqual(
            external_player_display_name("/usr/bin/totem"),
            "Totem (GNOME Videos)",
        )

    def test_windows_vlc_receives_user_agent_before_stream_url(self):
        command = external_player_command(
            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            "http://example.test/live/1",
            "IPTV Player",
            platform="win32",
        )

        self.assertEqual(
            command,
            '"C:\\Program Files\\VideoLAN\\VLC\\vlc.exe" '
            '--http-user-agent="IPTV Player" "http://example.test/live/1"',
        )

    def test_windows_vlc_receives_media_title(self):
        command = external_player_command(
            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            "http://example.test/series/1234.mkv",
            title="DAN DA DAN - Episode 02",
            platform="win32",
        )

        self.assertEqual(
            command,
            '"C:\\Program Files\\VideoLAN\\VLC\\vlc.exe" '
            '"--meta-title=DAN DA DAN - Episode 02" '
            '"--input-title-format=DAN DA DAN - Episode 02" '
            '"http://example.test/series/1234.mkv"',
        )

    def test_windows_generic_player_uses_only_executable_and_url(self):
        command = external_player_command(
            r"C:\Players\player.exe",
            "http://example.test/movie/2",
            "Ignored for generic players",
            platform="win32",
        )

        self.assertEqual(
            command,
            '"C:\\Players\\player.exe" "http://example.test/movie/2"',
        )

    def test_windows_smplayer_receives_media_title(self):
        command = external_player_command(
            r"C:\Program Files\SMPlayer\smplayer.exe",
            "http://example.test/live/1",
            title="Original channel title",
            platform="win32",
        )

        self.assertEqual(
            command,
            '"C:\\Program Files\\SMPlayer\\smplayer.exe" '
            '-media-title "Original channel title" '
            'http://example.test/live/1',
        )

    def test_linux_rejects_non_executable_player(self):
        with patch("iptv_player.external_player.os.access", return_value=False):
            with self.assertRaises(ExternalPlayerNotExecutableError):
                external_player_command(
                    "/usr/bin/vlc", "http://example.test/live/1", platform="linux"
                )

    def test_linux_mpv_receives_user_agent(self):
        with patch("iptv_player.external_player.os.access", return_value=True):
            command = external_player_command(
                "/usr/bin/mpv",
                "http://example.test/live/1",
                "IPTV Player",
                platform="linux",
            )

        self.assertEqual(
            command,
            [
                "/usr/bin/mpv",
                "--user-agent=IPTV Player",
                "http://example.test/live/1",
            ],
        )

    def test_linux_vlc_receives_media_title(self):
        with patch("iptv_player.external_player.os.access", return_value=True):
            command = external_player_command(
                "/usr/bin/vlc",
                "http://example.test/movie/1234.mkv",
                title="Original movie title",
                platform="linux",
            )

        self.assertEqual(
            command,
            [
                "/usr/bin/vlc",
                "--meta-title=Original movie title",
                "--input-title-format=Original movie title",
                "http://example.test/movie/1234.mkv",
            ],
        )

    def test_linux_smplayer_receives_media_title(self):
        with patch("iptv_player.external_player.os.access", return_value=True):
            command = external_player_command(
                "/usr/bin/smplayer",
                "http://example.test/live/1",
                title="Original channel title",
                platform="linux",
            )

        self.assertEqual(command, [
            "/usr/bin/smplayer",
            "-media-title",
            "Original channel title",
            "http://example.test/live/1",
        ])

    def test_macos_resolves_application_bundle_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "VLC.app"
            bundle.mkdir()
            with patch(
                "iptv_player.external_player.macos_bundle_executable",
                return_value="/Applications/VLC.app/Contents/MacOS/VLC",
            ):
                command = external_player_command(
                    str(bundle),
                    "http://example.test/live/1",
                    "IPTV Player",
                    title="Original channel title",
                    platform="darwin",
                )

        self.assertEqual(
            command,
            [
                "/Applications/VLC.app/Contents/MacOS/VLC",
                "--http-user-agent=IPTV Player",
                "--meta-title=Original channel title",
                "--input-title-format=Original channel title",
                "http://example.test/live/1",
            ],
        )

    def test_launcher_passes_constructed_command_to_subprocess(self):
        with patch(
            "iptv_player.external_player.external_player_command",
            return_value=["player", "stream"],
        ), patch("iptv_player.external_player.subprocess.Popen") as popen:
            launch_external_player("player", "stream")

        popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0], ["player", "stream"])
        self.assertIn("env", popen.call_args.kwargs)

    def test_external_player_does_not_inherit_qt_plugin_paths(self):
        environment = external_player_environment({
            "PATH": "system-path",
            "QT_PLUGIN_PATH": "bundled-qt",
            "QT_QPA_PLATFORM_PLUGIN_PATH": "bundled-platforms",
            "QT_QPA_PLATFORM": "offscreen",
            "QML2_IMPORT_PATH": "bundled-qml",
        }, platform="win32")

        self.assertEqual(environment, {"PATH": "system-path"})

    def test_external_player_restores_original_linux_library_path(self):
        environment = external_player_environment({
            "LD_LIBRARY_PATH": "bundled-libraries",
            "LD_LIBRARY_PATH_ORIG": "system-libraries",
        }, platform="linux")

        self.assertEqual(environment["LD_LIBRARY_PATH"], "system-libraries")
        self.assertNotIn("LD_LIBRARY_PATH_ORIG", environment)


if __name__ == "__main__":
    unittest.main()
