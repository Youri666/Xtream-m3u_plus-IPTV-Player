"""Resolve user data and application paths without depending on the UI."""

import os
import plistlib
import sys
from pathlib import Path


APPLICATION_NAME = "IPTV Player"


def writable_data_directory(platform=None, home=None, working_directory=None):
    """Return the directory used for configuration and disposable user data."""
    platform = platform or sys.platform
    if platform.startswith("darwin"):
        home_directory = Path(home).expanduser() if home else Path.home()
        return str(home_directory / "Library" / "Application Support" / APPLICATION_NAME)

    directory = Path(working_directory) if working_directory else Path.cwd()
    return str(directory.resolve())


def macos_bundle_executable(bundle_path):
    """Resolve the executable declared by a macOS application bundle."""
    bundle = Path(bundle_path)
    info_path = bundle / "Contents" / "Info.plist"
    with info_path.open("rb") as info_file:
        executable_name = plistlib.load(info_file).get("CFBundleExecutable", "")

    if not executable_name:
        raise OSError(f"The application bundle has no CFBundleExecutable: {bundle_path}")

    executable_path = bundle / "Contents" / "MacOS" / executable_name
    if not executable_path.is_file() or not os.access(executable_path, os.X_OK):
        raise OSError(f"The application bundle executable is unavailable: {executable_path}")
    return str(executable_path)

