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
    _preserve_credential_name_case(destination, config)
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


def _preserve_credential_name_case(destination, config):
    """Restore account-label case lost by callers using a default ConfigParser."""
    if "Credentials" not in config:
        return

    existing_config = configparser.ConfigParser()
    existing_config.optionxform = str
    try:
        existing_config.read(destination)
    except (configparser.Error, UnicodeDecodeError):
        existing_config = configparser.ConfigParser()
        existing_config.optionxform = str

    preferred_names = {}
    if "Credentials" in existing_config:
        preferred_names.update(
            (name.casefold(), name) for name in existing_config["Credentials"]
        )

    startup_name = config.get(
        "Startup credentials", "startup_credentials", fallback=""
    ).strip()
    if startup_name:
        preferred_names[startup_name.casefold()] = startup_name

    credentials = list(config["Credentials"].items())
    config.optionxform = str
    config.remove_section("Credentials")
    config.add_section("Credentials")
    for name, value in credentials:
        config["Credentials"][preferred_names.get(name.casefold(), name)] = value
