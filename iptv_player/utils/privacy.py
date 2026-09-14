"""Helpers for logging useful diagnostics without exposing credentials."""

from pathlib import PurePosixPath
import re
from urllib.parse import urlparse


_QUERY_CREDENTIAL = re.compile(
    r"(?i)([?&](?:username|password|login)=)[^&#\s]*"
)
_LABELED_CREDENTIAL = re.compile(
    r"(?i)(\b(?:username|password|login)\s*[:=]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;&]+)"
)
_XTREAM_PATH_CREDENTIALS = re.compile(
    r"(?i)(/(?:live|movie|series)/)[^/\s]+/[^/\s]+(?=/)"
)


def private_url_log_reference(url):
    """Identify a stream in logs without exposing its host or credentials."""
    try:
        final_component = PurePosixPath(urlparse(str(url)).path).name
        return f"<private URL ending in {final_component or 'unknown'}>"
    except (TypeError, ValueError):
        return "<private URL>"


def redact_log_credentials(value):
    """Replace credentials commonly exposed by URLs and network exceptions."""
    text = str(value)
    text = _QUERY_CREDENTIAL.sub(r"\1***", text)
    text = _LABELED_CREDENTIAL.sub(r"\1***", text)
    return _XTREAM_PATH_CREDENTIALS.sub(r"\1***/***", text)

