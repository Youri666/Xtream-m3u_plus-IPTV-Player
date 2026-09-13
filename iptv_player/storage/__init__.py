"""Persistent data storage helpers."""

from .favorites import entries_in_favorite_order, set_favorite
from .json_file import read_json_mapping, write_json_file

__all__ = (
    "entries_in_favorite_order",
    "read_json_mapping",
    "set_favorite",
    "write_json_file",
)
