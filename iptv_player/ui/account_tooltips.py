"""Format cached account metadata without exposing credentials."""
from datetime import datetime
from html import escape


def account_tooltip(metadata):
    """Make stale connection counts explicit and safely format optional timestamps."""
    if not metadata:
        return "Account information not available yet"
    expiry = "Unknown"
    try:
        expiry = datetime.fromtimestamp(int(metadata.get("exp_date"))).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError, OSError):
        pass
    refreshed = "Unknown"
    try:
        refreshed = datetime.fromisoformat(metadata.get("refreshed_at", "")).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OverflowError, OSError):
        pass
    hostname = metadata.get("url", "Unknown")
    port = metadata.get("port", "Unknown")
    host = hostname if port == "Unknown" or hostname == "Unknown" else f"{hostname}:{port}"
    rows = (("Host", host), ("Timezone", metadata.get("timezone", "Unknown")),
            ("Status", metadata.get("status", "Unknown")),
            ("Expiry", expiry), ("Max connections", metadata.get("max_connections", "Unknown")),
            ("Active connections (last known)", metadata.get("active_cons", "Unknown")),
            ("Last refreshed", refreshed))
    return "<qt>" + "<br>".join(escape(label) + ": " + escape(str(value)) for label, value in rows) + "</qt>"


from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QComboBox


class AccountSelector(QComboBox):
    """Notify the application when a mouse or keyboard opens the account list."""
    opening = pyqtSignal()

    def showPopup(self):
        self.opening.emit()
        super().showPopup()
