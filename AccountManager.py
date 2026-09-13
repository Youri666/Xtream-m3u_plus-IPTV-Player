"""Compatibility import for the account management dialogs.

New code should import these dialogs from ``iptv_player.ui.dialogs.accounts``.
"""

from iptv_player.ui.dialogs.accounts import AccountDialog, AccountManager

__all__ = ["AccountDialog", "AccountManager"]
