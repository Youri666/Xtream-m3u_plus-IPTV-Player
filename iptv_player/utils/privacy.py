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
_URL_AUTHORITY = re.compile(r"(?i)(https?://)[^/\s\"'<>]+")
_CONNECTION_TARGET = re.compile(
    r"(?i)(Starting new HTTPS? connection\s*\(\d+\):\s*)\S+"
)
_POOL_TARGET = re.compile(
    r"(?i)(HTTPS?ConnectionPool\()host=(['\"])[^'\"]*\2,\s*port=[^,)]+"
)
_ACCOUNT_VALUE = re.compile(
    r"(?i)(\b(?:account_id|account_name|name|id)=)(?:'[^']*'|\"[^\"]*\"|[^;\s]+)"
)
_USER_DIRECTORY = re.compile(
    r"(?i)((?:[A-Z]:[\\/]Users[\\/]|/home/|/Users/))[^\\/\s]+"
)
_RESOLUTION_TARGET = re.compile(
    r"(?i)(Failed to resolve\s+)(['\"])[^'\"]*\2"
)
_SECRET_VALUE = re.compile(
    r"(?i)(\b(?:api_key|access_token|token|authorization)\s*[:=]\s*)"
    r"(?:Bearer\s+)?(?:\"[^\"]*\"|'[^']*'|[^\s,;&]+)"
)
_REQUEST_PATH = re.compile(r'(\"(?:GET|POST|HEAD|PUT|DELETE|OPTIONS|PATCH)\s+)(/[^\s?\"]*)')
_URL_PATH = re.compile(r"(https?://<server>)(/(?!<path>)[^\s?\"'<>]*)", re.IGNORECASE)


def _safe_network_path(match):
    """Keep known API endpoint names; arbitrary paths can contain credentials."""
    prefix, request_path = match.groups()
    if request_path.rstrip('/').endswith('/player_api.php'):
        return prefix + '/player_api.php'
    # Preserve the already anonymized conventional Xtream structure.
    if re.fullmatch(r'/(?:live|movie|series)/\*\*\*/\*\*\*/[^/]+', request_path):
        return prefix + request_path
    return prefix + '/<path>'


def private_url_log_reference(url):
    """Identify a stream in logs without exposing its host or credentials."""
    try:
        final_component = PurePosixPath(urlparse(str(url)).path).name
        return f"<private URL ending in {final_component or 'unknown'}>"
    except (TypeError, ValueError):
        return "<private URL>"


def redact_log_credentials(value):
    """Remove network endpoints and personal identifiers from diagnostics."""
    text = str(value)
    text = _QUERY_CREDENTIAL.sub(r"\1***", text)
    text = _LABELED_CREDENTIAL.sub(r"\1***", text)
    text = _XTREAM_PATH_CREDENTIALS.sub(r"\1***/***", text)
    text = _URL_AUTHORITY.sub(r"\1<server>", text)
    text = _REQUEST_PATH.sub(_safe_network_path, text)
    text = _URL_PATH.sub(_safe_network_path, text)
    text = _CONNECTION_TARGET.sub(r"\1<server>", text)
    text = _POOL_TARGET.sub(r"\1host='<server>', port=<hidden>", text)
    text = _RESOLUTION_TARGET.sub(r"\1'<server>'", text)
    text = _SECRET_VALUE.sub(r"\1***", text)
    text = _USER_DIRECTORY.sub(r"\1<user>", text)
    if "account" in text.lower() or "category selected" in text.lower():
        text = _ACCOUNT_VALUE.sub(r"\1<hidden>", text)
    return text

