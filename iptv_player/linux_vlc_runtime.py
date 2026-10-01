"""Locate installed VLC plugins for Linux applications packaged by PyInstaller."""

import logging
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

from iptv_player.external_player import external_player_environment


def system_vlc_plugin_directory(environment=None):
    """Find plugins beside libVLC registered with the system dynamic linker."""
    environment = dict(os.environ if environment is None else environment)
    command = shutil.which('ldconfig', path=environment.get('PATH'))
    if command is None:
        command = next((candidate for candidate in ('/sbin/ldconfig', '/usr/sbin/ldconfig')
                        if os.path.isfile(candidate) and os.access(candidate, os.X_OK)), None)
    if command is None:
        return None
    try:
        result = subprocess.run(
            [command, '-p'], capture_output=True, text=True, timeout=3, check=True,
            env=external_player_environment(environment, platform='linux', frozen=True),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in result.stdout.splitlines():
        fields = line.strip().split()
        if not fields or not fields[0].startswith('libvlc.so') or '=>' not in fields:
            continue
        library = Path(fields[-1])
        if not library.is_absolute():
            continue
        # Ignore libraries for the other bitness on multilib installations.
        try:
            with library.open('rb') as binary:
                header = binary.read(5)
        except OSError:
            continue
        expected_class = 2 if struct.calcsize('P') == 8 else 1
        if header != b'\x7fELF' + bytes([expected_class]):
            continue
        plugins = library.resolve().parent / 'vlc' / 'plugins'
        if plugins.is_dir():
            return str(plugins)
    return None


def configure_linux_vlc_plugins(environment=None, platform=None, frozen=None):
    """Restore plugin discovery without replacing explicit VLC configuration."""
    environment = os.environ if environment is None else environment
    platform = platform or sys.platform
    frozen = getattr(sys, 'frozen', False) if frozen is None else frozen
    if not platform.startswith('linux') or not frozen:
        return
    if any(environment.get(key) for key in
           ('VLC_PLUGIN_PATH', 'PYTHON_VLC_MODULE_PATH', 'PYTHON_VLC_LIB_PATH')):
        return
    directory = system_vlc_plugin_directory(environment)
    if directory:
        environment['VLC_PLUGIN_PATH'] = directory
        logging.debug('Internal VLC system plugin directory: %s', directory)
    else:
        logging.debug('Internal VLC system plugin directory could not be located')
