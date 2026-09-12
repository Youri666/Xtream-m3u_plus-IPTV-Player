"""Helpers for logging useful diagnostics without exposing credentials."""

from pathlib import PurePosixPath
from urllib.parse import urlparse


def private_url_log_reference(url):
    """Identify a stream in logs without exposing its host or credentials."""
    try:
        final_component = PurePosixPath(urlparse(str(url)).path).name
        return f"<private URL ending in {final_component or 'unknown'}>"
    except (TypeError, ValueError):
        return "<private URL>"

