"""Explain why the native VLC engine cannot be loaded."""

import os
import struct
import sys
from pathlib import Path


_PE_ARCHITECTURES = {
    0x014C: "32-bit",
    0x8664: "64-bit",
    0xAA64: "ARM64",
}


def pe_architecture(filename):
    """Return the architecture stored in a Windows PE header, when readable."""
    try:
        with open(filename, "rb") as binary:
            if binary.read(2) != b"MZ":
                return "unknown"
            binary.seek(0x3C)
            pe_offset = struct.unpack("<I", binary.read(4))[0]
            binary.seek(pe_offset)
            if binary.read(4) != b"PE\0\0":
                return "unknown"
            machine = struct.unpack("<H", binary.read(2))[0]
        return _PE_ARCHITECTURES.get(machine, "unknown")
    except (OSError, EOFError, struct.error):
        return "unknown"


def current_process_architecture():
    """Return the architecture that native libraries must match."""
    executable_architecture = pe_architecture(sys.executable)
    if executable_architecture != "unknown":
        return executable_architecture
    return "64-bit" if struct.calcsize("P") == 8 else "32-bit"


def windows_vlc_library_paths(environment=None, registry_paths=None):
    """Return existing libVLC candidates from explicit and standard locations."""
    environment = os.environ if environment is None else environment
    candidates = []

    explicit_library = environment.get("PYTHON_VLC_LIB_PATH", "").strip()
    if explicit_library:
        candidates.append(Path(explicit_library))

    explicit_modules = environment.get("PYTHON_VLC_MODULE_PATH", "").strip()
    if explicit_modules:
        candidates.append(Path(explicit_modules) / "libvlc.dll")

    for variable in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        directory = environment.get(variable, "").strip()
        if directory:
            candidates.append(Path(directory) / "VideoLAN" / "VLC" / "libvlc.dll")

    candidates.extend(
        _registry_vlc_library_paths() if registry_paths is None else registry_paths
    )

    unique_paths = []
    seen = set()
    for candidate in candidates:
        candidate = Path(candidate)
        normalized = os.path.normcase(os.path.abspath(str(candidate)))
        if normalized in seen or not candidate.is_file():
            continue
        seen.add(normalized)
        unique_paths.append(candidate)
    return unique_paths


def _registry_vlc_library_paths():
    """Read both Windows registry views because VLC may be 32-bit or 64-bit."""
    if not sys.platform.startswith("win"):
        return []
    try:
        import winreg
    except ImportError:
        return []

    paths = []
    views = [getattr(winreg, "KEY_WOW64_64KEY", 0), getattr(winreg, "KEY_WOW64_32KEY", 0)]
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in views:
            try:
                with winreg.OpenKey(
                    root,
                    r"Software\VideoLAN\VLC",
                    0,
                    winreg.KEY_READ | view,
                ) as key:
                    install_directory, _value_type = winreg.QueryValueEx(key, "InstallDir")
                paths.append(Path(install_directory) / "libvlc.dll")
            except OSError:
                continue
    return paths


def describe_vlc_load_failure(
    error,
    library_paths=None,
    process_architecture=None,
    platform_name=None,
):
    """Return a user-facing explanation for one failed libVLC load."""
    platform_name = platform_name or sys.platform
    if not platform_name.startswith("win"):
        detail = str(error or "").strip()
        suffix = f" Technical details: {detail}" if detail else ""
        return (
            "VLC was found, but its native library could not be loaded. Install a "
            "VLC package compatible with this system, then restart IPTV Player."
            f"{suffix}"
        )

    process_architecture = process_architecture or current_process_architecture()
    library_paths = (
        windows_vlc_library_paths() if library_paths is None else list(library_paths)
    )
    detected = [(Path(item), pe_architecture(item)) for item in library_paths]
    known = [(item, architecture) for item, architecture in detected if architecture != "unknown"]
    compatible = [item for item, architecture in known if architecture == process_architecture]

    if known and not compatible:
        installed = ", ".join(sorted({architecture for _item, architecture in known}))
        return (
            f"A {installed} VLC installation was found, but IPTV Player requires "
            f"{process_architecture} VLC. Install the standard {process_architecture} "
            "version of VLC and restart IPTV Player."
        )

    if library_paths:
        return (
            f"VLC was found, but its native library could not be loaded by the "
            f"{process_architecture} IPTV Player. Reinstall the standard "
            f"{process_architecture} version of VLC in the default location, then "
            "restart IPTV Player."
        )

    detail = str(error or "").strip()
    suffix = f" Technical details: {detail}" if detail else ""
    return (
        "No VLC native library was found in the Windows registry or standard "
        "installation folders. Install the standard VLC desktop application from "
        "videolan.org using the default location, then restart IPTV Player."
        f"{suffix}"
    )
