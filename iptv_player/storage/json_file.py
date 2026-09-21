"""Safe JSON mapping persistence shared by caches and user data."""

import json
import os
import tempfile
from pathlib import Path


def read_json_mapping(filename):
    """Return a JSON object mapping or an empty mapping for invalid data."""
    try:
        with open(filename, "r") as json_file:
            data = json.load(json_file)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError, UnicodeDecodeError):
        return {}


def write_json_file(filename, data, indent=4):
    """Atomically replace a JSON file after serializing it completely."""
    destination = Path(filename)
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=str(destination.parent),
        text=True,
    )
    try:
        with os.fdopen(file_descriptor, "w", newline="") as json_file:
            json.dump(data, json_file, indent=indent)
            json_file.flush()
            os.fsync(json_file.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise

