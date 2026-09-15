"""Lifecycle helpers for files owned by one IPTV account."""

from pathlib import Path


def remove_account_data_files(
    account_id, cache_base_file, favorites_base_file, preferences_base_file
):
    """Remove an account's cache, favorites, and category preference files."""
    owned_files = (
        _account_file(cache_base_file, account_id),
        _account_file(favorites_base_file, account_id),
        _account_file(preferences_base_file, account_id),
    )
    failures = []
    for filename in owned_files:
        try:
            Path(filename).unlink()
        except FileNotFoundError:
            pass
        except OSError as error:
            failures.append((str(filename), error))
    return failures


def _account_file(base_filename, account_id):
    """Apply the shared per-account filename convention to one base path."""
    base_path = Path(base_filename)
    return base_path.with_name(
        f"{base_path.stem}.{account_id}{base_path.suffix}"
    )
