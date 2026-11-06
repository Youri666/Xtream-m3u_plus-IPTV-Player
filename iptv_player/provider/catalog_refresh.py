"""Per-account catalogue refresh scheduling shared by manual and timed requests."""
import time
from datetime import datetime


class CatalogRefreshPolicy:
    """Track real fetch age, in-flight requests and a bounded retry delay."""
    def __init__(self):
        self.busy = set()
        self.fetched_at = {}
        self.retry_after = {}

    def begin(self, account):
        if account in self.busy:
            return False
        self.busy.add(account)
        return True

    def finish(self, account, successful, fetched_at=None):
        self.busy.discard(account)
        if successful:
            self.fetched_at[account] = fetched_at if fetched_at is not None else time.time()
            self.retry_after.pop(account, None)
        else:
            self.fetched_at.setdefault(account, fetched_at or 0)
            self.retry_after[account] = time.time() + 300

    def due(self, account, max_age_hours):
        now = time.time()
        return (bool(account) and account not in self.busy
                and account in self.fetched_at
                and now >= self.retry_after.get(account, 0)
                and now - self.fetched_at[account] >= max_age_hours * 3600)


def catalog_last_updated_text(fetched_at):
    """Format the actual catalogue fetch time, never the cache-load time."""
    try:
        value = float(fetched_at)
        if value <= 0:
            raise ValueError("Missing fetch timestamp")
        timestamp = datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError, OverflowError):
        timestamp = "Not available"
    return f"Catalog last updated: {timestamp}"
