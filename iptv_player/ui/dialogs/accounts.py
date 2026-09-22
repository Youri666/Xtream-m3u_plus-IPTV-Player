from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from iptv_player.config import (
    account_name_error,
    load_account,
    load_account_epg_offset,
    load_accounts,
    save_account,
)
from iptv_player.provider.credentials import parse_xtream_m3u_url
from iptv_player.provider.workers import AccountInfoWorker

class AccountManager(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setWindowTitle("IPTV accounts")
        self.setMinimumSize(400, 300)
        self.parent = parent

        account_manager_layout = QtWidgets.QGridLayout(self)

        #Create accounts list
        self.accounts_list = QtWidgets.QListWidget()

        #Create buttons for adding, selecting and deleting accounts
        self.add_button = QPushButton("Add")
        self.add_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogNewFolder))
        self.add_button.clicked.connect(self.add_account)

        self.edit_button = QPushButton("Edit")
        self.edit_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogDetailedView))
        self.edit_button.clicked.connect(self.edit_account)

        self.delete_button = QPushButton("Delete")
        self.delete_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogCancelButton))
        self.delete_button.clicked.connect(self.delete_account)

        #Add widgets to layout
        account_manager_layout.addWidget(self.accounts_list,                0, 0, 1, 3)
        account_manager_layout.addWidget(self.add_button,                   1, 0)
        account_manager_layout.addWidget(self.edit_button,                  1, 1)
        account_manager_layout.addWidget(self.delete_button,                1, 2)

        #Load saved accounts from .ini file
        self.load_saved_accounts()

    def load_saved_accounts(self):
        self.accounts_list.clear()

        for name in load_accounts(self.parent.user_data_file):
            self.accounts_list.addItem(name)

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
                            'credentials': updated_credentials,
                            'epg_offset_minutes': dialog.epg_offset_minutes.value(),
                        }
                        self.save_credentials(credentials_dict)
                        self.load_saved_accounts()
                        if editing_active_account:
                            # Reapply changed URLs and credentials immediately so
                            # the in-memory catalog never keeps stale stream links.
                            self.parent.activate_saved_account(updated_name)

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
                    'credentials': credentials,
                    'epg_offset_minutes': dialog.epg_offset_minutes.value(),
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
            epg_offset_minutes=credentials_dict.get('epg_offset_minutes', 0),
        )

    def delete_account(self):
        selected_item = self.accounts_list.currentItem()

        if selected_item:
            name = selected_item.text()

            if self.parent.delete_saved_account(name):
                self.load_saved_accounts()

class AccountDialog(QtWidgets.QDialog):
    MODE_ADD = "add"
    MODE_EDIT = "edit"

    def __init__(self, parent=None, mode=MODE_ADD, account=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.parent = parent
        self.mode = mode
        self.account = account
        self.setWindowTitle("Edit Credentials" if self.mode == self.MODE_EDIT else "Add Credentials")
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        self.manual_entry_name    = "Manual/Xtream entry"
        self.m3u_plus_entry_name  = "Xtream M3U Plus URL"
        self.default_url_formats  = self.parent.parent.default_url_formats

        # Connection method
        self.method_selector = QtWidgets.QComboBox()
        self.method_selector.addItems([self.manual_entry_name, self.m3u_plus_entry_name])
        layout.addWidget(QtWidgets.QLabel("Select method"))
        layout.addWidget(self.method_selector)

        # Stack of forms
        self.stack = QtWidgets.QStackedWidget()
        layout.addWidget(self.stack)

        # Manual form
        self.manual_form = QtWidgets.QWidget()
        manual_layout = QFormLayout(self.manual_form)
        manual_layout.setContentsMargins(9, 9, 9, 0)

        self.name_entry_manual  = QLineEdit()
        self.server_entry       = QLineEdit()
        self.username_entry     = QLineEdit()
        self.password_entry     = QLineEdit()

        self.live_url_format_entry = QLineEdit(self.default_url_formats['live'])
        self.movie_url_format_entry = QLineEdit(self.default_url_formats['movie'])
        self.series_url_format_entry = QLineEdit(self.default_url_formats['series'])

        live_format_tooltip = (
            "<b>Live TV not working while Movies and Series do?</b><br>"
            "Some providers require a different Live URL format. Try one of these:<br><br>"
            "{server}/{username}/{password}/{stream_id}<br>"
            "{server}/{username}/{password}/{stream_id}.ts<br>"
            "{server}/{username}/{password}/{stream_id}.m3u8<br>"
            "{server}/{username}/{password}/live/{stream_id}<br>"
            "{server}/{username}/{password}/live/{stream_id}.ts<br>"
            "{server}/{username}/{password}/live/{stream_id}.m3u8<br>"
            "{server}/live/{username}/{password}/{stream_id}<br>"
            "{server}/live/{username}/{password}/{stream_id}.ts<br>"
            "{server}/live/{username}/{password}/{stream_id}.m3u8"
        )
        self.live_url_format_entry.setToolTip(live_format_tooltip)

        manual_layout.addRow("Name", self.name_entry_manual)
        manual_layout.addRow("Server URL", self.server_entry)
        manual_layout.addRow("Username", self.username_entry)
        manual_layout.addRow("Password", self.password_entry)
        manual_layout.addRow("Live URL format", self.live_url_format_entry)
        manual_layout.addRow("Movie URL format", self.movie_url_format_entry)
        manual_layout.addRow("Series URL format", self.series_url_format_entry)

        #Set placeholder texts for xtream credentials
        self.name_entry_manual.setPlaceholderText("Custom account name")
        self.server_entry.setPlaceholderText("e.g. http://xtreamcode.ex/")
        self.username_entry.setPlaceholderText("e.g. abcde12345")
        self.password_entry.setPlaceholderText("e.g. fghij67890")

        # M3U form
        self.m3u_form = QtWidgets.QWidget()
        m3u_layout = QFormLayout(self.m3u_form)
        m3u_layout.setContentsMargins(9, 9, 9, 0)

        self.name_entry_m3u = QLineEdit()
        self.m3u_url_entry  = QLineEdit()

        self.m3u_live_url_format_entry = QLineEdit(self.default_url_formats['live'])
        self.m3u_movie_url_format_entry = QLineEdit(self.default_url_formats['movie'])
        self.m3u_series_url_format_entry = QLineEdit(self.default_url_formats['series'])
        self.m3u_live_url_format_entry.setToolTip(live_format_tooltip)

        m3u_layout.addRow("Name", self.name_entry_m3u)
        m3u_layout.addRow("Xtream get.php URL", self.m3u_url_entry)
        m3u_layout.addRow("Live URL format", self.m3u_live_url_format_entry)
        m3u_layout.addRow("Movie URL format", self.m3u_movie_url_format_entry)
        m3u_layout.addRow("Series URL format", self.m3u_series_url_format_entry)

        #Set placeholder texts for m3u credentials
        self.name_entry_m3u.setPlaceholderText("Custom account name")
        self.m3u_url_entry.setPlaceholderText("e.g. http://xtreamcode.ex/get.php?username=Mike&password=1234&type=m3u_plus&output=ts")

        self.stack.addWidget(self.manual_form)
        self.stack.addWidget(self.m3u_form)

        self.m3u_explanation = QLabel(
            "This option accepts an Xtream get.php URL containing account "
            "credentials. Generic M3U playlist files and URLs are not supported."
        )
        self.m3u_explanation.setWordWrap(True)
        layout.addWidget(self.m3u_explanation)

        self.epg_offset_minutes = QSpinBox()
        self.epg_offset_minutes.setRange(-720, 720)
        self.epg_offset_minutes.setSingleStep(30)
        self.epg_offset_minutes.setSuffix(" minutes")
        self.epg_offset_minutes.setToolTip(
            "Shift this account's EPG times from -12 to +12 hours"
        )
        self.epg_offset_minutes.setFixedWidth(150)
        epg_layout = QtWidgets.QHBoxLayout()
        epg_layout.setContentsMargins(9, 0, 9, 0)
        epg_layout.setSpacing(6)
        epg_label = QLabel("EPG time offset")
        label_column_width = self.fontMetrics().horizontalAdvance(
            "Series URL format"
        )
        epg_label.setFixedWidth(label_column_width)
        epg_layout.addWidget(epg_label)
        epg_layout.addWidget(self.epg_offset_minutes)
        epg_layout.addStretch()
        layout.addLayout(epg_layout)

        self.method_selector.currentIndexChanged.connect(self._method_changed)

        test_layout = QtWidgets.QHBoxLayout()
        self.test_connection_button = QPushButton("Test connection")
        self.test_connection_button.clicked.connect(self.test_connection)
        self.test_connection_status = QLabel()
        self.test_connection_status.setWordWrap(True)
        test_layout.addWidget(self.test_connection_button)
        test_layout.addWidget(self.test_connection_status, 1)
        layout.addLayout(test_layout)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

        # Set form data if in edit mode
        if self.mode == self.MODE_EDIT and self.account:
            method, *credentials = self.account
            self.epg_offset_minutes.setValue(
                load_account_epg_offset(
                    self.parent.parent.user_data_file, credentials[0]
                )
            )
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

        self._method_changed(self.method_selector.currentIndex())

        self._resize_for_url_fields()

    def _method_changed(self, index):
        """Switch credential forms and explain the Xtream-only URL mode."""
        self.stack.setCurrentIndex(index)
        self.m3u_explanation.setVisible(index == 1)

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

    def _connection_credentials(self):
        """Return the currently entered server credentials without saving them."""
        if self.method_selector.currentText() == self.manual_entry_name:
            server = self.server_entry.text().strip()
            username = self.username_entry.text().strip()
            password = self.password_entry.text().strip()
            if server and username and password:
                return server, username, password
            return None
        return parse_xtream_m3u_url(self.m3u_url_entry.text().strip())

    def test_connection(self):
        """Check account metadata without downloading any provider catalog."""
        credentials = self._connection_credentials()
        if credentials is None:
            self._show_connection_result(
                False,
                "Enter a valid server URL, username, and password first.",
                title="Incomplete credentials",
            )
            return

        server, username, password = credentials
        self.test_connection_button.setEnabled(False)
        self.test_connection_status.setText("Testing…")
        main_window = self.parent.parent
        worker = AccountInfoWorker(
            server,
            username,
            password,
            main_window.current_user_agent,
        )
        worker.signals.finished.connect(self._connection_test_finished)
        worker.signals.error.connect(self._connection_test_failed)
        self._connection_test_worker = worker
        main_window.account_info_threadpool.start(worker)

    def _connection_test_finished(self, account_info):
        """Display authentication and account status returned by the provider."""
        self._connection_test_worker = None
        self.test_connection_button.setEnabled(True)
        user_info = account_info.get("user_info", {})
        if not isinstance(user_info, dict):
            user_info = {}
        authenticated = str(user_info.get("auth", "0")) == "1"
        status = str(user_info.get("status", "Unknown"))
        if not authenticated:
            self._show_connection_result(
                False,
                "The provider responded, but the credentials were not accepted.",
            )
            return
        self._show_connection_result(
            True,
            f"The credentials are valid. Account status: {status}.",
        )

    def _connection_test_failed(self, _error):
        """Report a network or invalid-response failure without exposing secrets."""
        self._connection_test_worker = None
        self.test_connection_button.setEnabled(True)
        self._show_connection_result(
            False,
            "Could not retrieve account information. Check the server URL and "
            "your network connection, then try again.",
        )

    def _show_connection_result(self, success, message, title=""):
        """Show a detailed themed dialog and a compact inline status."""
        word = "OK" if success else "Failed"
        color = "#2ea44f" if success else "#d64545"
        self.test_connection_status.setText(
            f'<span style="color:{color}">●</span> {word}'
        )

        dialog = QtWidgets.QMessageBox(self)
        dialog.setWindowTitle(
            title or ("Connection successful" if success else "Connection failed")
        )
        dialog.setText(message)
        dialog.setIcon(
            QtWidgets.QMessageBox.Information
            if success else QtWidgets.QMessageBox.Warning
        )
        dialog.setStandardButtons(QtWidgets.QMessageBox.Ok)
        self.parent.parent._prepare_dialog_theme(dialog)
        dialog.exec_()
    
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
                QtWidgets.QMessageBox.warning(
                    self,
                    "Input Error",
                    "Please enter an account name and a valid Xtream get.php URL.",
                )
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
