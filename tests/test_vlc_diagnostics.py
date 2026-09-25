import struct
import tempfile
import unittest
from pathlib import Path

from iptv_player.vlc_diagnostics import (
    describe_vlc_load_failure,
    pe_architecture,
    windows_vlc_library_paths,
)


def _write_pe(filename, machine):
    payload = bytearray(256)
    payload[0:2] = b"MZ"
    struct.pack_into("<I", payload, 0x3C, 128)
    payload[128:132] = b"PE\0\0"
    struct.pack_into("<H", payload, 132, machine)
    filename.write_bytes(payload)


class VlcDiagnosticsTests(unittest.TestCase):
    def test_reads_32_and_64_bit_windows_libraries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            x86_library = root / "x86.dll"
            x64_library = root / "x64.dll"
            _write_pe(x86_library, 0x014C)
            _write_pe(x64_library, 0x8664)

            self.assertEqual(pe_architecture(x86_library), "32-bit")
            self.assertEqual(pe_architecture(x64_library), "64-bit")

    def test_reports_architecture_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory) / "libvlc.dll"
            _write_pe(library, 0x014C)

            message = describe_vlc_load_failure(
                OSError("load failed"),
                library_paths=[library],
                process_architecture="64-bit",
                platform_name="win32",
            )

        self.assertIn("32-bit VLC installation", message)
        self.assertIn("requires 64-bit VLC", message)

    def test_reports_missing_standard_installation(self):
        message = describe_vlc_load_failure(
            OSError("libvlc.dll was not found"),
            library_paths=[],
            process_architecture="64-bit",
            platform_name="win32",
        )

        self.assertIn("No VLC native library was found", message)
        self.assertIn("libvlc.dll was not found", message)

    def test_finds_explicit_and_standard_libraries_without_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            standard = root / "VideoLAN" / "VLC" / "libvlc.dll"
            standard.parent.mkdir(parents=True)
            _write_pe(standard, 0x8664)

            paths = windows_vlc_library_paths(
                {
                    "ProgramW6432": str(root),
                    "ProgramFiles": str(root),
                    "ProgramFiles(x86)": "",
                },
                registry_paths=[],
            )

        self.assertEqual(paths, [standard])


if __name__ == "__main__":
    unittest.main()
