"""Check account isolation, legacy compatibility and account form presets."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from PyQt5 import QtWidgets
from iptv_player.config.accounts import save_account, load_account_user_agent
from iptv_player.provider.client import DEFAULT_USER_AGENT_HEADER, VLC_USER_AGENT_HEADER
from iptv_player.ui.dialogs.accounts import AccountDialog

class AccountUserAgentTests(unittest.TestCase):
    def test_legacy_value_and_account_isolation_survive_rename(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            filename.write_text("[User-Agent]\nuser-agent = Legacy client\n")
            credentials = ["https://example.test", "user", "pass", "live", "movie", "series"]
            save_account(filename, "manual", "First", credentials)
            save_account(filename, "manual", "Second", credentials, user_agent=VLC_USER_AGENT_HEADER)
            self.assertEqual(load_account_user_agent(filename, "First"), "Legacy client")
            self.assertEqual(load_account_user_agent(filename, "Second"), VLC_USER_AGENT_HEADER)
            save_account(filename, "manual", "Renamed", credentials, old_name="Second")
            self.assertEqual(load_account_user_agent(filename, "Renamed"), VLC_USER_AGENT_HEADER)

    def test_form_presets_and_custom_value(self):
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "userdata.ini"
            credentials = ["https://example.test", "user", "pass", "live", "movie", "series"]
            save_account(filename, "manual", "First", credentials, user_agent="Custom old client")
            manager = QtWidgets.QDialog()
            manager.parent = SimpleNamespace(user_data_file=filename, default_url_formats={"live":"live", "movie":"movie", "series":"series"})
            dialog = AccountDialog(manager, AccountDialog.MODE_EDIT, ("manual", "First", *credentials))
            dialog.show()
            app.processEvents()
            self.assertEqual(dialog.selected_user_agent(), "Custom old client")
            self.assertFalse(dialog.user_agent_entry.isReadOnly())
            menu = next(button.menu() for button in dialog.findChildren(QtWidgets.QToolButton)
                        if button.accessibleName() == "Choose a User-Agent preset")
            menu.actions()[1].trigger()
            self.assertEqual(dialog.selected_user_agent(), VLC_USER_AGENT_HEADER)
            self.assertFalse(dialog.user_agent_entry.isReadOnly())
            dialog.user_agent_entry.setText("Edited preset")
            self.assertEqual(dialog.selected_user_agent(), "Edited preset")
            menu.actions()[0].trigger()
            self.assertEqual(dialog.selected_user_agent(), DEFAULT_USER_AGENT_HEADER)
            self.assertEqual(dialog.user_agent_entry.geometry().left(), dialog.epg_offset_minutes.geometry().left())
            dialog.close()
