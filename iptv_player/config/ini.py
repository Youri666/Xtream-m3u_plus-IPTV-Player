"""Safe helpers for reading and writing INI configuration files."""

import configparser
import os
import tempfile
from pathlib import Path


def read_config_file(filename):
    """Load an INI file using the application's standard parser settings."""
    config = configparser.ConfigParser()
    config.read(filename)
    return config


def write_config_file(filename, config):
    """Replace an INI file atomically after its complete contents are written."""
    destination = Path(filename)
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=str(destination.parent),
        text=True,
    )
    try:
        # Keep the platform encoding used by previous releases until a dedicated
        # configuration encoding migration can safely convert existing files.
        with os.fdopen(file_descriptor, "w", newline="") as stream:
            config.write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
