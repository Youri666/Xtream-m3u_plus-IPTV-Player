"""Refresh account-selector summaries without loading or activating catalogues."""
import time
from PyQt5.QtCore import QObject, QThreadPool, pyqtSignal
from iptv_player.config.accounts import (load_accounts, load_account, load_account_id,
                                        load_account_user_agent, parse_account, save_account_metadata)
from iptv_player.provider.credentials import parse_xtream_m3u_url
from iptv_player.provider.workers import AccountInfoWorker


class AccountMetadataLoader(QObject):
    """Queue one metadata request per account and throttle repeated popup openings."""
    changed = pyqtSignal()

    def __init__(self, filename, parent=None):
        super().__init__(parent)
        self.filename = filename
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.pending = {}
        self.last_attempt = {}
        self.states = {}

    def refresh(self):
        """Refresh all saved accounts while keeping their existing summaries visible."""
        for name, serialized in load_accounts(self.filename).items():
            account_id = load_account_id(self.filename, name)
            key = (account_id, serialized, load_account_user_agent(self.filename, name))
            if key in self.pending or time.monotonic() - self.last_attempt.get(key, float('-inf')) < 30:
                continue
            parsed = parse_account(serialized)
            if parsed is None:
                continue
            method, fields = parsed
            credentials = tuple(fields[:3]) if method == "manual" else parse_xtream_m3u_url(fields[0])
            if not credentials:
                continue
            worker = AccountInfoWorker(*credentials, key[2])
            self.pending[key] = worker
            self.last_attempt[key] = time.monotonic()
            self.states[name] = "Loading account information…"
            worker.signals.finished.connect(lambda data, n=name, k=key: self._finished(n, k, data))
            worker.signals.error.connect(lambda _error, n=name, k=key: self._finished(n, k, None))
            self.pool.start(worker)
        self.changed.emit()

    def _finished(self, name, key, data):
        """Discard responses for deleted or edited accounts and keep cached data on failure."""
        self.pending.pop(key, None)
        if (load_account_id(self.filename, name), load_account(self.filename, name),
                load_account_user_agent(self.filename, name)) != key:
            self.states.pop(name, None)
            self.changed.emit()
            return
        user_info = data.get("user_info") if isinstance(data, dict) else None
        if isinstance(user_info, dict) and user_info:
            try:
                save_account_metadata(self.filename, name, user_info, data.get("server_info"))
                self.states.pop(name, None)
            except OSError:
                self.states[name] = "Could not save account information. Try again later."
        else:
            self.states[name] = "Could not refresh account information. Try again later."
        self.changed.emit()
