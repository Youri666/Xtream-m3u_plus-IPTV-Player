"""Parsing helpers for Xtream M3U account URLs."""

from urllib.parse import parse_qs, urlparse


def parse_xtream_m3u_url(url):
    """Return ``(server, username, password)`` for a valid Xtream M3U URL."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    if not parsed.path.endswith("/get.php"):
        return None

    query = parse_qs(parsed.query)
    username = (query.get("username") or [None])[0]
    password = (query.get("password") or [None])[0]
    if not username or not password:
        return None

    return f"{parsed.scheme}://{parsed.netloc}", username, password
