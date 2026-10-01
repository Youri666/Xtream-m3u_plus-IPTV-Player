"""Verify installed plugin discovery without distribution-specific library paths."""

from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from iptv_player.linux_vlc_runtime import configure_linux_vlc_plugins, system_vlc_plugin_directory


class LinuxVlcRuntimeTests(unittest.TestCase):
    def test_discovers_plugins_for_different_library_directory_layouts(self):
        for layout in ('lib', 'lib64', 'lib/x86_64-linux-gnu', 'custom/lib'):
            with self.subTest(layout=layout), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / layout
                plugins = root / 'vlc' / 'plugins'
                plugins.mkdir(parents=True)
                library = root / 'libvlc.so.5'
                library.write_bytes(b'\x7fELF' + bytes([2 if struct.calcsize('P') == 8 else 1]))
                output = subprocess.CompletedProcess([], 0, f'libvlc.so.5 (libc6) => {library}\n', '')
                with patch('iptv_player.linux_vlc_runtime.shutil.which', return_value='/sbin/ldconfig'), \
                        patch('iptv_player.linux_vlc_runtime.subprocess.run', return_value=output) as run:
                    self.assertEqual(system_vlc_plugin_directory({'LD_LIBRARY_PATH': '/bundled'}), str(plugins.resolve()))
                    self.assertNotIn('LD_LIBRARY_PATH', run.call_args.kwargs['env'])

    def test_configures_packaged_linux_and_keeps_parent_mapping_explicit(self):
        environment = {}
        with patch('iptv_player.linux_vlc_runtime.system_vlc_plugin_directory', return_value='/installed/plugins'):
            configure_linux_vlc_plugins(environment, platform='linux', frozen=True)
        self.assertEqual(environment, {'VLC_PLUGIN_PATH': '/installed/plugins'})

    def test_preserves_user_overrides(self):
        for variable in ('VLC_PLUGIN_PATH', 'PYTHON_VLC_MODULE_PATH', 'PYTHON_VLC_LIB_PATH'):
            environment = {variable: '/custom'}
            with patch('iptv_player.linux_vlc_runtime.system_vlc_plugin_directory') as discover:
                configure_linux_vlc_plugins(environment, platform='linux', frozen=True)
                discover.assert_not_called()
            self.assertEqual(environment, {variable: '/custom'})

    def test_other_platforms_and_source_execution_are_unchanged(self):
        for platform, frozen in (('linux', False), ('win32', True), ('darwin', True)):
            with patch('iptv_player.linux_vlc_runtime.system_vlc_plugin_directory') as discover:
                environment = {}
                configure_linux_vlc_plugins(environment, platform=platform, frozen=frozen)
                self.assertEqual(environment, {})
                discover.assert_not_called()

    def test_missing_linker_cache_does_not_prevent_normal_vlc_discovery(self):
        with patch('iptv_player.linux_vlc_runtime.shutil.which', return_value='/sbin/ldconfig'), \
                patch('iptv_player.linux_vlc_runtime.subprocess.run', side_effect=subprocess.TimeoutExpired('ldconfig', 3)):
            self.assertIsNone(system_vlc_plugin_directory({}))
