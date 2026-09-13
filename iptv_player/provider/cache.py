"""Account-aware storage for provider catalog responses."""

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path


CACHE_SCHEMA_VERSION = 1
STREAM_TYPES = ("LIVE", "Movies", "Series")


def account_cache_key(server, username):
    """Identify a provider account without storing its credentials in the cache."""
    identity = f"{str(server).rstrip('/').casefold()}\0{username}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def load_catalog_cache(filename):
    """Return a valid cache mapping or an empty mapping for unreadable data."""
    try:
        with open(filename, "r") as cache_file:
            cached_data = json.load(cache_file)
        return cached_data if isinstance(cached_data, dict) else {}
    except (OSError, ValueError, TypeError, UnicodeDecodeError):
        return {}


def required_catalog_keys(enabled_stream_types):
    """Return the cache collections required by the enabled content types."""
    return {
        key
        for stream_type in STREAM_TYPES
        if enabled_stream_types.get(stream_type, True)
        for key in (f"{stream_type} categories", stream_type)
    }


def catalog_cache_is_fresh(
    cached_data,
    expected_account_key,
    enabled_stream_types,
    max_age_hours,
    current_time=None,
):
    """Return whether a cache is complete, current, and owned by one account."""
    metadata = cached_data.get("_metadata", {})
    if metadata.get("account_key") != expected_account_key:
        return False
    try:
        fetched_at = float(metadata.get("fetched_at", 0))
    except (TypeError, ValueError):
        return False

    now = time.time() if current_time is None else current_time
    cache_age = max(0, now - fetched_at)
    return (
        cache_age <= max_age_hours * 3600
        and required_catalog_keys(enabled_stream_types).issubset(cached_data)
    )


def build_catalog_cache(
    previous_cache,
    expected_account_key,
    categories,
    entries,
    enabled_stream_types,
    fetch_complete,
    fetched_at=None,
):
    """Merge refreshed collections while preserving disabled cached content."""
    previous_metadata = previous_cache.get("_metadata", {})
    cache_matches_account = (
        previous_metadata.get("account_key") == expected_account_key
    )
    result = dict(previous_cache) if cache_matches_account else {}

    for stream_type in STREAM_TYPES:
        if enabled_stream_types.get(stream_type, True):
            result[f"{stream_type} categories"] = categories[stream_type]
            result[stream_type] = entries[stream_type]

    result["_metadata"] = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "account_key": expected_account_key,
        "fetched_at": (
            time.time() if fetched_at is None else fetched_at
        ) if fetch_complete else previous_metadata.get("fetched_at", 0),
    }
    return result


def write_catalog_cache(filename, cached_data):
    """Atomically replace the catalog cache after serializing it completely."""
    destination = Path(filename)
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=str(destination.parent),
        text=True,
    )
    try:
        with os.fdopen(file_descriptor, "w", newline="") as cache_file:
            json.dump(cached_data, cache_file, indent=4)
            cache_file.flush()
            os.fsync(cache_file.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise

