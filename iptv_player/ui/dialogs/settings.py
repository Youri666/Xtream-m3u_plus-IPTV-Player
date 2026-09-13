"""Settings dialogs used by the main IPTV Player window."""

from PyQt5.QtCore import QLocale, Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from iptv_player.constants import MEDIA_LANGUAGE_OPTIONS
from iptv_player.provider.client import DEFAULT_USER_AGENT_HEADER
from iptv_player.provider.network import (
    DEFAULT_ACCOUNT_INFO_REFRESH_INTERVAL,
    DEFAULT_CATALOG_CACHE_MAX_AGE_HOURS,
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_LIVE_STATUS_RETRIES,
    DEFAULT_LIVE_STATUS_TIMEOUT,
    DEFAULT_READ_TIMEOUT,
    MAX_LIVE_STATUS_RETRIES,
    NETWORK_SETTINGS,
)


class NetworkSettingsDialog(QDialog):
    """Edit advanced provider and network preferences in a compact dialog."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent_app = parent
        self.setWindowTitle("Advanced settings")
        self.setModal(True)

        main_layout = QVBoxLayout(self)

        general_group = QGroupBox("General network")
        general_form = QFormLayout(general_group)

        self.user_agent_box = QComboBox()
        self.user_agent_box.addItems(parent.user_agents)
        self.user_agent_box.setCurrentText(parent.current_user_agent)
        # A full User-Agent can be very long. Give the combo box a practical size
        # hint so adjustSize() fits the form without making the dialog excessively wide.
        self.user_agent_box.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.user_agent_box.setMinimumContentsLength(40)
        self.user_agent_box.setToolTip("User-Agent sent with IPTV provider requests")

        self.connection_timeout_spin = self._create_seconds_spinbox(
            NETWORK_SETTINGS.connection_timeout,
            "Maximum time allowed to establish a connection"
        )
        self.read_timeout_spin = self._create_seconds_spinbox(
            NETWORK_SETTINGS.read_timeout,
            "Maximum time allowed while waiting for regular response data"
        )

        general_form.addRow("User-Agent:", self.user_agent_box)
        general_form.addRow("Connection timeout:", self.connection_timeout_spin)
        general_form.addRow("Read timeout:", self.read_timeout_spin)

        self.account_refresh_checkbox = QCheckBox("Enable automatic Info refresh")
        self.account_refresh_checkbox.setChecked(parent.account_info_auto_refresh_enabled)
        self.account_refresh_checkbox.setToolTip(
            "Refresh account information periodically while the Info tab is visible"
        )
        self.account_refresh_spin = self._create_seconds_spinbox(
            parent.account_info_refresh_interval,
            "Automatic account information refresh interval while the Info tab is visible"
        )
        self.account_refresh_spin.setRange(10, 3600)
        self.account_refresh_checkbox.toggled.connect(
            self.account_refresh_spin.setEnabled
        )
        self.account_refresh_spin.setEnabled(
            self.account_refresh_checkbox.isChecked()
        )
        general_form.addRow(self.account_refresh_checkbox)
        general_form.addRow("Info auto-refresh interval:", self.account_refresh_spin)

        cache_group = QGroupBox("Provider catalog cache")
        cache_form = QFormLayout(cache_group)
        self.catalog_cache_checkbox = QCheckBox("Use cached provider catalogs")
        self.catalog_cache_checkbox.setChecked(parent.catalog_cache_enabled)
        self.catalog_cache_checkbox.setToolTip(
            "Reuse LIVE, Movies, and Series data until the cache expires"
        )
        self.catalog_cache_hours_spin = QSpinBox()
        self.catalog_cache_hours_spin.setRange(1, 720)
        self.catalog_cache_hours_spin.setSuffix(" h")
        self.catalog_cache_hours_spin.setValue(parent.catalog_cache_max_age_hours)
        self.catalog_cache_hours_spin.setToolTip(
            "Fetch fresh provider catalogs on the next account load after this age"
        )
        self.catalog_cache_checkbox.toggled.connect(
            self.catalog_cache_hours_spin.setEnabled
        )
        self.catalog_cache_hours_spin.setEnabled(
            self.catalog_cache_checkbox.isChecked()
        )
        self.refresh_catalog_button = QPushButton("Refresh provider catalog now")
        self.refresh_catalog_button.clicked.connect(self.refresh_catalog_now)
        cache_form.addRow(self.catalog_cache_checkbox)
        cache_form.addRow("Refresh after:", self.catalog_cache_hours_spin)
        cache_form.addRow(self.refresh_catalog_button)

        live_group = QGroupBox("LIVE stream status")
        live_layout = QVBoxLayout(live_group)
        self.live_status_checkbox = QCheckBox("Enable LIVE stream status checks")
        self.live_status_checkbox.setToolTip(
            "Probe the selected LIVE channel and display its green/red status indicator"
        )
        self.live_status_checkbox.setChecked(parent.stream_status_enabled)
        live_layout.addWidget(self.live_status_checkbox)

        # Put the dependent controls in their own widget so disabling status checks
        # also grays their labels, while the enabling checkbox remains clickable.
        self.live_options_widget = QWidget()
        live_form = QFormLayout(self.live_options_widget)
        live_form.setContentsMargins(0, 0, 0, 0)
        self.live_timeout_spin = self._create_seconds_spinbox(
            NETWORK_SETTINGS.live_status_timeout,
            "Maximum wait for each LIVE status attempt"
        )
        self.live_retries_spin = QSpinBox()
        self.live_retries_spin.setRange(0, MAX_LIVE_STATUS_RETRIES)
        self.live_retries_spin.setValue(NETWORK_SETTINGS.live_status_retries)
        self.live_retries_spin.setToolTip(
            "Number of additional attempts after the initial LIVE status request"
        )
        live_form.addRow("Timeout per attempt:", self.live_timeout_spin)
        live_form.addRow("Additional retries:", self.live_retries_spin)
        live_layout.addWidget(self.live_options_widget)

        self.live_status_checkbox.toggled.connect(self.live_options_widget.setEnabled)
        self.live_options_widget.setEnabled(self.live_status_checkbox.isChecked())

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Save
            | QDialogButtonBox.Cancel
            | QDialogButtonBox.RestoreDefaults
        )
        self.button_box.accepted.connect(self.save_settings)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.RestoreDefaults).clicked.connect(
            self.restore_defaults
        )

        main_layout.addWidget(general_group)
        main_layout.addWidget(cache_group)
        main_layout.addWidget(live_group)
        main_layout.addWidget(self.button_box)

        # Compute the initial dimensions only after every control has been added.
        # QDialog remains freely resizable because no fixed size is imposed.
        main_layout.activate()
        self.adjustSize()

    @staticmethod
    def _create_seconds_spinbox(value, tooltip):
        """Create a consistently bounded timeout editor."""
        spinbox = QSpinBox()
        spinbox.setRange(1, 999)
        spinbox.setSuffix(" s")
        spinbox.setValue(value)
        spinbox.setToolTip(tooltip)
        return spinbox

    def restore_defaults(self):
        """Restore the documented defaults without closing or saving the dialog."""
        self.user_agent_box.setCurrentText(DEFAULT_USER_AGENT_HEADER)
        self.connection_timeout_spin.setValue(DEFAULT_CONNECTION_TIMEOUT)
        self.read_timeout_spin.setValue(DEFAULT_READ_TIMEOUT)
        self.live_status_checkbox.setChecked(True)
        self.live_timeout_spin.setValue(DEFAULT_LIVE_STATUS_TIMEOUT)
        self.live_retries_spin.setValue(DEFAULT_LIVE_STATUS_RETRIES)
        self.account_refresh_spin.setValue(
            DEFAULT_ACCOUNT_INFO_REFRESH_INTERVAL
        )
        self.account_refresh_checkbox.setChecked(True)
        self.catalog_cache_checkbox.setChecked(True)
        self.catalog_cache_hours_spin.setValue(
            DEFAULT_CATALOG_CACHE_MAX_AGE_HOURS
        )

    def save_settings(self, force_catalog_refresh=False):
        """Apply the complete dialog state as one coherent configuration update."""
        self.parent_app.applyNetworkSettings(
            self.user_agent_box.currentText(),
            self.connection_timeout_spin.value(),
            self.read_timeout_spin.value(),
            self.live_timeout_spin.value(),
            self.live_retries_spin.value(),
            self.live_status_checkbox.isChecked(),
            self.account_refresh_spin.value(),
            self.account_refresh_checkbox.isChecked(),
            self.catalog_cache_checkbox.isChecked(),
            self.catalog_cache_hours_spin.value()
        )
        if force_catalog_refresh:
            self.parent_app.refreshProviderCatalog()
        self.accept()

    def refresh_catalog_now(self):
        """Save current settings and explicitly bypass the catalog cache once."""
        self.save_settings(force_catalog_refresh=True)


class CategoryVisibilityDialog(QDialog):
    """Choose which provider categories remain visible for one content type."""

    def __init__(self, parent, stream_type, categories, hidden_category_ids):
        super().__init__(parent)
        self.setWindowTitle(f"Select {stream_type} categories")
        self.setModal(True)
        self.resize(520, 620)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Checked categories are displayed. New provider categories are "
            "automatically checked."
        ))

        self.category_list = QListWidget()
        for category in sorted(
            categories,
            key=lambda entry: entry.get('category_name', '').casefold()
        ):
            category_id = str(category.get('category_id', ''))
            item = QListWidgetItem(category.get('category_name', ''))
            item.setData(Qt.UserRole, category_id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(
                Qt.Unchecked if category_id in hidden_category_ids else Qt.Checked
            )
            self.category_list.addItem(item)
        layout.addWidget(self.category_list)

        selection_buttons = QHBoxLayout()
        select_all_button = QPushButton("Select all")
        deselect_all_button = QPushButton("Deselect all")
        select_all_button.clicked.connect(lambda: self.set_all_checked(True))
        deselect_all_button.clicked.connect(lambda: self.set_all_checked(False))
        selection_buttons.addWidget(select_all_button)
        selection_buttons.addWidget(deselect_all_button)
        selection_buttons.addStretch()
        layout.addLayout(selection_buttons)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def set_all_checked(self, checked):
        """Apply one check state to every provider category in the dialog."""
        check_state = Qt.Checked if checked else Qt.Unchecked
        for row in range(self.category_list.count()):
            self.category_list.item(row).setCheckState(check_state)

    def hidden_category_ids(self):
        """Return only unchecked ids so future categories stay visible by default."""
        return {
            self.category_list.item(row).data(Qt.UserRole)
            for row in range(self.category_list.count())
            if self.category_list.item(row).checkState() != Qt.Checked
        }


class InternalPlayerSettingsDialog(QDialog):
    """Edit keyboard, mouse, and transport steps for the internal player."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Internal player settings")
        layout = QFormLayout(self)

        self.seek_step = QSpinBox()
        self.seek_step.setRange(1, 300)
        self.seek_step.setSuffix(" seconds")
        self.seek_step.setValue(parent.internal_seek_step_seconds)
        self.seek_step.setToolTip("Amount used by seek buttons and Left/Right arrows")

        self.volume_step = QSpinBox()
        self.volume_step.setRange(1, 25)
        self.volume_step.setSuffix(" %")
        self.volume_step.setValue(parent.internal_volume_step_percent)
        self.volume_step.setToolTip("Amount used by Up/Down arrows and the mouse wheel")

        self.speed_step = QDoubleSpinBox()
        self.speed_step.setRange(0.05, 1.00)
        self.speed_step.setSingleStep(0.05)
        self.speed_step.setDecimals(2)
        self.speed_step.setSuffix("×")
        # Keep the decimal separator consistent with the English-only interface
        # and with the speed value displayed by the internal player.
        self.speed_step.setLocale(QLocale.c())
        self.speed_step.setValue(parent.internal_speed_step)
        self.speed_step.setToolTip("Amount used by the slower/faster buttons and +/- keys")

        self.audio_language = QComboBox()
        self.audio_language.addItem("VLC default", "")
        for language_name, language_code in MEDIA_LANGUAGE_OPTIONS:
            self.audio_language.addItem(language_name, language_code)
        audio_index = self.audio_language.findData(parent.internal_audio_language)
        self.audio_language.setCurrentIndex(max(0, audio_index))

        self.subtitle_language = QComboBox()
        self.subtitle_language.addItem("VLC default", "")
        self.subtitle_language.addItem("Disabled", "disabled")
        for language_name, language_code in MEDIA_LANGUAGE_OPTIONS:
            self.subtitle_language.addItem(language_name, language_code)
        subtitle_index = self.subtitle_language.findData(parent.internal_subtitle_language)
        self.subtitle_language.setCurrentIndex(max(0, subtitle_index))

        layout.addRow("Seek step:", self.seek_step)
        layout.addRow("Volume step:", self.volume_step)
        layout.addRow("Playback speed step:", self.speed_step)
        layout.addRow("Preferred audio:", self.audio_language)
        layout.addRow("Preferred subtitles:", self.subtitle_language)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


