"""Helpers for reading bounded numeric values from the environment."""

import os


def bounded_integer_environment(name, default, minimum, maximum):
    """Read an integer environment value and keep it within safe bounds."""
    try:
        return max(minimum, min(int(os.environ.get(name, default)), maximum))
    except ValueError:
        return default


def bounded_float_environment(name, default, minimum, maximum):
    """Read a float environment value and keep it within safe bounds."""
    try:
        return max(minimum, min(float(os.environ.get(name, default)), maximum))
    except ValueError:
        return default
