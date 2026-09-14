from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from iptv_player.config import (
    account_name_error,
    delete_account,
    load_account,
    load_accounts,
    load_startup_account,
    parse_account,
    save_account,
    save_startup_account,
)

class AccountManager(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("IPTV accounts")
        self.setMinimumSize(400, 300)
        self.parent = parent

        account_manager_layout = QtWidgets.QGridLayout(self)

        #Create startup account label with options widget
        self.startup_account_label = QLabel("Startup account:")

        self.startup_account_options = QtWidgets.QComboBox()
        self.startup_account_options.currentTextChanged.connect(self.set_startup_credentials)

        #Create accounts list
        self.accounts_list = QtWidgets.QListWidget()
        self.accounts_list.itemDoubleClicked.connect(self.double_click_account)

        #Create buttons for adding, selecting and deleting accounts
        self.add_button = QPushButton("Add")
        self.add_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogNewFolder))
        self.add_button.clicked.connect(self.add_account)

        self.select_button = QPushButton("Select")
        self.select_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogYesButton))
        self.select_button.clicked.connect(self.select_account)

        self.edit_button = QPushButton("Edit")
        self.edit_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogDetailedView))
        self.edit_button.clicked.connect(self.edit_account)

        self.delete_button = QPushButton("Delete")
        self.delete_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogCancelButton))
        self.delete_button.clicked.connect(self.delete_account)

        #Add widgets to layout
        account_manager_layout.addWidget(self.startup_account_label,        0, 0)
        account_manager_layout.addWidget(self.startup_account_options,      0, 1, 1, 2)
        account_manager_layout.addWidget(self.accounts_list,                1, 0, 1, 4)
        account_manager_layout.addWidget(self.add_button,                   2, 0)
        account_manager_layout.addWidget(self.select_button,                2, 1)
        account_manager_layout.addWidget(self.edit_button,                  2, 2)
        account_manager_layout.addWidget(self.delete_button,                2, 3)

        #Load saved accounts from .ini file
        self.load_saved_accounts()

    def set_startup_credentials(self):
        selected_item = self.startup_account_options.currentText()
        save_startup_account(self.parent.user_data_file, selected_item)

    def load_saved_accounts(self):
        self.startup_account_options.currentTextChanged.disconnect(self.set_startup_credentials)

        self.accounts_list.clear()
        self.startup_account_options.clear()
        self.startup_account_options.addItem("None")

        for name in load_accounts(self.parent.user_data_file):
            self.accounts_list.addItem(name)
            self.startup_account_options.addItem(name)

        selected_name = load_startup_account(self.parent.user_data_file)
        index = self.startup_account_options.findText(selected_name)
        self.startup_account_options.setCurrentIndex(max(0, index))

        self.startup_account_options.currentTextChanged.connect(self.set_startup_credentials)

    def edit_account(self):
        selected_item = self.accounts_list.currentItem()

        if selected_item:
            name = selected_item.text()
            editing_active_account = (
                getattr(self.parent, "active_account_name", "") == name
            )
            account_data = load_account(self.parent.user_data_file, name)
            if account_data is not None:
                parts = account_data.split('|')
                method = parts[0]
                credentials = parts[1:]

                dialog = AccountDialog(self, AccountDialog.MODE_EDIT, (method, name, *credentials))
                self.parent._prepare_dialog_theme(dialog)

                if dialog.exec_() == QtWidgets.QDialog.Accepted:
                    updated_method, updated_name, *updated_credentials = dialog.get_credentials()

                    if updated_name:
                        # Create a dictionary with the updated credentials
                        credentials_dict = {
                            'method': updated_method,
                            'old_name': name,
                            'name': updated_name,
                            'credentials': updated_credentials
                        }
                        self.save_credentials(credentials_dict)
                        self.load_saved_accounts()
                        if editing_active_account:
                            # Reapply changed URLs and credentials immediately so
                            # the in-memory catalog never keeps stale stream links.
                            self._activate_account(updated_name)

    def add_account(self):
        dialog = AccountDialog(self, AccountDialog.MODE_ADD)
        self.parent._prepare_dialog_theme(dialog)

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            method, name, *credentials = dialog.get_credentials()

            if name:
                # Create a dictionary with the new credentials
                credentials_dict = {
                    'method': method,
                    'name': name,
                    'credentials': credentials
                }
                self.save_credentials(credentials_dict)
                self.load_saved_accounts()

    def save_credentials(self, credentials_dict):
        method = credentials_dict['method']
        name = credentials_dict['name']
        credentials = credentials_dict['credentials']
        save_account(
            self.parent.user_data_file,
            method,
            name,
            credentials,
            old_name=credentials_dict.get('old_name'),
        )

    def select_account(self):
        selected_item = self.accounts_list.currentItem()

        if selected_item and self._activate_account(selected_item.text()):
            self.accept()

    def _activate_account(self, name):
        """Load one saved account into the application and refresh its catalog."""
        parsed_account = parse_account(
            load_account(self.parent.user_data_file, name)
        )
        if parsed_account is None:
            return False
        method, fields = parsed_account

        if method == "manual":
            (
                server,
                username,
                password,
                live_url_format,
                movie_url_format,
                series_url_format,
            ) = fields

            self.parent.server = server
            self.parent.username = username
            self.parent.password = password
            self.parent.live_url_format = live_url_format
            self.parent.movie_url_format = movie_url_format
            self.parent.series_url_format = series_url_format
            self.parent.set_active_account(name)
            self.parent.login()
            return True

        if method == "m3u_plus":
            (
                m3u_url,
                live_url_format,
                movie_url_format,
                series_url_format,
            ) = fields

            self.parent.live_url_format = live_url_format
            self.parent.movie_url_format = movie_url_format
            self.parent.series_url_format = series_url_format

            if self.parent.extract_credentials_from_m3u_plus_url(m3u_url):
                self.parent.set_active_account(name)
                self.parent.login()
                return True

        return False

    def double_click_account(self, item):
        self.select_account()
        self.accept()

    def delete_account(self):
        selected_item = self.accounts_list.currentItem()

        if selected_item:
            name = selected_item.text()

            if delete_account(self.parent.user_data_file, name):
                self.load_saved_accounts()

class AccountDialog(QtWidgets.QDialog):
    MODE_ADD = "add"
    MODE_EDIT = "edit"

    def __init__(self, parent=None, mode=MODE_ADD, account=None):
        super().__init__(parent)
        self.parent = parent
        self.mode = mode
        self.account = account
        self.setWindowTitle("Edit Credentials" if self.mode == self.MODE_EDIT else "Add Credentials")
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        self.manual_entry_name    = "Manual/Xtream entry"
        self.m3u_plus_entry_name  = "M3U_plus URL entry"
        self.default_url_formats  = self.parent.parent.default_url_formats

        # Connection method
        self.method_selector = QtWidgets.QComboBox()
        self.method_selector.addItems([self.manual_entry_name, self.m3u_plus_entry_name])
        layout.addWidget(QtWidgets.QLabel("Select Method:"))
        layout.addWidget(self.method_selector)

        # Stack of forms
        self.stack = QtWidgets.QStackedWidget()
        layout.addWidget(self.stack)

        # Manual form
        self.manual_form = QtWidgets.QWidget()
        manual_layout = QFormLayout(self.manual_form)

        self.name_entry_manual  = QLineEdit()
        self.server_entry       = QLineEdit()
        self.username_entry     = QLineEdit()
        self.password_entry     = QLineEdit()

        self.live_url_format_entry = QLineEdit(self.default_url_formats['live'])
        self.movie_url_format_entry = QLineEdit(self.default_url_formats['movie'])
        self.series_url_format_entry = QLineEdit(self.default_url_formats['series'])

        manual_layout.addRow("Name:", self.name_entry_manual)
        manual_layout.addRow("Server URL:", self.server_entry)
        manual_layout.addRow("Username:", self.username_entry)
        manual_layout.addRow("Password:", self.password_entry)
        manual_layout.addRow("Live URL Format:", self.live_url_format_entry)
        manual_layout.addRow("Movie URL Format:", self.movie_url_format_entry)
        manual_layout.addRow("Series URL Format:", self.series_url_format_entry)

        #Set placeholder texts for xtream credentials
        self.name_entry_manual.setPlaceholderText("Custom account name")
        self.server_entry.setPlaceholderText("e.g. http://xtreamcode.ex/")
        self.username_entry.setPlaceholderText("e.g. abcde12345")
        self.password_entry.setPlaceholderText("e.g. fghij67890")

        # M3U form
        self.m3u_form = QtWidgets.QWidget()
        m3u_layout = QFormLayout(self.m3u_form)

        self.name_entry_m3u = QLineEdit()
        self.m3u_url_entry  = QLineEdit()

        self.m3u_live_url_format_entry = QLineEdit(self.default_url_formats['live'])
        self.m3u_movie_url_format_entry = QLineEdit(self.default_url_formats['movie'])
        self.m3u_series_url_format_entry = QLineEdit(self.default_url_formats['series'])

        m3u_layout.addRow("Name:", self.name_entry_m3u)
        m3u_layout.addRow("m3u_plus URL:", self.m3u_url_entry)
        m3u_layout.addRow("Live URL Format:", self.m3u_live_url_format_entry)
        m3u_layout.addRow("Movie URL Format:", self.m3u_movie_url_format_entry)
        m3u_layout.addRow("Series URL Format:", self.m3u_series_url_format_entry)

        #Set placeholder texts for m3u credentials
        self.name_entry_m3u.setPlaceholderText("Custom account name")
        self.m3u_url_entry.setPlaceholderText("e.g. http://xtreamcode.ex/get.php?username=Mike&password=1234&type=m3u_plus&output=ts")

        self.stack.addWidget(self.manual_form)
        self.stack.addWidget(self.m3u_form)

        self.method_selector.currentIndexChanged.connect(self.stack.setCurrentIndex)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

        # Set form data if in edit mode
        if self.mode == self.MODE_EDIT and self.account:
            method, *credentials = self.account
            if method == 'manual':
                self.method_selector.setCurrentText(self.manual_entry_name)
                self.name_entry_manual.setText(credentials[0])
                self.server_entry.setText(credentials[1])
                self.username_entry.setText(credentials[2])
                self.password_entry.setText(credentials[3])
                self.live_url_format_entry.setText(credentials[4])
                self.movie_url_format_entry.setText(credentials[5])
                self.series_url_format_entry.setText(credentials[6])
            else:
                self.method_selector.setCurrentText(self.m3u_plus_entry_name)
                self.name_entry_m3u.setText(credentials[0])
                self.m3u_url_entry.setText(credentials[1])
                self.m3u_live_url_format_entry.setText(credentials[2])
                self.m3u_movie_url_format_entry.setText(credentials[3])
                self.m3u_series_url_format_entry.setText(credentials[4])

        self._resize_for_url_fields()

    def _resize_for_url_fields(self):
        """Choose a readable initial width while keeping the dialog resizable."""
        fields = (
            self.server_entry,
            self.live_url_format_entry,
            self.movie_url_format_entry,
            self.series_url_format_entry,
            self.m3u_url_entry,
            self.m3u_live_url_format_entry,
            self.m3u_movie_url_format_entry,
            self.m3u_series_url_format_entry,
        )
        metrics = self.fontMetrics()
        content_width = max(
            metrics.horizontalAdvance(field.text() or field.placeholderText())
            for field in fields
        )
        target_width = max(850, content_width + 220)

        screen = QtWidgets.QApplication.primaryScreen()
        if screen is not None:
            target_width = min(target_width, int(screen.availableGeometry().width() * 0.9))

        self.resize(target_width, self.sizeHint().height())
    
    def validate_and_accept(self):
        method = self.method_selector.currentText()

        if method == self.manual_entry_name:
            name        = self.name_entry_manual.text().strip()
            server      = self.server_entry.text().strip()
            username    = self.username_entry.text().strip()
            password    = self.password_entry.text().strip()

            if not name or not server or not username or not password:
                QtWidgets.QMessageBox.warning(self, "Input Error", "Please fill all fields for Manual Entry.")
                return
        else:
            name    = self.name_entry_m3u.text().strip()
            m3u_url = self.m3u_url_entry.text().strip()

            if not name or not m3u_url:
                QtWidgets.QMessageBox.warning(self, "Input Error", "Please fill all fields for m3u_plus URL Entry.")
                return

        validation_error = account_name_error(name)
        if validation_error:
            QtWidgets.QMessageBox.warning(self, "Invalid Account Name", validation_error)
            return

        existing_names = load_accounts(self.parent.parent.user_data_file)
        original_name = self.account[1] if self.account else None
        duplicate_name = next(
            (
                existing_name
                for existing_name in existing_names
                if existing_name.casefold() == name.casefold()
                and (
                    original_name is None
                    or existing_name.casefold() != original_name.casefold()
                )
            ),
            None,
        )
        if duplicate_name:
            QtWidgets.QMessageBox.warning(
                self,
                "Duplicate Account Name",
                f"An account named '{duplicate_name}' already exists.",
            )
            return

        self.accept()

    def get_credentials(self):
        method = self.method_selector.currentText()

        if method == self.manual_entry_name:
            name              = self.name_entry_manual.text().strip()
            server            = self.server_entry.text().strip()
            username          = self.username_entry.text().strip()
            password          = self.password_entry.text().strip()
            live_url_format   = self.live_url_format_entry.text().strip()
            movie_url_format  = self.movie_url_format_entry.text().strip()
            series_url_format = self.series_url_format_entry.text().strip()

            return ('manual', name, server, username, password, live_url_format, movie_url_format, series_url_format)
        else:
            name              = self.name_entry_m3u.text().strip()
            m3u_url           = self.m3u_url_entry.text().strip()
            live_url_format   = self.m3u_live_url_format_entry.text().strip()
            movie_url_format  = self.m3u_movie_url_format_entry.text().strip()
            series_url_format = self.m3u_series_url_format_entry.text().strip()

            return ('m3u_plus', name, m3u_url, live_url_format, movie_url_format, series_url_format)
