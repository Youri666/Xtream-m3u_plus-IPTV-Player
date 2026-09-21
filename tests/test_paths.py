import os
import plistlib
import tempfile
import unittest
from pathlib import Path

from iptv_player.config.paths import (
    application_resource_path,
    macos_bundle_executable,
    writable_data_directory,
)


class ApplicationResourcePathTests(unittest.TestCase):
    def test_resolves_resource_from_explicit_application_root(self):
        with tempfile.TemporaryDirectory() as directory:
            expected = Path(directory) / "Images" / "icon.ico"

            result = application_resource_path(
                Path("Images") / "icon.ico", application_root=directory
            )

            self.assertEqual(result, str(expected.resolve()))


class WritableDataDirectoryTests(unittest.TestCase):
    def test_macos_uses_application_support(self):
        result = writable_data_directory(platform="darwin", home="/Users/tester")
        self.assertEqual(
            result,
            str(Path("/Users/tester/Library/Application Support/IPTV Player")),
        )

    def test_other_platforms_use_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            result = writable_data_directory(
                platform="win32", working_directory=directory
            )
            self.assertEqual(result, str(Path(directory).resolve()))


class MacOSBundleExecutableTests(unittest.TestCase):
    def test_resolves_executable_from_info_plist(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "Player.app"
            contents = bundle / "Contents"
            executable = contents / "MacOS" / "PlayerBinary"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"binary")
            executable.chmod(executable.stat().st_mode | 0o111)
            with (contents / "Info.plist").open("wb") as info_file:
                plistlib.dump({"CFBundleExecutable": "PlayerBinary"}, info_file)

            self.assertEqual(macos_bundle_executable(bundle), str(executable))

    def test_rejects_bundle_without_executable_name(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "Player.app"
            contents = bundle / "Contents"
            contents.mkdir(parents=True)
            with (contents / "Info.plist").open("wb") as info_file:
                plistlib.dump({}, info_file)

            with self.assertRaises(OSError):
                macos_bundle_executable(bundle)


if __name__ == "__main__":
    unittest.main()
