"""Lifecycle helpers for files owned by one IPTV account."""

from pathlib import Path


def remove_account_data_files(account_id, *base_files):
    """Remove every per-account file derived from the supplied base paths."""
    owned_files = tuple(_account_file(filename, account_id) for filename in base_files)
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
