import sys
import os
from os import path
import time
import requests
import subprocess
import configparser
import re
import json
import queue
import threading
import uuid
from collections import Counter
from multiprocessing.connection import Listener
from datetime import datetime
from PyQt5.QtGui import QIcon, QFont, QPixmap, QColor, QDesktopServices, QPainter
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize,
    QThreadPool, QUrl, QByteArray
)
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QLineEdit, QLabel, QPushButton,
    QListWidget, QWidget, QFileDialog, QCheckBox, QSizePolicy, QHBoxLayout,
    QDialog, QTabWidget, QListWidgetItem, QMenu, QAction, QActionGroup,
    QTextEdit, QGridLayout, QMessageBox, QListView, QTreeWidgetItem, QComboBox, QSplitter,
    QGroupBox, QRadioButton, QButtonGroup, QToolButton
)

from iptv_player.ui.info_panels import LiveInfoBox, MovieInfoBox, SeriesInfoBox
from iptv_player.ui.player import EmbeddedPlayerWindow
from iptv_player.bootstrap import configure_qt_application, install_logging
from iptv_player.constants import (
    CURRENT_CONFIG_SCHEMA_VERSION,
    CURRENT_VERSION,
    DEFAULT_INTERNAL_SEEK_STEP_SECONDS,
    DEFAULT_INTERNAL_SPEED_STEP,
    DEFAULT_INTERNAL_VOLUME_STEP_PERCENT,
    DEFAULT_URL_FORMATS,
    GITHUB_REPO,
    MEDIA_LANGUAGE_OPTIONS,
    REMEMBER_CATEGORY_SORTING,
)
from iptv_player.config import (
    application_resource_path,
    load_account,
    load_account_id,
    load_startup_account,
    migrate_legacy_player_volume,
    migrate_user_data_file,
    parse_account,
    writable_data_directory,
    write_config_file,
)
from iptv_player.ui.theme import (
    application_palette_is_dark,
    apply_application_theme,
    apply_windows_title_bar_theme,
)
from iptv_player.ui.dialogs.settings import (
    CategoryVisibilityDialog,
    InternalPlayerSettingsDialog,
    NetworkSettingsDialog,
)
from iptv_player.ui.dialogs.accounts import AccountManager
from iptv_player.ui.widgets import KeyboardNavigableListWidget
from iptv_player.utils.privacy import private_url_log_reference
from iptv_player.utils.search import (
    normalize_search_text,
    search_relevance_key,
    title_matches_search,
)
from iptv_player.utils.sorting import ordered_catalog_entries, ordered_season_keys
from iptv_player.storage import (
    account_favorites_file,
    entries_in_favorite_order,
    load_provider_preferences,
    migrate_legacy_favorites_file,
    provider_preferences_file,
    save_provider_preferences,
    set_favorite,
)
from iptv_player.provider.cache import account_cache_key
from iptv_player.provider.client import DEFAULT_USER_AGENT_HEADER
from iptv_player.provider.credentials import parse_xtream_m3u_url
from iptv_player.player_process import run_embedded_player_process
from iptv_player.external_player import (
    ExternalPlayerNotExecutableError,
    launch_external_player,
)
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
from iptv_player.provider.workers import (
    AccountInfoWorker,
    EPGWorker,
    FetchDataWorker,
    ImageFetcher,
    MovieInfoFetcher,
    OnlineWorker,
    SeriesInfoFetcher,
)

# CURRENT_CONFIG_SCHEMA_VERSION describes the structure and meaning of userdata.ini.
# Increment the schema only when a release changes persisted data and add a matching,
# ordered migration in migrate_user_data_file(). It is intentionally independent from
# CURRENT_VERSION because most application releases do not change persisted data.
is_windows  = sys.platform.startswith('win')



class IPTVPlayerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"IPTV Player {CURRENT_VERSION}")
        self.resize(1300, 900)

        self.user_agents = [
            "VLC/3.0.16 LibVLC/3.0.16", #VLC
            "Kodi/20.2 (Linux; Android 13; SM-G998B) Android/13 Sys_CPU/armv8a App_Bitness/64 Version/20.2-(20.2.0)-Git:20230626-abc123", #Kodi
            "Dalvik/2.1.0 (Linux; U; Android 13; Pixel 6 Pro Build/TQ2A.230505.002)", #MX Player
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36", #Windows Chrome
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0", #Windows Firefox
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Safari/605.1.15", #MacOS Safari
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.3351.83", #Windows Edge
            "Mozilla/5.0 (Linux; Android 14; Pixel 7 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36", #Android Chrome
            "Mozilla/5.0 (Android 14; Mobile; rv:126.0) Gecko/126.0 Firefox/126.0", #Android Firefox
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1", #iOS 17 Safari
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0", #Linux (Ubuntu + Chrome)
            "Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0", #Linux (Fedora + Firefox)
            "Mozilla/5.0 (X11; CrOS x86_64 15633.64.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", #ChromeOS
            "Mozilla/5.0 (Linux; Android 13; SAMSUNG SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/24.0 Chrome/124.0.0.0 Mobile Safari/537.36", #Samsung Internet
        ]
        self.current_user_agent = ""

        self.data_directory = writable_data_directory()
        os.makedirs(self.data_directory, exist_ok=True)
        self.user_data_file = path.join(self.data_directory, "userdata.ini")
        self.favorites_base_file = path.join(
            self.data_directory, "provider_favorites.json"
        )
        self.legacy_favorites_file = path.join(self.data_directory, "favorites.json")
        self.favorites_file = self.legacy_favorites_file
        self.provider_preferences_base_file = path.join(
            self.data_directory, "provider_preferences.json"
        )
        self.provider_preferences_file = ""
        self.cache_file = path.join(self.data_directory, "provider_catalog_cache.json")
        self.legacy_cache_file = path.join(self.data_directory, "all_cached_data.json")

        # The internal VLC UI runs in a second process. Commands are queued so
        # sending a large visible playlist can never block the main Qt event loop.
        self._embedded_player_process = None
        self._embedded_player_listener = None
        self._embedded_player_command_queue = None
        self._embedded_player_sender_thread = None

        # These defaults are replaced by persisted values during startup and are
        # sent to the isolated VLC process whenever it is started or reconfigured.
        self.internal_seek_step_seconds = DEFAULT_INTERNAL_SEEK_STEP_SECONDS
        self.internal_volume_step_percent = DEFAULT_INTERNAL_VOLUME_STEP_PERCENT
        self.internal_speed_step = DEFAULT_INTERNAL_SPEED_STEP
        self.internal_audio_language = ""
        self.internal_subtitle_language = ""
        # Default values for URL formats
        self.default_url_formats = dict(DEFAULT_URL_FORMATS)

        # Update the .ini file if needed to maintain backward compatibility.
        self.update_user_data_file()
        self._migrate_legacy_player_volume()

        self._init_resource_paths()

        self.setWindowIcon(QIcon(self.path_to_window_icon))

        self.default_font_size      = 10
        self.go_back_text           = " Go back"
        self.all_categories_text    = "All"
        self.fav_categories_text    = "Favorites"

        #navigation level indicates in what list level we are
        #LIVE and VOD have no navigation levels.
        #Series has 0: Series, 1: Seasons, 2: Episodes
        self.series_navigation_level = 0
        self.finished_fetching_series_info = False

        #Make history list index a list in order to achieve pass by reference
        self.streaming_search_history_list      = []
        self.streaming_search_history_list_idx  = [0]
        self.category_search_history_list       = []
        self.category_search_history_list_idx   = [0]
        self.max_search_history_size            = 30

        #Previous clicked item for preventing loading the same item multiple times
        self.prev_clicked_category_item = {
            'LIVE': 0,
            'Movies': 0,
            'Series': 0
        }
        self.prev_clicked_streaming_item        = 0
        self.prev_double_clicked_streaming_item = 0

        self.categories_per_stream_type = {}
        self.entries_per_stream_type = {
            'LIVE': [],
            'Movies': [],
            'Series': []
        }

        #Loaded data used for search algorithm
        self.currently_loaded_categories = {
            'LIVE': [],
            'Movies': [],
            'Series': []
        }
        self.category_item_counts = {
            'LIVE': {},
            'Movies': {},
            'Series': {},
        }
        self.currently_loaded_streams = {
            'LIVE': [],
            'Movies': [],
            'Series': [],
            'Seasons': [],
            'Episodes': []
        }

        # Cache the filtered and ordered entry lists used by category views. The
        # provider data is already cached, but preparing "All" again can still scan
        # and sort tens of thousands of Movies every time the user returns to it.
        self.category_view_cache = {
            'LIVE': {},
            'Movies': {},
            'Series': {}
        }
        # QListWidgetItem creation dominates category switching for very large
        # catalogs. Detached items can safely be kept and reattached when the same
        # view is opened again, making repeated switches effectively immediate.
        self.category_item_cache = {
            'LIVE': {},
            'Movies': {},
            'Series': {}
        }
        self.active_category_view_key = {
            'LIVE': None,
            'Movies': None,
            'Series': None
        }

        # Each content type can be hidden and omitted from provider requests.
        self.content_enabled = {
            'LIVE': True,
            'Movies': True,
            'Series': True
        }

        #Create search bar dicts
        self.category_search_bars   = {}
        self.streaming_search_bars  = {}
        self.category_search_widgets = {}
        self.streaming_search_widgets = {}

        # Preserve the provider order until the user explicitly selects sorting.
        self.sorting_enabled    = False
        self.sorting_order      = 0
        self.remember_category_sorting = False
        self.category_sort_fallback = 'disabled'
        self.category_sort_preferences = {
            'LIVE': {},
            'Movies': {},
            'Series': {}
        }
        self.category_list_sort_preferences = {}

        # Store exclusions rather than visible ids so categories introduced by the
        # provider after an application update remain visible without user action.
        self.hidden_category_ids = {
            'LIVE': set(),
            'Movies': set(),
            'Series': set()
        }

        #Credentials
        self.server            = ""
        self.username          = ""
        self.password          = ""
        self.live_url_format   = ""
        self.movie_url_format  = ""
        self.series_url_format = ""
        self.active_account_name = ""
        self.active_account_id = ""

        #Create threadpool for data/EPG/image fetching. Single-threaded to keep
        #fetching ordered and gentle on the IPTV server.
        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(1)

        #Stream-status probes run on a dedicated 2-thread pool so a slow LIVE channel
        #check can't block image or EPG fetching (issue #74).
        self.status_threadpool = QThreadPool()
        self.status_threadpool.setMaxThreadCount(2)

        #Whether the LIVE traffic-light stream-status check is enabled. The check
        #can be disabled in the Settings tab if a provider's streams are flaky and
        #the probe is producing false offline reports.
        self.stream_status_enabled = True

        # Account metadata has its own lightweight worker and timer. It must never
        # trigger a playlist, category, stream, or EPG reload.
        self.account_info_refresh_interval = (
            DEFAULT_ACCOUNT_INFO_REFRESH_INTERVAL
        )
        self.account_info_auto_refresh_enabled = True
        self.catalog_cache_enabled = True
        self.catalog_cache_max_age_hours = (
            DEFAULT_CATALOG_CACHE_MAX_AGE_HOURS
        )
        self.account_info_refresh_in_progress = False
        self.account_info_worker = None
        self.account_info_threadpool = QThreadPool()
        self.account_info_threadpool.setMaxThreadCount(1)
        self.account_info_timer = QTimer(self)
        self.account_info_timer.timeout.connect(self.refresh_account_info)

        self.init_icons()

        self.init_tab_widget()

        self.init_iptv_info()

        self.init_category_list_widgets()
        self.init_entry_list_widgets()
        self.init_info_boxes()

        self.init_search_bars()

        # self.initHomeTab()

        self.init_settings_tab()

        self.init_progress_bar()

        #Load default settings after GUI has been initialized
        self.load_data_at_startup()

        self.live_splitter = self._create_content_splitter(
            self.category_search_widgets["LIVE"],
            self.category_list_live,
            self.streaming_search_widgets["LIVE"],
            self.streaming_list_live,
            self.live_info_box,
            info_minimum_width=300,
        )
        self.live_tab_layout.addWidget(self.live_splitter)

        self.movies_splitter = self._create_content_splitter(
            self.category_search_widgets["Movies"],
            self.category_list_movies,
            self.streaming_search_widgets["Movies"],
            self.streaming_list_movies,
            self.movies_info_box,
            info_minimum_width=350,
        )
        self.movies_tab_layout.addWidget(self.movies_splitter)

        self.series_splitter = self._create_content_splitter(
            self.category_search_widgets["Series"],
            self.category_list_series,
            self.streaming_search_widgets["Series"],
            self.streaming_list_series,
            self.series_info_box,
            info_minimum_width=350,
        )
        self.series_tab_layout.addWidget(self.series_splitter)

        #Add iptv info text to info tab
        self.info_tab_layout.addWidget(self.iptv_info_text)

        #Create main widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        #Add everything to the main_layout
        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self.progress_bar)

        # Restore only after every splitter and tab exists. The saved geometry also
        # carries the maximized state, while the splitter states preserve the three
        # independently resized columns in each content tab.
        self.restore_window_layout()

        # Defer automatic login until the complete window exists and Qt has entered
        # its event loop. A fast cache load must not populate widgets while the main
        # window is still being constructed.
        QTimer.singleShot(0, self.load_startup_credentials)

    def set_active_account(self, name):
        """Store the active account label and expose it in the window title."""
        self._reset_provider_view_state()
        self.active_account_name = str(name or "").strip()
        self.active_account_id = (
            load_account_id(self.user_data_file, self.active_account_name) or ""
        )
        self.provider_preferences_file = (
            str(provider_preferences_file(
                self.provider_preferences_base_file, self.active_account_id
            ))
            if self.active_account_id else ""
        )
        title = f"IPTV Player {CURRENT_VERSION}"
        if self.active_account_name:
            title = f"{title} — {self.active_account_name}"
        self.setWindowTitle(title)
        self._load_hidden_categories()
        self._load_account_sort_preferences()

    def _reset_provider_view_state(self):
        """Discard every catalog and Qt item reference before changing accounts."""
        if not hasattr(self, 'category_list_widgets'):
            return
        for item_cache in self.category_item_cache.values():
            item_cache.clear()
        for stream_cache in self.category_view_cache.values():
            stream_cache.clear()
        for stream_type in self.active_category_view_key:
            self.active_category_view_key[stream_type] = None
            self.prev_clicked_category_item[stream_type] = 0
            self.currently_loaded_categories[stream_type] = []
            self.currently_loaded_streams[stream_type] = []
            self.category_item_counts[stream_type] = {}
        self.currently_loaded_streams['Seasons'] = []
        self.currently_loaded_streams['Episodes'] = []
        self.prev_clicked_streaming_item = 0
        self.prev_double_clicked_streaming_item = 0
        self.series_navigation_level = 0
        for search_bar in (
            *self.category_search_bars.values(),
            *self.streaming_search_bars.values(),
        ):
            search_bar.blockSignals(True)
            search_bar.clear()
            search_bar.blockSignals(False)
        for list_widget in (
            *self.category_list_widgets.values(),
            *self.streaming_list_widgets.values(),
        ):
            list_widget.clear()

    def _init_resource_paths(self):
        """Resolve all packaged image assets from one declarative mapping."""
        filenames = {
            'path_to_window_icon': 'TV_icon.ico',
            'path_to_no_img': 'no_image.jpg',
            'path_to_loading_img': 'loading-icon.png',
            'path_to_404_img': '404_not_found.png',
            'path_to_yt_img': 'yt_icon_rgb.png',
            'path_to_tmdb_img': 'primary_full-TMDB.svg',
            'path_to_home_icon': 'home_tab_icon.ico',
            'path_to_live_icon': 'tv_tab_icon.ico',
            'path_to_movies_icon': 'movies_tab_icon.ico',
            'path_to_series_icon': 'series_tab_icon.ico',
            'path_to_favorites_icon': 'favorite_tab_icon.ico',
            'path_to_fav_colour_icon': 'favorite_tab_icon_colour.ico',
            'path_to_online_status_icon': 'online_status.png',
            'path_to_offline_status_icon': 'offline_status.png',
            'path_to_maybe_status_icon': 'maybe_status.png',
            'path_to_unknown_status_icon': 'unknown_status.png',
            'path_to_info_icon': 'info_tab_icon.ico',
            'path_to_settings_icon': 'settings_tab_icon.ico',
            'path_to_search_icon': 'search_bar_icon.ico',
            'path_to_sorting_icon': 'sorting_icon.ico',
            'path_to_clear_btn_icon': 'clear_button_icon.ico',
            'path_to_go_back_icon': 'go_back_icon.ico',
            'path_to_account_icon': 'account_manager_icon.ico',
            'path_to_mediaplayer_icon': 'film_camera_icon.ico',
        }
        application_root = path.dirname(__file__)
        for attribute, filename in filenames.items():
            setattr(
                self,
                attribute,
                application_resource_path(
                    path.join('Images', filename), application_root
                ),
            )

    def _create_content_splitter(
        self,
        category_search,
        category_list,
        streaming_search,
        streaming_list,
        info_box,
        info_minimum_width,
    ):
        """Build the shared category, catalog, and information column layout."""
        splitter = QSplitter(Qt.Horizontal)

        category_container = QWidget()
        category_layout = QVBoxLayout(category_container)
        category_layout.setContentsMargins(0, 0, 0, 0)
        category_layout.addWidget(category_search)
        category_layout.addWidget(category_list)
        category_container.setMinimumWidth(150)

        streaming_container = QWidget()
        streaming_layout = QVBoxLayout(streaming_container)
        streaming_layout.setContentsMargins(0, 0, 0, 0)
        streaming_layout.addWidget(streaming_search)
        streaming_layout.addWidget(streaming_list)
        streaming_container.setMinimumWidth(150)

        info_container = QWidget()
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.addWidget(info_box)
        info_container.setMinimumWidth(info_minimum_width)

        for column in (category_container, streaming_container, info_container):
            splitter.addWidget(column)

        splitter.setSizes([200, 200, 300])
        for column_index in range(3):
            splitter.setCollapsible(column_index, False)

        return splitter

    def _encoded_widget_state(self, state):
        """Encode Qt's binary geometry/state payload for safe INI storage."""
        return bytes(state.toBase64()).decode('ascii')

    def _decoded_widget_state(self, encoded_state):
        """Decode a persisted Qt state, returning an empty payload if invalid."""
        try:
            return QByteArray.fromBase64(encoded_state.encode('ascii'))
        except (AttributeError, UnicodeEncodeError):
            return QByteArray()

    def restore_window_layout(self):
        """Restore window geometry, active tab, and per-tab column widths."""
        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError) as e:
            print(f"Could not restore window layout: {e}")
            return

        if 'Window' not in config:
            return

        window_config = config['Window']
        encoded_geometry = window_config.get('geometry', '')
        if encoded_geometry:
            self.restoreGeometry(self._decoded_widget_state(encoded_geometry))
            self._ensure_window_is_visible()

        splitters = {
            'live_splitter': self.live_splitter,
            'movies_splitter': self.movies_splitter,
            'series_splitter': self.series_splitter
        }
        for setting_name, splitter in splitters.items():
            encoded_state = window_config.get(setting_name, '')
            if encoded_state:
                splitter.restoreState(self._decoded_widget_state(encoded_state))

        active_tab = window_config.get('active_tab', '')
        for tab_index in range(self.tab_widget.count()):
            if self.tab_widget.tabText(tab_index) == active_tab:
                self.tab_widget.setCurrentIndex(tab_index)
                break

    def _ensure_window_is_visible(self):
        """Move a restored window back on-screen after monitor layout changes."""
        window_geometry = self.frameGeometry()
        if any(
            window_geometry.intersects(screen.availableGeometry())
            for screen in QApplication.screens()
        ):
            return

        primary_screen = QApplication.primaryScreen()
        if primary_screen is None:
            return

        available = primary_screen.availableGeometry()
        self.setWindowState(Qt.WindowNoState)
        self.resize(min(1300, available.width()), min(900, available.height()))
        centered_geometry = self.frameGeometry()
        centered_geometry.moveCenter(available.center())
        self.move(centered_geometry.topLeft())

    def save_window_layout(self):
        """Persist durable UI layout preferences in userdata.ini."""
        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError):
            config = configparser.ConfigParser()

        config['Window'] = {
            'geometry': self._encoded_widget_state(self.saveGeometry()),
            'live_splitter': self._encoded_widget_state(self.live_splitter.saveState()),
            'movies_splitter': self._encoded_widget_state(self.movies_splitter.saveState()),
            'series_splitter': self._encoded_widget_state(self.series_splitter.saveState()),
            'active_tab': self.tab_widget.tabText(self.tab_widget.currentIndex())
        }

        try:
            write_config_file(self.user_data_file, config)
        except OSError as e:
            print(f"Could not save window layout: {e}")

    def closeEvent(self, event):
        self.save_window_layout()
        self._stop_embedded_player_process()
        super().closeEvent(event)

    def update_user_data_file(self):
        """Apply ordered migrations to the persisted user configuration."""
        migrate_user_data_file(
            self.user_data_file,
            self.default_url_formats,
            CURRENT_CONFIG_SCHEMA_VERSION,
        )

    def _migrate_legacy_player_volume(self):
        """Move the former standalone volume preference into userdata.ini."""
        migrate_legacy_player_volume(self.user_data_file, self.data_directory)

    def init_icons(self):
        #Set tab icon size to 24x24
        self.tab_icon_size = QSize(24, 24)

        #Create tab icons
        self.home_icon              = QIcon(self.path_to_home_icon)
        self.live_icon              = QIcon(self.path_to_live_icon)
        self.movies_icon            = QIcon(self.path_to_movies_icon)
        self.series_icon            = QIcon(self.path_to_series_icon)
        self.favorites_icon         = QIcon(self.path_to_favorites_icon)
        self.favorites_icon_colour  = QIcon(self.path_to_fav_colour_icon)
        self.info_icon              = QIcon(self.path_to_info_icon)
        self.settings_icon          = QIcon(self.path_to_settings_icon)

        #Create settings buttons icons
        self.account_manager_icon   = QIcon(self.path_to_account_icon)
        self.mediaplayer_icon       = QIcon(self.path_to_mediaplayer_icon)

        #Create misc icons
        self.search_icon    = QIcon(self.path_to_search_icon)
        self.sorting_icon   = QIcon(self.path_to_sorting_icon)
        self.clear_btn_icon = QIcon(self.path_to_clear_btn_icon)
        self.go_back_icon   = QIcon(self.path_to_go_back_icon)

    def _tinted_icon(self, source_icon, color):
        """Create a monochrome copy of an icon that contrasts with the theme."""
        source = source_icon.pixmap(24, 24)
        tinted = QPixmap(source.size())
        tinted.fill(Qt.transparent)
        painter = QPainter(tinted)
        painter.drawPixmap(0, 0, source)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), color)
        painter.end()
        return QIcon(tinted)

    def _category_icon(self, color):
        """Draw a transparent category grid using the current theme contrast."""
        # Some native Qt list icons have an opaque background. Tinting such an
        # icon colors its complete rectangle, so draw this simple symbol directly.
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        for x in (4, 13):
            for y in (4, 13):
                painter.fillRect(x, y, 7, 7, color)
        painter.end()
        return QIcon(pixmap)

    def _refresh_theme_icons(self, dark):
        """Refresh monochrome icons after the application palette changes."""
        color = QColor("#f2f2f2" if dark else "#202020")
        themed_paths = {
            'home_icon': self.path_to_home_icon,
            'live_icon': self.path_to_live_icon,
            'movies_icon': self.path_to_movies_icon,
            'series_icon': self.path_to_series_icon,
            'favorites_icon': self.path_to_favorites_icon,
            'info_icon': self.path_to_info_icon,
            'settings_icon': self.path_to_settings_icon,
            'account_manager_icon': self.path_to_account_icon,
            'mediaplayer_icon': self.path_to_mediaplayer_icon,
            'search_icon': self.path_to_search_icon,
            'sorting_icon': self.path_to_sorting_icon,
            'clear_btn_icon': self.path_to_clear_btn_icon,
            'go_back_icon': self.path_to_go_back_icon,
        }
        for attribute, icon_path in themed_paths.items():
            setattr(self, attribute, self._tinted_icon(QIcon(icon_path), color))

        if hasattr(self, 'tab_widget'):
            tab_icons = {
                'LIVE': self.live_icon,
                'Movies': self.movies_icon,
                'Series': self.series_icon,
                'Info': self.info_icon,
                'Settings': self.settings_icon,
            }
            for index in range(self.tab_widget.count()):
                icon = tab_icons.get(self.tab_widget.tabText(index))
                if icon is not None:
                    self.tab_widget.setTabIcon(index, icon)

        for search_bar in (
            list(getattr(self, 'category_search_bars', {}).values())
            + list(getattr(self, 'streaming_search_bars', {}).values())
        ):
            if hasattr(search_bar, 'search_action'):
                search_bar.search_action.setIcon(self.search_icon)
            if hasattr(search_bar, 'sort_button'):
                search_bar.sort_button.setIcon(self.sorting_icon)
            if hasattr(search_bar, 'clear_button'):
                search_bar.clear_button.setIcon(self.clear_btn_icon)
            if hasattr(search_bar, 'category_visibility_button'):
                search_bar.category_visibility_button.setIcon(
                    self._category_icon(color)
                )

        if hasattr(self, 'address_book_button'):
            self.address_book_button.setIcon(self.account_manager_icon)
        if hasattr(self, 'choose_player_button'):
            self.choose_player_button.setIcon(self.mediaplayer_icon)

    def status_pixmap(self, icon_path, width=24):
        """Load a colored status circle without its legacy opaque white corners."""
        pixmap = QPixmap(icon_path)
        pixmap.setMask(pixmap.createMaskFromColor(QColor(Qt.white), Qt.MaskInColor))
        return pixmap.scaledToWidth(width, Qt.SmoothTransformation)

    def init_tab_widget(self):
        #Create tab widget
        self.tab_widget = QTabWidget()

        #Create tabs
        home_tab          = QWidget()
        self.live_tab     = QWidget()
        self.movies_tab   = QWidget()
        self.series_tab   = QWidget()
        favorites_tab     = QWidget()
        self.info_tab     = QWidget()
        settings_tab      = QWidget()

        #Create layouts for tabs
        self.home_tab_layout        = QVBoxLayout(home_tab)
        self.live_tab_layout        = QVBoxLayout(self.live_tab)
        self.movies_tab_layout      = QVBoxLayout(self.movies_tab)
        self.series_tab_layout      = QVBoxLayout(self.series_tab)
        self.favorites_tab_layout   = QGridLayout(favorites_tab)
        self.info_tab_layout        = QVBoxLayout(self.info_tab)
        self.settings_layout        = QGridLayout(settings_tab)

        #Add created tabs to tab widget with their names
        # self.tab_widget.addTab(home_tab,        self.home_icon,         "Home")
        self.tab_widget.addTab(self.live_tab,   self.live_icon,         "LIVE")
        self.tab_widget.addTab(self.movies_tab, self.movies_icon,       "Movies")
        self.tab_widget.addTab(self.series_tab, self.series_icon,       "Series")
        # self.tab_widget.addTab(favorites_tab,   self.favorites_icon,    "Favorites")
        self.tab_widget.addTab(self.info_tab,   self.info_icon,         "Info")
        self.tab_widget.addTab(settings_tab,    self.settings_icon,     "Settings")
        self.tab_widget.currentChanged.connect(self._on_current_tab_changed)

    def init_search_bars(self):
        #Initialize search bars for category lists
        self.category_search_bars["LIVE"] = QLineEdit()
        self.category_search_bars["LIVE"].setPlaceholderText("Search Live TV Categories...")
        self.category_search_widgets["LIVE"] = self.configure_search_bar(self.category_search_bars["LIVE"], 'category', 'LIVE', self.category_list_widgets, self.category_search_history_list, self.category_search_history_list_idx)

        self.category_search_bars["Movies"] = QLineEdit()
        self.category_search_bars["Movies"].setPlaceholderText("Search Movies Categories...")
        self.category_search_widgets["Movies"] = self.configure_search_bar(self.category_search_bars["Movies"], 'category', 'Movies', self.category_list_widgets, self.category_search_history_list, self.category_search_history_list_idx)

        self.category_search_bars["Series"] = QLineEdit()
        self.category_search_bars["Series"].setPlaceholderText("Search Series Categories...")
        self.category_search_widgets["Series"] = self.configure_search_bar(self.category_search_bars["Series"], 'category', 'Series', self.category_list_widgets, self.category_search_history_list, self.category_search_history_list_idx)

        #Initialize search bars for streaming content lists
        self.streaming_search_bars["LIVE"] = QLineEdit()
        self.streaming_search_bars["LIVE"].setPlaceholderText("Search Live TV Channels...")
        self.streaming_search_widgets["LIVE"] = self.configure_search_bar(self.streaming_search_bars["LIVE"], 'streaming', 'LIVE', self.streaming_list_widgets, self.streaming_search_history_list, self.streaming_search_history_list_idx)

        self.streaming_search_bars["Movies"] = QLineEdit()
        self.streaming_search_bars["Movies"].setPlaceholderText("Search Movies...")
        self.streaming_search_widgets["Movies"] = self.configure_search_bar(self.streaming_search_bars["Movies"], 'streaming', 'Movies', self.streaming_list_widgets, self.streaming_search_history_list, self.streaming_search_history_list_idx)

        self.streaming_search_bars["Series"] = QLineEdit()
        self.streaming_search_bars["Series"].setPlaceholderText("Search Series...")
        self.streaming_search_widgets["Series"] = self.configure_search_bar(self.streaming_search_bars["Series"], 'streaming', 'Series', self.streaming_list_widgets, self.streaming_search_history_list, self.streaming_search_history_list_idx)

    def configure_search_bar(self, search_bar, list_content_type, stream_type, list_widgets, search_history_list, search_history_list_idx):
        #Create sorting actions
        sort_a_z        = QAction("A-Z", self)
        sort_z_a        = QAction("Z-A", self)
        sort_disabled   = QAction("Sorting disabled", self)
        for sorting_action in (sort_a_z, sort_z_a, sort_disabled):
            sorting_action.setCheckable(True)

        #Add search icon
        search_bar.search_action = search_bar.addAction(
            self.search_icon, QLineEdit.LeadingPosition
        )

        # Use a real tool button for the menu. A QAction embedded in QLineEdit may
        # consume the first click only to focus the editor on Windows, which makes
        # the user click another column before the sorting menu becomes available.
        sort_button = QToolButton()
        sort_button.setIcon(self.sorting_icon)
        sort_button.setToolTip("Set sorting order")
        sort_button.setPopupMode(QToolButton.InstantPopup)

        #Create sorting action menu
        sorting_menu = QMenu(sort_button)
        sorting_menu.setTitle("Set sorting order:")
        sorting_group = QActionGroup(sorting_menu)
        sorting_group.setExclusive(True)
        sorting_group.addAction(sort_a_z)
        sorting_group.addAction(sort_z_a)
        sorting_group.addAction(sort_disabled)
        sorting_menu.addActions([sort_a_z, sort_z_a, sort_disabled])
        sort_button.setMenu(sorting_menu)

        #Connect functions to sorting actions
        sort_a_z.triggered.connect(
            lambda: self.apply_sorting_choice(
                search_bar, list_content_type, stream_type, list_widgets, True, 0
            )
        )
        sort_z_a.triggered.connect(
            lambda: self.apply_sorting_choice(
                search_bar, list_content_type, stream_type, list_widgets, True, 1
            )
        )
        sort_disabled.triggered.connect(
            lambda: self.apply_sorting_choice(
                search_bar, list_content_type, stream_type, list_widgets, False, 0
            )
        )

        # Keep clearing independent from editor focus for the same reason.
        clear_button = QToolButton()
        clear_button.setIcon(self.clear_btn_icon)
        clear_button.setToolTip("Clear search")

        #Connect function to clear search action
        clear_button.clicked.connect(lambda: self.clear_search(search_bar, list_content_type, stream_type, list_widgets, search_history_list_idx))

        # Store references on the editor for tests and future UI customization.
        search_bar.sort_button = sort_button
        search_bar.clear_button = clear_button
        search_bar.sorting_menu = sorting_menu
        search_bar.sorting_group = sorting_group
        search_bar.sort_actions = {
            'a_z': sort_a_z,
            'z_a': sort_z_a,
            'disabled': sort_disabled
        }
        search_bar.current_sorting = (self.sorting_enabled, self.sorting_order)
        sorting_menu.aboutToShow.connect(
            lambda: self.update_sorting_menu(
                search_bar, list_content_type, stream_type
            )
        )

        container = QWidget()
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(2)
        container_layout.addWidget(search_bar)
        # Keep the clear action beside the field it affects. It only empties the
        # search text and never changes sorting or category visibility settings.
        container_layout.addWidget(clear_button)
        if list_content_type == 'category':
            category_visibility_button = QToolButton()
            category_visibility_button.setText("Categories")
            category_visibility_button.setIcon(
                self._category_icon(
                    QColor("#f2f2f2" if application_palette_is_dark(QtWidgets.qApp)
                           else "#202020")
                )
            )
            category_visibility_button.setToolButtonStyle(
                Qt.ToolButtonTextBesideIcon
            )
            category_visibility_button.setToolTip(
                f"Choose which {stream_type} categories are displayed"
            )
            category_visibility_button.clicked.connect(
                lambda: self.open_category_visibility_dialog(stream_type)
            )
            search_bar.category_visibility_button = category_visibility_button
            container_layout.addWidget(category_visibility_button)
        container_layout.addWidget(sort_button)

        # Connect the search field to history navigation and filtering.
        search_bar.keyPressEvent = lambda event: self.search_bar_key_pressed(
            event,
            search_bar,
            list_content_type,
            stream_type,
            list_widgets,
            search_history_list,
            search_history_list_idx,
        )

        return container

    def open_category_visibility_dialog(self, stream_type):
        """Open the visibility editor and apply accepted changes immediately."""
        categories = self.categories_per_stream_type.get(stream_type, [])
        if not categories:
            QMessageBox.information(
                self,
                "Categories unavailable",
                f"No {stream_type} categories have been loaded yet."
            )
            return

        dialog = CategoryVisibilityDialog(
            self,
            stream_type,
            categories,
            self.hidden_category_ids[stream_type]
        )
        self._prepare_dialog_theme(dialog)
        if dialog.exec() != QDialog.Accepted:
            return

        self.hidden_category_ids[stream_type] = dialog.hidden_category_ids()
        self._save_hidden_categories()

        # All is derived from visible categories, so every cached representation for
        # this content type becomes stale as soon as the exclusions change.
        self.category_view_cache[stream_type].clear()
        self.category_item_cache[stream_type].clear()
        self.active_category_view_key[stream_type] = None
        self._refresh_visible_categories(stream_type)

    def _visible_categories(self, stream_type):
        """Return provider categories that are not explicitly hidden by the user."""
        hidden_ids = self.hidden_category_ids[stream_type]
        return [
            category
            for category in self.categories_per_stream_type.get(stream_type, [])
            if str(category.get('category_id', '')) not in hidden_ids
        ]

    def _entries_in_visible_categories(self, stream_type):
        """Return entries included in the synthetic All view after exclusions."""
        visible_category_ids = {
            str(category.get('category_id'))
            for category in self._visible_categories(stream_type)
            if category.get('category_id') is not None
        }
        return [
            entry
            for entry in self.entries_per_stream_type.get(stream_type, [])
            if entry.get('category_id') is not None
            and str(entry.get('category_id')) in visible_category_ids
        ]

    def _category_display_text(self, stream_type, category_name, category_id=None):
        """Return a category label with its locally known catalog size."""
        if category_name == self.all_categories_text:
            count = len(self._entries_in_visible_categories(stream_type))
        elif category_name == self.fav_categories_text:
            count = len(self._favorites_in_user_order(stream_type))
        else:
            count = self.category_item_counts[stream_type].get(str(category_id), 0)
        return f"{category_name} ({count})"

    def _new_category_item(self, stream_type, category_data):
        """Create a category row while keeping its undecorated name in item data."""
        category_name = category_data.get('category_name', '')
        category_id = category_data.get('category_id')
        item = QListWidgetItem(
            self._category_display_text(stream_type, category_name, category_id)
        )
        item.setData(Qt.UserRole, category_data)
        return item

    def _refresh_category_count_labels(self, stream_type):
        """Refresh visible category counts without rebuilding the list."""
        list_widget = self.category_list_widgets[stream_type]
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            category_data = item.data(Qt.UserRole)
            if not isinstance(category_data, dict):
                continue
            item.setText(self._category_display_text(
                stream_type,
                category_data.get('category_name', ''),
                category_data.get('category_id'),
            ))

    def _refresh_visible_categories(self, stream_type):
        """Rebuild one category column and preserve its selection when possible."""
        previous_name, previous_id = self._selected_category(stream_type)
        active_category_was_hidden = (
            previous_name not in (
                self.all_categories_text, self.fav_categories_text
            )
            and str(previous_id) in self.hidden_category_ids[stream_type]
        )
        self.currently_loaded_categories[stream_type] = self._visible_categories(
            stream_type
        )
        if active_category_was_hidden:
            # All must be available as the safe replacement selection.
            self.category_search_bars[stream_type].clear()
        search_text = self.category_search_bars[stream_type].text()
        self.search_in_list('category', stream_type, search_text)

        category_list = self.category_list_widgets[stream_type]
        selected_row = -1
        for row in range(category_list.count()):
            item = category_list.item(row)
            item_data = item.data(Qt.UserRole) or {}
            if previous_name in (self.all_categories_text, self.fav_categories_text):
                matches_previous = item_data.get('category_name') == previous_name
            else:
                matches_previous = (
                    str(item_data.get('category_id', '')) == str(previous_id)
                )
            if matches_previous:
                selected_row = row
                break

        if selected_row >= 0:
            category_list.setCurrentRow(selected_row)
            category_list.itemClicked.emit(category_list.item(selected_row))
            return

        # If the active category was just hidden, switch to All so the stream list
        # cannot remain filled with content from a category no longer displayed.
        if not search_text:
            all_items = [
                category_list.item(row)
                for row in range(category_list.count())
                if (category_list.item(row).data(Qt.UserRole) or {}).get(
                    'category_name'
                ) == self.all_categories_text
            ]
            if all_items:
                category_list.setCurrentItem(all_items[0])
                category_list.itemClicked.emit(all_items[0])

    def _load_hidden_categories(self):
        """Load category exclusions belonging to the active IPTV account."""
        self.hidden_category_ids = {
            'LIVE': set(), 'Movies': set(), 'Series': set()
        }
        if not self.provider_preferences_file:
            return
        saved = load_provider_preferences(
            self.provider_preferences_file
        ).get('hidden_categories', {})
        if isinstance(saved, dict):
            for stream_type in self.hidden_category_ids:
                hidden_ids = saved.get(stream_type, [])
                if isinstance(hidden_ids, list):
                    self.hidden_category_ids[stream_type] = {
                        str(category_id) for category_id in hidden_ids
                    }

    def _save_hidden_categories(self):
        """Persist category exclusions for the active IPTV account."""
        if not self.provider_preferences_file:
            return
        current = load_provider_preferences(self.provider_preferences_file)
        hidden_categories = {
            stream_type: sorted(hidden_ids)
            for stream_type, hidden_ids in self.hidden_category_ids.items()
        }
        try:
            save_provider_preferences(
                self.provider_preferences_file,
                hidden_categories,
                current.get('category_sorting', {}),
            )
        except OSError as e:
            print(f"Could not save hidden categories: {e}")

    def update_sorting_menu(self, search_bar, list_content_type, stream_type):
        """Check the action that matches the order of the list being displayed."""
        remembers_current_category = (
            self.remember_category_sorting
            and list_content_type == 'streaming'
            and (stream_type != 'Series' or self.series_navigation_level == 0)
        )
        if remembers_current_category:
            category_name, category_id = self._selected_category(stream_type)
            sorting_enabled, sort_order = self._sorting_for_category(
                stream_type, category_name, category_id
            )
        else:
            sorting_enabled, sort_order = getattr(
                search_bar, 'current_sorting',
                (self.sorting_enabled, self.sorting_order)
            )

        preference = self._sorting_preference_value(
            sorting_enabled, sort_order
        )
        for action_name, action in search_bar.sort_actions.items():
            action.setChecked(action_name == preference)

    def apply_sorting_choice(
        self, search_bar, list_content_type, stream_type, list_widgets,
        sorting_enabled, sort_order
    ):
        """Apply a menu choice and persist it for the selected category if enabled."""
        if self.remember_category_sorting and list_content_type == 'category':
            self.category_list_sort_preferences[stream_type] = (
                self._sorting_preference_value(sorting_enabled, sort_order)
            )
            self._save_category_sort_preferences()

        if (
            self.remember_category_sorting
            and list_content_type == 'streaming'
            and (stream_type != 'Series' or self.series_navigation_level == 0)
        ):
            category_name, category_id = self._selected_category(stream_type)
            preference_key = self._category_sort_preference_key(
                category_name, category_id
            )
            preference_value = self._sorting_preference_value(
                sorting_enabled, sort_order
            )
            self.category_sort_preferences[stream_type][preference_key] = (
                preference_value
            )
            self._save_category_sort_preferences()

            # Prepared dictionaries and reusable Qt items contain a specific order.
            # Discard this content type's caches so the new preference is used when
            # the user leaves and later returns to the category.
            self.category_view_cache[stream_type].clear()
            self.category_item_cache[stream_type].clear()
            self.active_category_view_key[stream_type] = None

            prepared_entries = self._entries_for_category_view(
                stream_type, category_name, category_id
            )
            self.currently_loaded_streams[stream_type] = list(prepared_entries)

        self.sort_list(
            search_bar, list_content_type, stream_type, list_widgets,
            sorting_enabled, sort_order
        )

        if self.remember_category_sorting and list_content_type == 'streaming':
            category_name, category_id = self._selected_category(stream_type)
            self.active_category_view_key[stream_type] = self._category_view_key(
                stream_type, category_name, category_id
            )

    def clear_search(self, search_bar, list_content_type, stream_type, list_widgets, history_list_idx):
        #Clear search bar
        search_bar.clear()

        #Reset list history index to -1
        history_list_idx[0] = -1

        #Search for nothing so list will be reset
        self.search_in_list(list_content_type, stream_type, "")

    def sort_list(self, search_bar, list_content_type, stream_type, list_widgets, sorting_enabled, sort_order):
        # Keep the menu check mark synchronized even when a global setting invokes
        # sorting directly instead of going through applySortingChoice().
        search_bar.current_sorting = (sorting_enabled, sort_order)
        self.set_progress_bar(0, f"Sorting {stream_type} {list_content_type}")

        #Get list
        list_widget = list_widgets[stream_type]

        # Top-level stream catalogs can contain tens of thousands of rows. Qt's
        # native QListWidget sort runs entirely in the GUI thread and can freeze the
        # whole application for several seconds. Sort the lightweight dictionaries
        # first, then rebuild the widget in cooperative chunks.
        is_top_level_stream_view = (
            list_content_type == 'streaming'
            and (stream_type != 'Series' or self.series_navigation_level == 0)
        )
        if is_top_level_stream_view:
            ordered_entries = ordered_catalog_entries(
                self.currently_loaded_streams[stream_type],
                sorting_enabled,
                descending=(sort_order == 1),
            )

            self.currently_loaded_streams[stream_type] = ordered_entries
            self._replace_streaming_list_items(stream_type, ordered_entries)
            self.set_progress_bar(
                100, f"Finished sorting {stream_type} {list_content_type}"
            )
            return

        # The Seasons view (Series tab, navigation level 1) needs numeric ordering, not Qt's
        # default text sort — otherwise "Season 10" comes before "Season 2". Issue #18.
        is_seasons_view = (
            list_content_type == 'streaming'
            and stream_type == 'Series'
            and getattr(self, 'series_navigation_level', 0) == 1
        )
        if is_seasons_view and sorting_enabled:
            seasons_dict = self.currently_loaded_streams.get('Seasons', {}) or {}

            keys = ordered_season_keys(
                seasons_dict.keys(), descending=(sort_order == 1)
            )

            list_widget.setSortingEnabled(False)
            list_widget.clear()
            go_back_item = QListWidgetItem(self.go_back_text)
            go_back_item.setIcon(self.go_back_icon)
            list_widget.addItem(go_back_item)
            for season in keys:
                item = QListWidgetItem(f"Season {season}")
                item.setData(Qt.UserRole, seasons_dict[season])
                list_widget.addItem(item)
            self.animate_progress(0, 100, f"Finished sorting {stream_type} {list_content_type}")
            return

        # Keep automatic sorting disabled while changing the list. Enabling it here
        # already performs a sort, and the former explicit sortItems() call performed
        # the same expensive work a second time for large Movie catalogs.
        list_widget.setSortingEnabled(False)
        list_widget.setUpdatesEnabled(False)

        try:
            #Remove 'All' and 'Favorites' category items
            if list_content_type == 'category':
                matches = []
                for row in range(list_widget.count()):
                    item = list_widget.item(row)
                    item_data = item.data(Qt.UserRole) or {}
                    if item_data.get('category_name') in (
                        self.all_categories_text, self.fav_categories_text
                    ):
                        matches.append(item)

                for item in matches:
                    idx = list_widget.row(item)
                    list_widget.takeItem(idx)

            if sorting_enabled:
                # Perform exactly one native Qt sort after all items are present.
                list_widget.sortItems(sort_order)

            else:
                #When sorting is disabled, reload list manually
                if list_content_type == 'category':
                    self.category_list_widgets[stream_type].clear()

                    for entry in self.currently_loaded_categories[stream_type]:
                        item = self._new_category_item(stream_type, entry)
                        self.category_list_widgets[stream_type].addItem(item)

                elif list_content_type == 'streaming':
                    self.streaming_list_widgets[stream_type].clear()

                    for entry in self.currently_loaded_streams[stream_type]:
                        item = QListWidgetItem(entry['name'])
                        item.setData(Qt.UserRole, entry)

                        self.streaming_list_widgets[stream_type].addItem(item)

            if list_content_type == 'category':
                #Add 'All' and 'Favorites' categories to top
                itemAll = self._new_category_item(
                    stream_type, {'category_name': self.all_categories_text}
                )
                self.category_list_widgets[stream_type].insertItem(0, itemAll)

                itemFav = self._new_category_item(
                    stream_type, {'category_name': self.fav_categories_text}
                )
                self.category_list_widgets[stream_type].insertItem(1, itemFav)
        finally:
            list_widget.setUpdatesEnabled(True)
            list_widget.viewport().update()

        self.animate_progress(0, 100, f"Finished sorting {stream_type} {list_content_type}")

    def _replace_streaming_list_items(self, stream_type, entries):
        """Replace a large stream list while periodically yielding to Qt."""
        list_widget = self.streaming_list_widgets[stream_type]
        category_widget = self.category_list_widgets[stream_type]
        chunk_size = 1000

        list_widget.setSortingEnabled(False)
        list_widget.setUpdatesEnabled(False)
        category_widget.setEnabled(False)
        try:
            list_widget.clear()
            total_entries = len(entries)
            for start in range(0, total_entries, chunk_size):
                chunk = entries[start:start + chunk_size]
                first_row = list_widget.count()
                list_widget.addItems([
                    entry.get('name', '') for entry in chunk
                ])
                for offset, entry in enumerate(chunk):
                    list_widget.item(first_row + offset).setData(Qt.UserRole, entry)

                # Process pending paint and input events between chunks so switching
                # tabs and using the rest of the application remains responsive.
                self.set_progress_bar(
                    int(min(99, ((start + len(chunk)) * 100) / total_entries)),
                    f"Loading {stream_type} streams: "
                    f"{start + len(chunk)} of {total_entries}"
                )

            if not entries:
                list_widget.addItem("No items in list...")
        finally:
            category_widget.setEnabled(True)
            list_widget.setUpdatesEnabled(True)
            list_widget.viewport().update()

    def init_iptv_info(self):
        info_controls = QHBoxLayout()
        self.refresh_account_info_button = QPushButton("Refresh")
        self.refresh_account_info_button.setIcon(
            self.style().standardIcon(QtWidgets.QStyle.SP_BrowserReload)
        )
        self.refresh_account_info_button.setToolTip(
            "Refresh account status and active connections only"
        )
        self.refresh_account_info_button.clicked.connect(self.refresh_account_info)
        self.account_info_last_refresh_label = QLabel("Not refreshed yet")
        info_controls.addWidget(self.refresh_account_info_button)
        info_controls.addWidget(self.account_info_last_refresh_label)
        info_controls.addStretch()
        self.info_tab_layout.addLayout(info_controls)

        self.iptv_info_text = QTextEdit()
        self.iptv_info_text.setReadOnly(True)

        default_font = QFont()
        default_font.setPointSize(self.default_font_size)

        self.iptv_info_text.setFont(default_font)

    def init_category_list_widgets(self):
        #Create lists for categories
        self.category_list_live     = KeyboardNavigableListWidget()
        self.category_list_movies   = KeyboardNavigableListWidget()
        self.category_list_series   = KeyboardNavigableListWidget()

        #Enable sorting
        # self.category_list_live.setSortingEnabled(True)
        # self.category_list_movies.setSortingEnabled(True)
        # self.category_list_series.setSortingEnabled(True)

        #Connect functions to category list events
        self.category_list_live.itemClicked.connect(self.category_item_clicked)
        self.category_list_movies.itemClicked.connect(self.category_item_clicked)
        self.category_list_series.itemClicked.connect(self.category_item_clicked)
        self.category_list_live.keyboardActivated.connect(self.category_item_clicked)
        self.category_list_movies.keyboardActivated.connect(self.category_item_clicked)
        self.category_list_series.keyboardActivated.connect(self.category_item_clicked)
        self.category_list_live.keyboardSelected.connect(self.category_item_clicked)
        self.category_list_movies.keyboardSelected.connect(self.category_item_clicked)
        self.category_list_series.keyboardSelected.connect(self.category_item_clicked)

        #Put category lists in list
        self.category_list_widgets = {
            'LIVE': self.category_list_live,
            'Movies': self.category_list_movies,
            'Series': self.category_list_series,
        }

        #Configure visuals of the lists
        standard_icon_size = QSize(24, 24)
        for list_widget in [self.category_list_live, self.category_list_movies, self.category_list_series]:
            list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            list_widget.setIconSize(standard_icon_size)
            list_widget.setStyleSheet("""
                QListWidget {
                    background-color: palette(base);
                    color: palette(text);
                }
                QListWidget::item {
                    padding-top: 5px;
                    padding-bottom: 5px;
                }
                QListWidget::item:selected {
                    background-color: palette(highlight);
                    color: palette(highlighted-text);
                }
            """)

    def init_entry_list_widgets(self):
        #Create lists for channels
        self.streaming_list_live      = KeyboardNavigableListWidget()
        self.streaming_list_movies    = KeyboardNavigableListWidget()
        self.streaming_list_series    = KeyboardNavigableListWidget()

        #Enable sorting
        # self.streaming_list_live.setSortingEnabled(True)
        # self.streaming_list_movies.setSortingEnabled(True)
        # self.streaming_list_series.setSortingEnabled(True)

        #Set that lists load items in batches to prevent screen freezing
        self.streaming_list_live.setLayoutMode(QListView.Batched)
        self.streaming_list_movies.setLayoutMode(QListView.Batched)
        self.streaming_list_series.setLayoutMode(QListView.Batched)

        self.streaming_list_live.setBatchSize(2000)
        self.streaming_list_movies.setBatchSize(2000)
        self.streaming_list_series.setBatchSize(2000)

        #Connect functions to entry list events
        self.streaming_list_live.itemDoubleClicked.connect(self.streaming_item_double_clicked)
        self.streaming_list_movies.itemDoubleClicked.connect(self.streaming_item_double_clicked)
        self.streaming_list_series.itemDoubleClicked.connect(self.streaming_item_double_clicked)

        self.streaming_list_live.itemClicked.connect(self.streaming_item_clicked)
        self.streaming_list_movies.itemClicked.connect(self.streaming_item_clicked)
        self.streaming_list_series.itemClicked.connect(self.streaming_item_clicked)

        self.streaming_list_live.keyboardActivated.connect(self.streaming_item_keyboard_activated)
        self.streaming_list_movies.keyboardActivated.connect(self.streaming_item_keyboard_activated)
        self.streaming_list_series.keyboardActivated.connect(self.streaming_item_keyboard_activated)
        self.streaming_list_live.keyboardSelected.connect(self.streaming_item_clicked)
        self.streaming_list_movies.keyboardSelected.connect(self.streaming_item_clicked)
        self.streaming_list_series.keyboardSelected.connect(self.streaming_item_clicked)

        #Put entry lists in list
        self.streaming_list_widgets = {
            'LIVE': self.streaming_list_live,
            'Movies': self.streaming_list_movies,
            'Series': self.streaming_list_series,
        }

        # Tab and Backtab switch directly between the two catalog columns.
        for stream_type in ('LIVE', 'Movies', 'Series'):
            category_list = self.category_list_widgets[stream_type]
            streaming_list = self.streaming_list_widgets[stream_type]
            category_list.set_tab_target(streaming_list)
            streaming_list.set_tab_target(category_list)

        #Configure visuals of the lists
        standard_icon_size = QSize(24, 24)
        for list_widget in [self.streaming_list_live, self.streaming_list_movies, self.streaming_list_series]:
            list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            list_widget.setIconSize(standard_icon_size)
            list_widget.setStyleSheet("""
                QListWidget {
                    background-color: palette(base);
                    color: palette(text);
                }
                QListWidget::item {
                    padding-top: 5px;
                    padding-bottom: 5px;
                }
                QListWidget::item:selected {
                    background-color: palette(highlight);
                    color: palette(highlighted-text);
                }
            """)

    def init_info_boxes(self):
        #Create Movies and Series info box
        self.live_info_box   = LiveInfoBox(self)
        self.movies_info_box = MovieInfoBox(self)
        self.series_info_box = SeriesInfoBox(self)

    def init_home_tab(self):
        #Create lists to show previously watched content
        self.live_history_list      = QListWidget()
        self.movie_history_list     = QListWidget()
        self.series_history_list    = QListWidget()

        #Set that items are viewed from left to right
        self.live_history_list.setFlow(QListView.LeftToRight)
        self.movie_history_list.setFlow(QListView.LeftToRight)
        self.series_history_list.setFlow(QListView.LeftToRight)

        #Create labels for lists
        self.live_history_lbl   = QLabel("Previously watched TV")
        self.movie_history_lbl  = QLabel("Previously watched movies")
        self.series_history_lbl = QLabel("Previously watched series")

        #Set fonts
        self.live_history_lbl.setFont(QFont('Segoe UI', 14, QFont.Bold))
        self.movie_history_lbl.setFont(QFont('Segoe UI', 14, QFont.Bold))
        self.series_history_lbl.setFont(QFont('Segoe UI', 14, QFont.Bold))

        #Add widgets to home tab
        self.home_tab_layout.addWidget(self.live_history_lbl)
        self.home_tab_layout.addWidget(self.live_history_list)
        self.home_tab_layout.addWidget(self.movie_history_lbl)
        self.home_tab_layout.addWidget(self.movie_history_list)
        self.home_tab_layout.addWidget(self.series_history_lbl)
        self.home_tab_layout.addWidget(self.series_history_list)

    def load_default_sorting_order(self):
        sorting_order = ""

        config = configparser.ConfigParser()
        config.read(self.user_data_file)

        if 'Sorting order' in config:
            # self.external_player_command = config['ExternalPlayer'].get('Command', '')
            sorting_order = config['Sorting order'].get('Order', '')

        print(f"loading default sorting order: {sorting_order}")

        if not sorting_order:
            # Keep the provider order for a new profile with no saved choice.
            self.default_sorting_order_box.setCurrentText("Sorting disabled")

        else:
            self.default_sorting_order_box.setCurrentText(sorting_order)

        self._load_category_sort_preferences(config)

        #Set sorting variables
        match self.default_sorting_order_box.currentText():
            case "A-Z":
                self.sorting_enabled    = True
                self.sorting_order      = 0
                self.remember_category_sorting = False

            case "Z-A":
                self.sorting_enabled    = True
                self.sorting_order      = 1

                self.remember_category_sorting = False

            case "Remember per category":
                # Unsaved categories inherit the last persisted global preference.
                self.sorting_enabled    = True
                self.sorting_order      = 0
                self.remember_category_sorting = True

            case _:
                self.sorting_enabled    = False
                self.sorting_order      = 0
                self.remember_category_sorting = False

    def _load_category_sort_preferences(self, config):
        """Reset category sorting before an account-specific load."""
        self.category_sort_preferences = {
            'LIVE': {}, 'Movies': {}, 'Series': {}
        }
        self.category_list_sort_preferences = {}
        self.category_sort_fallback = self._sorting_preference_value(
            self.sorting_enabled, self.sorting_order
        )

    def _load_account_sort_preferences(self):
        """Load category sorting choices belonging to the active account."""
        self._load_category_sort_preferences(None)
        if not self.provider_preferences_file:
            return
        saved = load_provider_preferences(
            self.provider_preferences_file
        ).get('category_sorting', {})
        if not isinstance(saved, dict):
            return
        saved_fallback = saved.get('fallback', 'a_z')
        if saved_fallback in ('a_z', 'z_a', 'disabled'):
            self.category_sort_fallback = saved_fallback

        for stream_type in self.category_sort_preferences:
            preferences = saved.get('preferences', {}).get(stream_type, {})
            if isinstance(preferences, dict):
                self.category_sort_preferences[stream_type] = {
                    str(key): value
                    for key, value in preferences.items()
                    if value in ('a_z', 'z_a', 'disabled')
                }

            category_list_preference = saved.get(
                'category_lists', {}
            ).get(stream_type, '')
            if category_list_preference in ('a_z', 'z_a', 'disabled'):
                self.category_list_sort_preferences[stream_type] = (
                    category_list_preference
                )

    def _save_category_sort_preferences(self):
        """Store category sorting preferences for the active IPTV account."""
        if not self.provider_preferences_file:
            return
        current = load_provider_preferences(self.provider_preferences_file)
        category_sorting = {
            'fallback': self.category_sort_fallback,
            'preferences': self.category_sort_preferences,
            'category_lists': self.category_list_sort_preferences,
        }

        try:
            save_provider_preferences(
                self.provider_preferences_file,
                current.get('hidden_categories', {}),
                category_sorting,
            )
        except OSError as e:
            print(f"Could not save category sorting preferences: {e}")

    def _sorting_preference_value(self, sorting_enabled, sort_order):
        if not sorting_enabled:
            return 'disabled'
        return 'z_a' if sort_order == 1 else 'a_z'

    def _sorting_tuple_from_preference(self, preference):
        if preference == 'disabled':
            return False, 0
        return True, 1 if preference == 'z_a' else 0

    def _category_sort_preference_key(self, category_name, category_id=None):
        """Use stable provider ids, with dedicated keys for synthetic categories."""
        if category_name == self.all_categories_text:
            return 'all'
        if category_name == self.fav_categories_text:
            return 'favorites'
        return f"category:{category_id}"

    def _selected_category(self, stream_type):
        selected_item = self.category_list_widgets[stream_type].currentItem()
        if selected_item is None:
            return self.all_categories_text, None

        category_data = selected_item.data(Qt.UserRole) or {}
        category_name = category_data.get('category_name', selected_item.text())
        return category_name, category_data.get('category_id')

    def _sorting_for_category(self, stream_type, category_name, category_id=None):
        if not self.remember_category_sorting:
            return self.sorting_enabled, self.sorting_order

        preference_key = self._category_sort_preference_key(
            category_name, category_id
        )
        preference = self.category_sort_preferences[stream_type].get(
            preference_key, self.category_sort_fallback
        )
        return self._sorting_tuple_from_preference(preference)

    def _sorting_for_category_list(self, stream_type):
        """Return the remembered order for a tab's category column."""
        if not self.remember_category_sorting:
            return self.sorting_enabled, self.sorting_order

        preference = self.category_list_sort_preferences.get(
            stream_type, self.category_sort_fallback
        )
        return self._sorting_tuple_from_preference(preference)

    def set_all_sorting_order(self, sorting_order):
        match sorting_order:
            case "A-Z":
                print("sorting A-Z")
                self.sort_list(self.category_search_bars["LIVE"], 'category', "LIVE", self.category_list_widgets, True, 0)
                self.sort_list(self.category_search_bars["Movies"], 'category', "Movies", self.category_list_widgets, True, 0)
                self.sort_list(self.category_search_bars["Series"], 'category', "Series", self.category_list_widgets, True, 0)

                self.sort_list(self.streaming_search_bars["LIVE"], 'streaming', "LIVE", self.streaming_list_widgets, True, 0)
                self.sort_list(self.streaming_search_bars["Movies"], 'streaming', "Movies", self.streaming_list_widgets, True, 0)
                self.sort_list(self.streaming_search_bars["Series"], 'streaming', "Series", self.streaming_list_widgets, True, 0)

            case "Z-A":
                print("sorting Z-A")
                self.sort_list(self.category_search_bars["LIVE"], 'category', "LIVE", self.category_list_widgets, True, 1)
                self.sort_list(self.category_search_bars["Movies"], 'category', "Movies", self.category_list_widgets, True, 1)
                self.sort_list(self.category_search_bars["Series"], 'category', "Series", self.category_list_widgets, True, 1)

                self.sort_list(self.streaming_search_bars["LIVE"], 'streaming', "LIVE", self.streaming_list_widgets, True, 1)
                self.sort_list(self.streaming_search_bars["Movies"], 'streaming', "Movies", self.streaming_list_widgets, True, 1)
                self.sort_list(self.streaming_search_bars["Series"], 'streaming', "Series", self.streaming_list_widgets, True, 1)

            case _:
                print("sorting disabled")
                self.sort_list(self.category_search_bars["LIVE"], 'category', "LIVE", self.category_list_widgets, False, 0)
                self.sort_list(self.category_search_bars["Movies"], 'category', "Movies", self.category_list_widgets, False, 0)
                self.sort_list(self.category_search_bars["Series"], 'category', "Series", self.category_list_widgets, False, 0)

                self.sort_list(self.streaming_search_bars["LIVE"], 'streaming', "LIVE", self.streaming_list_widgets, False, 0)
                self.sort_list(self.streaming_search_bars["Movies"], 'streaming', "Movies", self.streaming_list_widgets, False, 0)
                self.sort_list(self.streaming_search_bars["Series"], 'streaming', "Series", self.streaming_list_widgets, False, 0)

    def set_default_sorting_order(self, e, combobox):
        sorting_order = combobox.currentText()

        print(f"setting default sorting order: {sorting_order}")

        #Set sorting variables
        match sorting_order:
            case "A-Z":
                self.sorting_enabled    = True
                self.sorting_order      = 0
                self.remember_category_sorting = False
                self.category_sort_fallback = 'a_z'

            case "Z-A":
                self.sorting_enabled    = True
                self.sorting_order      = 1

                self.remember_category_sorting = False
                self.category_sort_fallback = 'z_a'

            case "Remember per category":
                self.sorting_enabled    = True
                self.sorting_order      = 0
                self.remember_category_sorting = True

            case _:
                self.sorting_enabled    = False
                self.sorting_order      = 0
                self.remember_category_sorting = False
                self.category_sort_fallback = 'disabled'

        # Cached category views include the selected ordering, so discard them when
        # the global sorting preference changes.
        for stream_cache in self.category_view_cache.values():
            stream_cache.clear()
        for item_cache in self.category_item_cache.values():
            item_cache.clear()
        for stream_type in self.active_category_view_key:
            self.active_category_view_key[stream_type] = None

        if sorting_order == REMEMBER_CATEGORY_SORTING:
            # Reapply both the category-column order and the preference for the
            # category currently visible in each content tab.
            for stream_type in self.streaming_list_widgets:
                category_list_enabled, category_list_order = (
                    self._sorting_for_category_list(stream_type)
                )
                self.sort_list(
                    self.category_search_bars[stream_type], 'category',
                    stream_type, self.category_list_widgets,
                    category_list_enabled, category_list_order
                )
                category_name, category_id = self._selected_category(stream_type)
                enabled, order = self._sorting_for_category(
                    stream_type, category_name, category_id
                )
                prepared_entries = self._entries_for_category_view(
                    stream_type, category_name, category_id
                )
                self.currently_loaded_streams[stream_type] = list(
                    prepared_entries
                )
                self.sort_list(
                    self.streaming_search_bars[stream_type], 'streaming',
                    stream_type, self.streaming_list_widgets, enabled, order
                )
                self.active_category_view_key[stream_type] = (
                    self._category_view_key(
                        stream_type, category_name, category_id
                    )
                )
        else:
            self.set_all_sorting_order(sorting_order)

        config = configparser.ConfigParser()
        config.read(self.user_data_file)

        config['Sorting order'] = {'Order': sorting_order}
        if 'Category sorting' not in config:
            config.add_section('Category sorting')
        config['Category sorting']['fallback'] = self.category_sort_fallback

        write_config_file(self.user_data_file, config)

    def init_settings_tab(self):
        #Create items in settings tab
        self.settings_layout.setSpacing(20)
        self.settings_layout.setAlignment(Qt.AlignTop)

        self.address_book_button = QPushButton("IPTV accounts")
        self.address_book_button.setIcon(self.account_manager_icon)
        self.address_book_button.setToolTip("Manage IPTV accounts")
        self.address_book_button.clicked.connect(self.open_address_book)

        # Keep both player choices in one compact group. The radio buttons make the
        # active mode explicit, while the read-only field exposes the external path
        # without forcing the Settings tab to display a full-width status sentence.
        self.player_group_box = QGroupBox("Media player")
        self.player_group_layout = QGridLayout(self.player_group_box)

        self.internal_player_radio = QRadioButton(
            "Internal VLC (requires VLC installed on this computer)"
        )
        self.internal_player_radio.setToolTip(
            "Play inside this application using the latest VLC installed on this computer"
        )

        self.external_player_radio = QRadioButton("External player")
        self.external_player_radio.setToolTip(
            "Play streams with an installed application such as VLC, MPV, or MPC-HC"
        )

        self.player_mode_group = QButtonGroup(self)
        self.player_mode_group.setExclusive(True)
        self.player_mode_group.addButton(self.internal_player_radio)
        self.player_mode_group.addButton(self.external_player_radio)

        self.external_player_path = QLineEdit()
        self.external_player_path.setReadOnly(True)
        self.external_player_path.setPlaceholderText("No external player selected")
        self.external_player_path.setToolTip(
            "Path kept for the external player, even while Internal VLC is active"
        )

        self.choose_player_button = QPushButton("Browse…")
        self.choose_player_button.setIcon(self.mediaplayer_icon)
        self.choose_player_button.setToolTip("Select an external media player executable")
        self.choose_player_button.clicked.connect(self.choose_external_player)

        self.internal_player_settings_button = QPushButton("Options…")
        self.internal_player_settings_button.setToolTip(
            "Configure seek, volume, and playback-speed steps"
        )
        self.internal_player_settings_button.setEnabled(False)
        self.internal_player_settings_button.clicked.connect(
            self.open_internal_player_settings
        )

        self.current_player_label = QLabel("")
        self.current_player_label.setStyleSheet("color: #5b8def;")

        self.internal_player_radio.toggled.connect(
            lambda checked: self.use_embedded_player() if checked else None
        )
        self.internal_player_radio.toggled.connect(
            self.internal_player_settings_button.setEnabled
        )
        self.external_player_radio.toggled.connect(self.use_external_player)

        self.player_group_layout.addWidget(self.internal_player_radio, 0, 0)
        # Align the internal options with the complete path-and-Browse area used
        # by the external player row directly below it.
        self.player_group_layout.addWidget(
            self.internal_player_settings_button, 0, 1, 1, 2
        )
        self.player_group_layout.addWidget(self.external_player_radio, 1, 0)
        self.player_group_layout.addWidget(self.external_player_path, 1, 1)
        self.player_group_layout.addWidget(self.choose_player_button, 1, 2)
        self.player_group_layout.addWidget(self.current_player_label, 2, 0, 1, 3)
        self.player_group_layout.setColumnStretch(1, 1)

        self.content_group_box = QGroupBox("Content")
        self.content_group_layout = QHBoxLayout(self.content_group_box)
        self.content_checkboxes = {}
        for stream_type in ('LIVE', 'Movies', 'Series'):
            checkbox = QCheckBox(stream_type)
            checkbox.setToolTip(
                f"Show the {stream_type} tab and load its data for the active account"
            )
            checkbox.stateChanged.connect(
                lambda state, selected_type=stream_type:
                self.toggle_content_type(selected_type, state)
            )
            self.content_checkboxes[stream_type] = checkbox
            self.content_group_layout.addWidget(checkbox)
        self.content_group_layout.addStretch()

        self.keep_on_top_checkbox = QCheckBox("Keep on top")
        self.keep_on_top_checkbox.setToolTip("Keep the application on top of all windows")
        self.keep_on_top_checkbox.stateChanged.connect(self.toggle_keep_on_top)

        self.default_sorting_order_box = QComboBox()
        self.default_sorting_order_box.addItems([
            "A-Z", "Z-A", "Sorting disabled", REMEMBER_CATEGORY_SORTING
        ])
        self.default_sorting_order_box.setCurrentText("Sorting disabled")
        self.default_sorting_order_box.currentTextChanged.connect(lambda e: self.set_default_sorting_order(e, self.default_sorting_order_box))

        self.update_checker = QPushButton("Check for updates")
        self.update_checker.clicked.connect(lambda: self.check_for_updates(True))

        self.auto_update_checkbox = QCheckBox("Auto check for updates")
        self.auto_update_checkbox.setToolTip("Automatically check for updates at startup")
        self.auto_update_checkbox.stateChanged.connect(self.toggle_auto_update)

        self.advanced_network_button = QPushButton("Advanced settings…")
        self.advanced_network_button.setToolTip(
            "Configure request timeouts, Info refresh, LIVE status checks, retries, and User-Agent"
        )
        self.advanced_network_button.clicked.connect(self.open_network_settings)

        self.theme_select_box = QComboBox()
        self.theme_select_box.addItems(["System", "Light", "Dark"])
        self.theme_select_box.setToolTip("Switch between Light, Dark, or follow the OS setting (default).")
        self.theme_select_box.currentTextChanged.connect(self.theme_changed)

        # Group the remaining preferences consistently with Media player and Content.
        self.window_behavior_group_box = QGroupBox("Window behavior")
        window_behavior_layout = QHBoxLayout(self.window_behavior_group_box)
        window_behavior_layout.addWidget(self.keep_on_top_checkbox)
        window_behavior_layout.addSpacing(30)
        window_behavior_layout.addWidget(QLabel("Theme:"))
        window_behavior_layout.addWidget(self.theme_select_box, 1)

        self.sorting_group_box = QGroupBox("Sorting")
        sorting_layout = QHBoxLayout(self.sorting_group_box)
        sorting_layout.addWidget(QLabel("Default sorting order:"))
        sorting_layout.addWidget(self.default_sorting_order_box, 1)

        self.advanced_settings_group_box = QGroupBox("Advanced settings")
        advanced_settings_layout = QHBoxLayout(self.advanced_settings_group_box)
        self.advanced_network_button.setText("Open advanced settings…")
        advanced_settings_layout.addWidget(self.advanced_network_button)

        self.updates_group_box = QGroupBox("Updates")
        updates_layout = QHBoxLayout(self.updates_group_box)
        updates_layout.addWidget(self.update_checker)
        updates_layout.addWidget(self.auto_update_checkbox)
        updates_layout.addStretch()

        # Keep the Settings page in the exact functional order shown to the user.
        self.settings_layout.addWidget(self.address_book_button,             0, 0, 1, 2)
        self.settings_layout.addWidget(self.content_group_box,               1, 0, 1, 2)
        self.settings_layout.addWidget(self.window_behavior_group_box,       2, 0, 1, 2)
        self.settings_layout.addWidget(self.sorting_group_box,               3, 0, 1, 2)
        self.settings_layout.addWidget(self.player_group_box,                4, 0, 1, 2)
        self.settings_layout.addWidget(self.advanced_settings_group_box,     5, 0, 1, 2)
        self.settings_layout.addWidget(self.updates_group_box,               6, 0, 1, 2)

    def load_default_user_agent(self):
        #Read userdata config file
        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError):
            config = configparser.ConfigParser()

        #Check if defined in config. Otherwise set to default
        if config.has_option('User-Agent', 'user-agent'):
            self.current_user_agent = config['User-Agent']['user-agent']
        else:
            self.current_user_agent = DEFAULT_USER_AGENT_HEADER

    def load_default_content(self):
        #Read userdata config file
        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError):
            config = configparser.ConfigParser()

        # Prefer the new independent values. An existing VOD preference remains a
        # migration fallback for Movies and Series, so current users keep their choice.
        def read_boolean(section, option, fallback):
            try:
                return config.getboolean(section, option, fallback=fallback)
            except (ValueError, configparser.Error):
                return fallback

        if config.has_section('Content'):
            for stream_type in self.content_enabled:
                self.content_enabled[stream_type] = read_boolean(
                    'Content', stream_type, True
                )
        else:
            legacy_vods_enabled = read_boolean('VOD', 'enabled', True)
            self.content_enabled = {
                'LIVE': True,
                'Movies': legacy_vods_enabled,
                'Series': legacy_vods_enabled
            }

        self._apply_content_visibility()

        # Loading preferences must not trigger three redundant writes to userdata.ini.
        for stream_type, checkbox in self.content_checkboxes.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(self.content_enabled[stream_type])
            checkbox.blockSignals(False)

    def _apply_content_visibility(self):
        """Show only enabled content tabs while keeping Info and Settings available."""
        tab_by_stream_type = {
            'LIVE': self.live_tab,
            'Movies': self.movies_tab,
            'Series': self.series_tab
        }
        for stream_type, tab in tab_by_stream_type.items():
            self.tab_widget.setTabVisible(
                self.tab_widget.indexOf(tab),
                self.content_enabled[stream_type]
            )

    def open_network_settings(self):
        """Open the modal editor after all persisted network values are loaded."""
        dialog = NetworkSettingsDialog(self)
        self._prepare_dialog_theme(dialog)
        dialog.exec_()

    def open_internal_player_settings(self):
        """Edit and immediately apply the internal player's control steps."""
        dialog = InternalPlayerSettingsDialog(self)
        self._prepare_dialog_theme(dialog)
        if dialog.exec_() != QDialog.Accepted:
            return

        self.internal_seek_step_seconds = dialog.seek_step.value()
        self.internal_volume_step_percent = dialog.volume_step.value()
        self.internal_speed_step = round(dialog.speed_step.value(), 2)
        self.internal_audio_language = dialog.audio_language.currentData() or ""
        self.internal_subtitle_language = dialog.subtitle_language.currentData() or ""
        self.save_internal_player_settings()

        if self._embedded_player_command_queue is not None:
            self._embedded_player_command_queue.put({
                'command': 'control_steps',
                'seek_seconds': self.internal_seek_step_seconds,
                'volume_percent': self.internal_volume_step_percent,
                'speed_step': self.internal_speed_step,
                'audio_language': self.internal_audio_language,
                'subtitle_language': self.internal_subtitle_language
            })

    def save_internal_player_settings(self):
        """Persist internal-player controls without replacing unrelated settings."""
        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError):
            config = configparser.ConfigParser()
        # Preserve the volume written by the isolated player process.
        saved_volume = config.get('InternalPlayer', 'volume', fallback='80')
        config['InternalPlayer'] = {
            'seek_step_seconds': str(self.internal_seek_step_seconds),
            'volume_step_percent': str(self.internal_volume_step_percent),
            'speed_step': str(self.internal_speed_step),
            'audio_language': self.internal_audio_language,
            'subtitle_language': self.internal_subtitle_language,
            'volume': saved_volume
        }
        try:
            write_config_file(self.user_data_file, config)
        except OSError as error:
            print(f"Could not save internal player settings: {error}")

    def load_default_internal_player_settings(self):
        """Load bounded control steps so manual INI edits remain safe."""
        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError):
            config = configparser.ConfigParser()

        try:
            seek_seconds = config.getint(
                'InternalPlayer', 'seek_step_seconds',
                fallback=DEFAULT_INTERNAL_SEEK_STEP_SECONDS
            )
        except (ValueError, configparser.Error):
            seek_seconds = DEFAULT_INTERNAL_SEEK_STEP_SECONDS
        try:
            volume_percent = config.getint(
                'InternalPlayer', 'volume_step_percent',
                fallback=DEFAULT_INTERNAL_VOLUME_STEP_PERCENT
            )
        except (ValueError, configparser.Error):
            volume_percent = DEFAULT_INTERNAL_VOLUME_STEP_PERCENT
        try:
            speed_step = config.getfloat(
                'InternalPlayer', 'speed_step',
                fallback=DEFAULT_INTERNAL_SPEED_STEP
            )
        except (ValueError, configparser.Error):
            speed_step = DEFAULT_INTERNAL_SPEED_STEP

        self.internal_seek_step_seconds = max(1, min(seek_seconds, 300))
        self.internal_volume_step_percent = max(1, min(volume_percent, 25))
        self.internal_speed_step = max(0.05, min(round(speed_step, 2), 1.0))
        valid_languages = {code for _, code in MEDIA_LANGUAGE_OPTIONS}
        audio_language = config.get('InternalPlayer', 'audio_language', fallback='')
        subtitle_language = config.get('InternalPlayer', 'subtitle_language', fallback='')
        self.internal_audio_language = (
            audio_language if audio_language in valid_languages else ''
        )
        self.internal_subtitle_language = (
            subtitle_language
            if subtitle_language in valid_languages | {'disabled'} else ''
        )

    def apply_network_settings(self, user_agent, connection_timeout, read_timeout,
                             live_status_timeout, live_status_retries,
                             stream_status_enabled, account_refresh_interval,
                             account_auto_refresh_enabled, catalog_cache_enabled,
                             catalog_cache_max_age_hours):
        """Apply and persist all advanced provider settings in one operation."""
        self.current_user_agent = user_agent or DEFAULT_USER_AGENT_HEADER
        NETWORK_SETTINGS.connection_timeout = connection_timeout
        NETWORK_SETTINGS.read_timeout = read_timeout
        NETWORK_SETTINGS.live_status_timeout = live_status_timeout
        NETWORK_SETTINGS.live_status_retries = live_status_retries
        self.stream_status_enabled = stream_status_enabled
        self.account_info_refresh_interval = account_refresh_interval
        self.account_info_auto_refresh_enabled = account_auto_refresh_enabled
        self.catalog_cache_enabled = catalog_cache_enabled
        self.catalog_cache_max_age_hours = catalog_cache_max_age_hours
        self._apply_stream_status_visibility()
        self._update_account_info_timer()

        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError):
            config = configparser.ConfigParser()

        config['User-Agent'] = {'user-agent': self.current_user_agent}
        config['Timeouts'] = {
            'CONNECTION_TIMEOUT': str(connection_timeout),
            'READ_TIMEOUT': str(read_timeout),
            'LIVE_STATUS_TIMEOUT': str(live_status_timeout),
            'LIVE_STATUS_RETRIES': str(live_status_retries)
        }
        config['StreamStatus'] = {'enabled': str(stream_status_enabled)}
        config['AccountInfo'] = {
            'refresh_interval': str(account_refresh_interval),
            'auto_refresh_enabled': str(account_auto_refresh_enabled)
        }
        config['CatalogCache'] = {
            'enabled': str(catalog_cache_enabled),
            'max_age_hours': str(catalog_cache_max_age_hours)
        }

        try:
            write_config_file(self.user_data_file, config)
            self.animate_progress(0, 100, "Network settings saved")
        except OSError as e:
            print(f"Could not write user data file: {e}")
            self.animate_progress(0, 100, f"Failed saving network settings: {e}", "error")

    def load_default_network_options(self):
        try:
            # Read persisted network values. A malformed file falls back to the
            # in-code defaults instead of preventing the application from starting.
            config = configparser.ConfigParser()
            try:
                config.read(self.user_data_file)
            except (configparser.Error, UnicodeDecodeError):
                config = configparser.ConfigParser()

            # Clamp manually edited values to the same ranges as the dialog. Each
            # value falls back independently, so one bad entry cannot discard the rest.
            def read_bounded_integer(option, default, minimum, maximum):
                try:
                    value = config.getint("Timeouts", option, fallback=default)
                except (ValueError, configparser.Error):
                    value = default
                return max(minimum, min(value, maximum))

            if config.has_section("Timeouts"):
                NETWORK_SETTINGS.connection_timeout = read_bounded_integer(
                    "CONNECTION_TIMEOUT", DEFAULT_CONNECTION_TIMEOUT, 1, 999
                )
                NETWORK_SETTINGS.read_timeout = read_bounded_integer(
                    "READ_TIMEOUT", DEFAULT_READ_TIMEOUT, 1, 999
                )
                NETWORK_SETTINGS.live_status_timeout = read_bounded_integer(
                    "LIVE_STATUS_TIMEOUT", DEFAULT_LIVE_STATUS_TIMEOUT, 1, 999
                )
                NETWORK_SETTINGS.live_status_retries = read_bounded_integer(
                    "LIVE_STATUS_RETRIES", DEFAULT_LIVE_STATUS_RETRIES,
                    0, MAX_LIVE_STATUS_RETRIES
                )

            try:
                self.account_info_refresh_interval = config.getint(
                    'AccountInfo', 'refresh_interval',
                    fallback=DEFAULT_ACCOUNT_INFO_REFRESH_INTERVAL
                )
            except (ValueError, configparser.Error):
                self.account_info_refresh_interval = (
                    DEFAULT_ACCOUNT_INFO_REFRESH_INTERVAL
                )
            self.account_info_refresh_interval = max(
                10, min(self.account_info_refresh_interval, 3600)
            )
            try:
                self.account_info_auto_refresh_enabled = config.getboolean(
                    'AccountInfo', 'auto_refresh_enabled', fallback=True
                )
            except (ValueError, configparser.Error):
                self.account_info_auto_refresh_enabled = True
            self._update_account_info_timer()

            try:
                self.catalog_cache_enabled = config.getboolean(
                    'CatalogCache', 'enabled', fallback=True
                )
            except (ValueError, configparser.Error):
                self.catalog_cache_enabled = True
            try:
                self.catalog_cache_max_age_hours = config.getint(
                    'CatalogCache', 'max_age_hours',
                    fallback=DEFAULT_CATALOG_CACHE_MAX_AGE_HOURS
                )
            except (ValueError, configparser.Error):
                self.catalog_cache_max_age_hours = (
                    DEFAULT_CATALOG_CACHE_MAX_AGE_HOURS
                )
            self.catalog_cache_max_age_hours = max(
                1, min(self.catalog_cache_max_age_hours, 720)
            )

        except Exception as e:
            print(f"Failed loading default timeout values: {e}")

    def _version_tuple(self, v):
        # "V1.03.02" -> (1, 3, 2). Used so the update checker doesn't prompt when
        # the current build is AHEAD of upstream (e.g. an unreleased fork build).
        return tuple(int(x) for x in re.findall(r'\d+', v or ""))

    def check_for_updates(self, enable_update_msg):
        try:
            print("Checking for updates")

            #Create github api url to fetch data from
            git_api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

            #Request data from url. Pair a small read-timeout with the connection timeout —
            #without one a slow GitHub response can block the main thread indefinitely
            #(the previous code only set the connection timeout).
            git_resp = requests.get(
                git_api_url, timeout=(NETWORK_SETTINGS.connection_timeout, 5)
            )

            #Get data and latest version
            data = git_resp.json()
            latest_version = data['tag_name']

            #Only prompt when upstream is strictly newer than what we're running —
            #avoids a spurious "update available" dialog for fork/dev builds that
            #carry a higher version number.
            if self._version_tuple(latest_version) > self._version_tuple(CURRENT_VERSION):
                #If not up to date ask if user wants to go to download page
                update_dialog = QMessageBox(self)
                update_dialog.setIcon(QMessageBox.Question)
                update_dialog.setWindowTitle('Update Available')
                update_dialog.setText(
                    f"A new version ({latest_version}) is available.\n"
                    "Do you want to visit the download page?"
                )
                update_dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                update_dialog.setDefaultButton(QMessageBox.Yes)
                self._prepare_dialog_theme(update_dialog)
                reply = update_dialog.exec_()

                #If user wants to go to download page, open latest version page
                if reply == QMessageBox.Yes:
                    latest_version_url = data['html_url']

                    QDesktopServices.openUrl(QUrl(latest_version_url))

            #Current version is up to date
            elif enable_update_msg:
                update_dialog = QMessageBox(self)
                update_dialog.setIcon(QMessageBox.Information)
                update_dialog.setWindowTitle('No Update')
                update_dialog.setText("You are using the latest version.")
                update_dialog.setStandardButtons(QMessageBox.Ok)
                self._prepare_dialog_theme(update_dialog)
                update_dialog.exec_()

            else:
                self.animate_progress(0, 100, "No update available")

        except Exception as e:
            print(f"Failed update checker: {e}")

            if enable_update_msg:
                update_dialog = QMessageBox(self)
                update_dialog.setIcon(QMessageBox.Warning)
                update_dialog.setWindowTitle('Failed update checker')
                update_dialog.setText("Failed checking for updates.\nPlease try again.")
                update_dialog.setStandardButtons(QMessageBox.Ok)
                self._prepare_dialog_theme(update_dialog)
                update_dialog.exec_()
            else:
                self.animate_progress(0, 100, "Failed checking for updates", "error")

    def toggle_auto_update(self, state):
        checked = bool(state)

        config = configparser.ConfigParser()
        config.read(self.user_data_file)

        config['Updater'] = {'auto-update-checker': checked}

        write_config_file(self.user_data_file, config)

    def load_default_auto_update(self):
        #Read userdata file
        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError):
            config = configparser.ConfigParser()

        #Check if updater is in config
        if config.has_option('Updater', 'auto-update-checker'):
            if config['Updater']['auto-update-checker'] == 'True':
                #Set checkbox checked
                self.auto_update_checkbox.setCheckState(Qt.Checked)

                #If auto update checker is enabled, check for update
                self.check_for_updates(False)

        #If not enable the auto-update-checker by default
        else:
            #Write default value to userdata file
            config['Updater'] = {'auto-update-checker': True}

            try:
                write_config_file(self.user_data_file, config)
            except OSError as e:
                print(f"Could not write user data file: {e}")

            #Set checkbox checked
            self.auto_update_checkbox.setCheckState(Qt.Checked)

            #Check for updates
            self.check_for_updates(False)

    def init_progress_bar(self):
        #Create progress bar
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setFixedHeight(25)
        self.progress_bar.setTextVisible(True)
        self.set_progress_state("busy")

        #Animate progress bar
        self.playlist_progress_animation = QPropertyAnimation(self.progress_bar, b"value")
        self.playlist_progress_animation.setDuration(1000)  # longer duration for smoother animation
        self.playlist_progress_animation.setEasingCurve(QEasingCurve.InOutQuad)
        self._progress_animation_final_state = "success"
        self.playlist_progress_animation.finished.connect(
            self._finish_progress_animation
        )

    def load_data_at_startup(self):
        # Load internal-player steps before a startup account can launch media.
        self.load_default_internal_player_settings()

        #Load external media player
        self.external_player_command = self.load_external_player_command()
        self._refresh_current_player_label()

        #Load default sorting setting
        self.load_default_sorting_order()

        #Load category exclusions before provider data populates the three columns
        self._load_hidden_categories()

        #Load default user agent
        self.load_default_user_agent()

        #Load independent LIVE, Movies, and Series availability
        self.load_default_content()

        #Load default auto update checker
        self.load_default_auto_update()

        #Load stream-status toggle (issue #74)
        self.load_default_stream_status()

        #Apply persisted theme (Light / Dark / System) — default System
        self.load_default_theme()

        # Load network and cache preferences before startup credentials can begin
        # provider requests in the background.
        self.load_default_network_options()

    def load_startup_credentials(self):
        # Load playlist on startup if enabled. A malformed/missing key here used to crash
        # the app right after the login screen (issue #92), so every access is guarded.
        try:
            selected_startup_account = load_startup_account(self.user_data_file)
            data = load_account(self.user_data_file, selected_startup_account)
        except (configparser.Error, UnicodeDecodeError) as e:
            print(f"Failed reading user data file at startup: {e}")
            return

        if not selected_startup_account or selected_startup_account == 'None':
            return

        parsed_account = parse_account(data)
        if parsed_account is None:
            return

        try:
            method, fields = parsed_account

            if method == 'manual':
                server, username, password, live_url_format, movie_url_format, series_url_format = fields

                self.server            = server
                self.username          = username
                self.password          = password
                self.live_url_format   = live_url_format
                self.movie_url_format  = movie_url_format
                self.series_url_format = series_url_format
                self.set_active_account(selected_startup_account)

                self.login()

            elif method == 'm3u_plus':
                m3u_url, live_url_format, movie_url_format, series_url_format = fields

                self.live_url_format   = live_url_format
                self.movie_url_format  = movie_url_format
                self.series_url_format = series_url_format

                if self.extract_credentials_from_m3u_plus_url(m3u_url):
                    self.set_active_account(selected_startup_account)
                    self.login()
            else:
                print(f"Skipping startup account '{selected_startup_account}': data is malformed.")
        except Exception as e:
            print(f"Failed loading startup account: {e}")

    def toggle_keep_on_top(self, state):
        if state == Qt.Checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()

    def _apply_theme(self, theme_name):
        dark = apply_application_theme(QtWidgets.qApp, theme_name)
        apply_windows_title_bar_theme(self, dark)
        self._refresh_theme_icons(dark)
        # Qt style-sheet palette references are resolved when the sheet is set.
        # Reapply list sheets so switching Dark -> Light updates existing widgets.
        list_widgets = (
            list(getattr(self, 'category_list_widgets', {}).values())
            + list(getattr(self, 'streaming_list_widgets', {}).values())
        )
        for list_widget in list_widgets:
            style_sheet = list_widget.styleSheet()
            list_widget.setStyleSheet("")
            list_widget.setPalette(QtWidgets.qApp.palette())
            list_widget.setStyleSheet(style_sheet)
            list_widget.viewport().update()

    def _prepare_dialog_theme(self, dialog):
        """Apply the current palette and native title-bar theme to a dialog."""
        dialog.setPalette(QtWidgets.qApp.palette())
        apply_windows_title_bar_theme(
            dialog, application_palette_is_dark(QtWidgets.qApp)
        )

    def theme_changed(self, theme_name):
        self._apply_theme(theme_name)
        # Keep an already-open isolated player synchronized with Settings.
        if self._embedded_player_command_queue is not None:
            self._embedded_player_command_queue.put({
                'command': 'theme',
                'theme': theme_name
            })
        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError):
            config = configparser.ConfigParser()
        config['Theme'] = {'mode': theme_name}
        try:
            write_config_file(self.user_data_file, config)
        except OSError as e:
            print(f"Could not write user data file: {e}")

    def load_default_theme(self):
        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError):
            config = configparser.ConfigParser()
        mode = "System"
        if config.has_option("Theme", "mode"):
            mode = config["Theme"]["mode"]
            if mode not in ("System", "Light", "Dark"):
                mode = "System"
        # Block signals so applying the value to the combobox doesn't re-trigger
        # a write to disk.
        self.theme_select_box.blockSignals(True)
        self.theme_select_box.setCurrentText(mode)
        self.theme_select_box.blockSignals(False)
        self._apply_theme(mode)

    def _apply_stream_status_visibility(self):
        """Keep the indicator visibility consistent with the no-probe preference."""
        # Hiding the widget also releases its reserved space in the title layout.
        # More importantly, startOnlineWorker() uses the same flag to avoid sending
        # any future probe request to the IPTV provider.
        try:
            self.live_info_box.stream_status.setVisible(self.stream_status_enabled)
            if not self.stream_status_enabled:
                self.live_info_box.stream_status.setPixmap(
                    self.status_pixmap(self.path_to_unknown_status_icon, 24)
                )
        except Exception:
            pass

    def load_default_stream_status(self):
        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError):
            config = configparser.ConfigParser()

        if config.has_option('StreamStatus', 'enabled'):
            self.stream_status_enabled = (config['StreamStatus']['enabled'] == 'True')
        else:
            self.stream_status_enabled = True

        self._apply_stream_status_visibility()

    def toggle_content_type(self, stream_type, state):
        """Persist one content choice and immediately update tab visibility."""
        was_enabled = self.content_enabled[stream_type]
        is_enabled = bool(state)
        self.content_enabled[stream_type] = is_enabled
        self._apply_content_visibility()

        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError):
            config = configparser.ConfigParser()
        config['Content'] = {
            key: str(enabled)
            for key, enabled in self.content_enabled.items()
        }
        try:
            write_config_file(self.user_data_file, config)
        except OSError as e:
            print(f"Could not write user data file: {e}")

        # A newly visible tab needs provider data immediately. Reload every enabled
        # type as one consistent snapshot; the worker still skips disabled endpoints.
        # With no active account, the normal login path will load it later.
        if is_enabled and not was_enabled and all(
            (self.server, self.username, self.password)
        ):
            self.set_progress_bar(0, "Reloading enabled content...")
            self.fetch_data_thread()
    
    def toggle_cache_on_startup(self, state):
        if state == Qt.Checked:
            print("checked")
        else:
            print("unchecked")

    def open_m3u_plus_dialog(self):
        text, ok = QtWidgets.QInputDialog.getText(self, 'M3u_plus Login', 'Enter m3u_plus URL:')
        if ok and text:
            m3u_plus_url = text.strip()
            self.extract_credentials_from_m3u_plus_url(m3u_plus_url)
            self.login()

    def update_font_size(self, value):
        self.default_font_size = value
        for tab_name, list_widget in self.streaming_list_widgets.items():
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                font = item.font()
                font.setPointSize(value)
                item.setFont(font)

        font = QFont()
        font.setPointSize(value)
        self.iptv_info_text.setFont(font)

    def extract_credentials_from_m3u_plus_url(self, url):
        # Parses an Xtream get.php URL into (server, username, password). The previous
        # regex required `&type=m3u_plus` to appear in exactly that position and contained
        # a literal `&output=m3u8` as a "type" alternative — which was a bug. We now use
        # urllib.parse so the query parameters can appear in any order, and we follow
        # shortened-URL redirects (bit.ly etc.) before parsing (see issues #2 and #13).
        def _show_invalid():
            self.animate_progress(0, 100, "Invalid m3u_plus or m3u URL", "error")
            dlg = QMessageBox(self)
            dlg.setWindowTitle("Error!")
            dlg.setText("M3U plus URL is invalid!\nPlease enter a valid Xtream get.php URL.")
            dlg.exec()

        try:
            result = parse_xtream_m3u_url(url)

            # If it doesn't parse directly, the user may have pasted a shortened URL.
            # Follow redirects once (HEAD with a small timeout) and try the resolved URL.
            if result is None and url.lower().startswith(('http://', 'https://')):
                try:
                    resp = requests.head(url, allow_redirects=True, timeout=5)
                    if resp.url and resp.url != url:
                        print(
                            "Resolved shortened URL: "
                            f"{private_url_log_reference(url)} -> "
                            f"{private_url_log_reference(resp.url)}"
                        )
                        result = parse_xtream_m3u_url(resp.url)
                except requests.RequestException as e:
                    print(
                        "Could not resolve URL "
                        f"{private_url_log_reference(url)}: {e}"
                    )

            if result:
                self.server, self.username, self.password = result
                return True

            _show_invalid()
            return False
        except Exception as e:
            print(f"Error extracting credentials: {e}")
            self.animate_progress(0, 100, "Error extracting credentials", "error")
            return False

    def set_progress_text(self, text):
        self.progress_bar.setFormat(text)
        QtWidgets.qApp.processEvents()
        # QtWidgets.qApp.sendPostedEvents()

    def set_progress_state(self, state):
        """Apply a stable visual state without relying on message wording."""
        colors = {
            "busy": "#2d8fd5",
            "success": "#2ea44f",
            "error": "#d64545"
        }
        if state not in colors:
            state = "busy"

        self.progress_bar.setProperty("progressState", state)
        self.progress_bar.setStyleSheet(
            "QProgressBar {"
            " border: 1px solid palette(mid);"
            " border-radius: 3px;"
            " background-color: palette(base);"
            " color: palette(text);"
            " text-align: center;"
            "}"
            f"QProgressBar::chunk {{ background-color: {colors[state]}; }}"
        )

    def set_progress_bar(self, val, text, state=None):
        # Values below 100 describe work in progress. A completed operation defaults
        # to green; callers explicitly pass "error" for unsuccessful completion.
        progress_state = state or ("success" if val >= 100 else "busy")
        self.set_progress_state(progress_state)
        self.progress_bar.setFormat(text)
        if progress_state == "busy" and val <= 0:
            # Qt hides the format text while a QProgressBar uses its indeterminate
            # 0..0 range. A full blue bar communicates the unknown-duration busy
            # state while keeping the operation message visible in the center.
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(val)
        QtWidgets.qApp.processEvents()

    def animate_progress(self, start, end, text, state=None):
        self.playlist_progress_animation.stop()
        self.progress_bar.setRange(0, 100)
        self.playlist_progress_animation.setStartValue(start)
        self.playlist_progress_animation.setEndValue(end)
        self._progress_animation_final_state = state or (
            "success" if end >= 100 else "busy"
        )
        # Keep the bar blue during the animation, then expose the final result when
        # the target value is reached.
        self.set_progress_state("busy")
        self.set_progress_text(text)
        self.playlist_progress_animation.start()
        QtWidgets.qApp.processEvents()

    def _finish_progress_animation(self):
        """Apply the success or failure color selected by animate_progress()."""
        self.set_progress_state(self._progress_animation_final_state)

    def login(self):
        # When logging into another server, reset the progress bar
        self.set_progress_bar(0, "Logging in...")

        #Clear lists
        for tab_name, list_widget in self.streaming_list_widgets.items():
            list_widget.clear()

        for tab_name, list_widget in self.category_list_widgets.items():
            list_widget.clear()

        #Check if login credentials are not empty
        if not self.server or not self.username or not self.password:
            dlg = QMessageBox(self)
            dlg.setWindowTitle("Error!")
            dlg.setText("Please fill in all fields to login!")
            dlg.exec()

            return

        provider_key = account_cache_key(self.server, self.username)
        storage_key = self.active_account_id or provider_key
        dedicated_favorites_file = account_favorites_file(
            self.favorites_base_file, storage_key
        )
        previous_hashed_favorites_file = account_favorites_file(
            self.favorites_base_file, provider_key
        )
        favorites_migration_source = (
            previous_hashed_favorites_file
            if path.isfile(previous_hashed_favorites_file)
            else self.legacy_favorites_file
        )
        self.favorites_file = str(migrate_legacy_favorites_file(
            favorites_migration_source, dedicated_favorites_file
        ))

        #Start IPTV data fetch thread
        self.fetch_data_thread()

        self.set_progress_bar(0, "Going to fetch data...")

    def fetch_data_thread(self, force_refresh=False):
        dataWorker = FetchDataWorker(
            self.server,
            self.username,
            self.password,
            self.live_url_format,
            self.movie_url_format,
            self.series_url_format,
            self,
            self.content_enabled,
            self.catalog_cache_enabled,
            self.catalog_cache_max_age_hours,
            force_refresh
        )
        dataWorker.signals.finished.connect(self.process_data)
        dataWorker.signals.error.connect(self.on_fetch_data_error)
        dataWorker.signals.progress_bar.connect(self.animate_progress)
        dataWorker.signals.show_error_msg.connect(self.show_error_msg)
        dataWorker.signals.show_info_msg.connect(self.show_info_msg)
        self.threadpool.start(dataWorker)

    def refresh_provider_catalog(self):
        """Fetch every enabled provider collection while retaining cache fallback."""
        if not self.server or not self.username or not self.password:
            self.show_info_msg("No account selected", "Select an IPTV account first.")
            return
        self.set_progress_bar(0, "Refreshing provider catalog...")
        self.fetch_data_thread(force_refresh=True)

    def _is_info_tab_visible(self):
        """Return whether Info is the currently selected visible tab."""
        return self.tab_widget.currentWidget() is self.info_tab

    def _update_account_info_timer(self):
        """Run automatic refreshes only while Info is selected and enabled."""
        should_run = (
            self.account_info_auto_refresh_enabled
            and self._is_info_tab_visible()
            and bool(self.server and self.username and self.password)
        )
        if should_run:
            self.account_info_timer.start(
                self.account_info_refresh_interval * 1000
            )
        else:
            self.account_info_timer.stop()

    def _on_current_tab_changed(self, _index):
        """Refresh immediately on Info, then start or stop its periodic timer."""
        self._update_account_info_timer()
        if self._is_info_tab_visible():
            # Entering Info should show the current connection count immediately;
            # disabling auto-refresh affects only subsequent periodic requests.
            self.refresh_account_info()

    def refresh_account_info(self):
        """Refresh account metadata without downloading provider content."""
        if self.account_info_refresh_in_progress:
            return
        if not self.server or not self.username or not self.password:
            self.account_info_last_refresh_label.setText("No account selected")
            return

        self.account_info_refresh_in_progress = True
        self.refresh_account_info_button.setEnabled(False)
        self.account_info_last_refresh_label.setText("Refreshing…")
        worker = AccountInfoWorker(
            self.server,
            self.username,
            self.password,
            self.current_user_agent
        )
        worker.signals.finished.connect(self._account_info_refresh_finished)
        worker.signals.error.connect(self._account_info_refresh_failed)
        # Keep the Python wrapper alive until the QRunnable has emitted its result.
        self.account_info_worker = worker
        self.account_info_threadpool.start(worker)

    def _account_info_refresh_finished(self, iptv_info):
        """Display the refreshed metadata and release the request guard."""
        self.account_info_refresh_in_progress = False
        self.account_info_worker = None
        self.refresh_account_info_button.setEnabled(True)
        self.update_account_info(iptv_info)

    def _account_info_refresh_failed(self, error):
        """Keep existing information visible when a lightweight refresh fails."""
        self.account_info_refresh_in_progress = False
        self.account_info_worker = None
        self.refresh_account_info_button.setEnabled(True)
        self.account_info_last_refresh_label.setText(
            f"Refresh failed at {datetime.now().strftime('%H:%M:%S')}"
        )
        print(f"Failed refreshing account information: {error}")

    def update_account_info(self, iptv_info):
        """Render account and server metadata returned by player_api.php."""
        user_info = iptv_info.get("user_info", {})
        server_info = iptv_info.get("server_info", {})

        hostname = server_info.get("url", "Unknown")
        port = server_info.get("port", "Unknown")
        host = (
            "Unknown"
            if hostname == "Unknown" or port == "Unknown"
            else f"http://{hostname}:{port}"
        )

        def format_timestamp(value):
            """Format optional provider timestamps without breaking the Info tab."""
            try:
                return datetime.fromtimestamp(int(value)).strftime("%B %d, %Y")
            except (TypeError, ValueError, OSError, OverflowError):
                return "Unknown"

        expiry = format_timestamp(user_info.get("exp_date"))
        created_at = format_timestamp(user_info.get("created_at"))
        trial = "Yes" if user_info.get("is_trial") == "1" else "No"

        self.iptv_info_text.setText(
            f"Host: {host}\n"
            f"Username: {user_info.get('username', 'Unknown')}\n"
            f"Password: {user_info.get('password', 'Unknown')}\n"
            f"Max Connections: {user_info.get('max_connections', 'Unknown')}\n"
            f"Active Connections: {user_info.get('active_cons', 'Unknown')}\n"
            f"Timezone: {server_info.get('timezone', 'Unknown')}\n"
            f"Trial: {trial}\n"
            f"Status: {user_info.get('status', 'Unknown')}\n"
            f"Created At: {created_at}\n"
            f"Expiry: {expiry}\n"
        )
        self.account_info_last_refresh_label.setText(
            f"Last refreshed: {datetime.now().strftime('%H:%M:%S')}"
        )
        self._update_account_info_timer()

    def process_data(self, iptv_info, categories_per_stream_type, entries_per_stream_type):
        print("Going to process IPTV data now")

        self.categories_per_stream_type = categories_per_stream_type
        self.entries_per_stream_type    = entries_per_stream_type

        for stream_type, entries in self.entries_per_stream_type.items():
            self.category_item_counts[stream_type] = Counter(
                str(entry.get('category_id'))
                for entry in entries
                if entry.get('category_id') is not None
            )

        # A refreshed provider snapshot invalidates every prepared category view.
        for stream_cache in self.category_view_cache.values():
            stream_cache.clear()
        for item_cache in self.category_item_cache.values():
            item_cache.clear()
        for stream_type in self.active_category_view_key:
            self.active_category_view_key[stream_type] = None

        self.set_progress_bar(0, "Processing received data...")

        # A cache hit deliberately skips the account request. Keep the initial Info
        # state until that tab performs its existing lightweight refresh.
        if iptv_info:
            self.update_account_info(iptv_info)

        #Process categories and entries
        hidden_categories_changed = False
        for stream_type in self.entries_per_stream_type.keys():
            #Clear category and streaming list
            self.category_list_widgets[stream_type].clear()
            self.streaming_list_widgets[stream_type].clear()

            # A reload replaces the previous snapshot. Clearing these search sources
            # prevents duplicate and stale results after a content type is re-enabled.
            self.currently_loaded_streams[stream_type] = []
            self.currently_loaded_categories[stream_type] = []

            # Disabled types contain no newly requested data and stay out of the UI.
            if not self.content_enabled[stream_type]:
                continue

            #Fill currently loaded streams with current stream data
            for entry in self._entries_in_visible_categories(stream_type):
                self.currently_loaded_streams[stream_type].append(entry)

            # Remove exclusions for categories the current provider no longer sends.
            # This keeps userdata.ini compact without affecting disabled content types.
            provider_category_ids = {
                str(category.get('category_id', ''))
                for category in self.categories_per_stream_type[stream_type]
            }
            valid_hidden_ids = (
                self.hidden_category_ids[stream_type] & provider_category_ids
            )
            if valid_hidden_ids != self.hidden_category_ids[stream_type]:
                self.hidden_category_ids[stream_type] = valid_hidden_ids
                hidden_categories_changed = True

            # Fill the search source and visible list with non-hidden categories only.
            visible_categories = self._visible_categories(stream_type)
            for entry in visible_categories:
                self.currently_loaded_categories[stream_type].append(entry)

            #Add categories in category list
            num_of_categories = len(visible_categories)
            prev_perc = 0
            for idx, category_item in enumerate(visible_categories):
                item = self._new_category_item(stream_type, category_item)
                # item.setIcon(channel_icon)

                #Add item to list
                self.category_list_widgets[stream_type].addItem(item)

                perc = (idx * 100) / max(1, num_of_categories)
                if (perc - prev_perc) > 10:
                    prev_perc = perc
                    self.set_progress_bar(int(perc), f"Loading {stream_type} categories: {idx} of {num_of_categories}")
                    QtWidgets.qApp.processEvents()

            # Sort each first column with its remembered order when that mode is active.
            category_list_enabled, category_list_order = (
                self._sorting_for_category_list(stream_type)
            )
            self.sort_list(
                self.category_search_bars[stream_type], 'category', stream_type,
                self.category_list_widgets, category_list_enabled,
                category_list_order
            )

            # Build the stream list once in its final order. sortList() uses chunked
            # insertion for top-level catalogs so large Movie libraries do not block
            # the main window while Qt creates their rows.
            enabled, order = self._sorting_for_category(
                stream_type, self.all_categories_text
            )
            self.sort_list(
                self.streaming_search_bars[stream_type], 'streaming',
                stream_type, self.streaming_list_widgets, enabled, order
            )
            self.active_category_view_key[stream_type] = self._category_view_key(
                stream_type, self.all_categories_text
            )

        if hidden_categories_changed:
            self._save_hidden_categories()

        self.set_progress_bar(100, f"Finished loading")
        QtWidgets.qApp.processEvents()

    def on_fetch_data_error(self, error_msg):
        print(f"Error occurred while fetching data: {error_msg}")
        self.set_progress_bar(100, "Failed fetching data", "error")

    def show_error_msg(self, title, msg):
        QMessageBox.warning(self, title, msg)

    def show_info_msg(self, title, msg):
        QMessageBox.information(self, title, msg)

    def fetch_vod_info(self, vod_id):
        movie_info_fetcher = MovieInfoFetcher(self.server, self.username, self.password, vod_id, self)
        movie_info_fetcher.signals.finished.connect(self.process_vod_info)
        movie_info_fetcher.signals.error.connect(self.on_fetch_data_error)
        self.threadpool.start(movie_info_fetcher)

    def process_vod_info(self, vod_info, vod_data):
        #Get movie image url
        movie_img_url = vod_info.get('movie_image', 0)

        #Fetch movie image
        self.fetch_image(movie_img_url, 'Movies')

        #If vod data is valid
        if vod_data:
            #Get movie name from vod_info, otherwise try name from vod_data
            movie_name = vod_info.get('name', vod_data.get('name', 'No name Available...'))

            #If movie name is an empty string
            if not movie_name:
                movie_name = vod_data.get('name', 'No name Available...')

                #Check again if movie name is an empty string
                if not movie_name:
                    movie_name = 'No name Available...'
        else:
            #Get movie name from vod info
            movie_name = vod_info.get('name', 'No name Available...')

        #Set movie info box texts
        self.movies_info_box.name.setText(f"{movie_name}")
        self.movies_info_box.release_date.setText(f"Release date: {vod_info.get('releasedate') or '—'}")
        self.movies_info_box.country.setText(f"Country: {vod_info.get('country') or '—'}")
        self.movies_info_box.genre.setText(f"Genre: {vod_info.get('genre') or '—'}")
        self.movies_info_box.duration.setText(f"Duration: {vod_info.get('duration') or '—'}")
        self.movies_info_box.rating.setText(f"Rating: {vod_info.get('rating') or '—'}")
        self.movies_info_box.director.setText(f"Director: {vod_info.get('director') or '—'}")
        self.movies_info_box.cast.setText(f"Cast: {vod_info.get('actors') or '—'}")
        self.movies_info_box.description.setText(f"Description: {vod_info.get('description') or '—'}")

        #Get youtube trailer code
        yt_code = vod_info.get('youtube_trailer', 0)
        if yt_code:
            self.movies_info_box.yt_code = yt_code

            #Make YouTube button visible
            self.movies_info_box.trailer.setEnabled(True)
        else:
            self.movies_info_box.yt_code = None

            #Make YouTube button invisible
            self.movies_info_box.trailer.setEnabled(False)

        #Get TMDB code
        tmdb_code = vod_info.get('tmdb_id', 0)
        if tmdb_code:
            self.movies_info_box.tmdb_code = tmdb_code

            #Make TMDB button visible
            self.movies_info_box.tmdb.setEnabled(True)
        else:
            self.movies_info_box.tmdb_code = None

            #Make TMDB button invisible
            self.movies_info_box.tmdb.setEnabled(False)

        #Update progress bar
        if not vod_info:
            print(f"VOD info was empty: {vod_info}")
            self.set_progress_bar(100, "Failed loading Movie info", "error")
        else:
            self.set_progress_bar(100, "Loaded Movie info")

    def fetch_series_info(self, series_id, is_show_request):
        series_info_fetcher = SeriesInfoFetcher(self.server, self.username, self.password, series_id, is_show_request, self)
        series_info_fetcher.signals.finished.connect(self.process_series_info)
        series_info_fetcher.signals.error.connect(self.on_fetch_data_error)
        self.threadpool.start(series_info_fetcher)

    def process_series_info(self, series_info_data, is_show_request):
        #If no series info data available
        if not series_info_data:
            self.animate_progress(0, 100, "Failed fetching series info", "error")
            return

        #Check if fetch request came from show_seasons()
        if is_show_request:
            #Clear series list
            self.streaming_list_widgets['Series'].clear()

            #Reset scrollbar position to top
            self.streaming_list_widgets['Series'].scrollToTop()

            #Add go back item
            go_back_item = QListWidgetItem(self.go_back_text)
            go_back_item.setIcon(self.go_back_icon)
            self.streaming_list_widgets['Series'].addItem(go_back_item)

            #Save currently loaded series data for search functionality
            self.currently_loaded_streams['Seasons'] = series_info_data['episodes']

            # Sort season keys numerically when possible — Qt's default text sort
            # would put "Season 10" before "Season 2" (issue #18). The provider
            # returns string keys, so we cast to int when the key is numeric and
            # otherwise fall back to a lexical order at the end of the list.
            def _season_sort_key(k):
                try:
                    return (0, int(k))
                except (TypeError, ValueError):
                    return (1, str(k).lower())

            for season in sorted(series_info_data['episodes'].keys(), key=_season_sort_key):
                #Create season item
                item = QListWidgetItem(f"Season {season}")

                #Set season data to item
                item.setData(Qt.UserRole, series_info_data['episodes'][season])
                # item.setIcon(channel_icon)

                #Add season item to series list
                self.streaming_list_widgets['Series'].addItem(item)

            self.animate_progress(0, 100, "Loading finished")

        #Otherwise request came from single click to show only series info
        else:
            #Get series information data
            series_info = series_info_data['info']

            #Get movie image url
            series_img_url = series_info.get('cover', 0)

            #Fetch Series image
            self.fetch_image(series_img_url, 'Series')

            #Get series name
            series_name = series_info.get('name', 'No name Available...')
            if not series_name:
                #If series name is empty set replacement
                series_name = 'No name Available...'

            # Build the seasons list naturally — `", ".join(...)` avoids the trailing
            # comma the previous code left behind ("Seasons: 1," → "Seasons: 1").
            season_keys = [str(k) for k in series_info_data['episodes'].keys()]
            seasons = ", ".join(season_keys) if season_keys else "—"

            #Get strings from series info
            release_date    = series_info.get('releaseDate')   or "—"
            genre           = series_info.get('genre')         or "—"
            duration        = series_info.get('episode_run_time')
            rating          = series_info.get('rating')
            director        = series_info.get('director')      or "—"
            cast            = series_info.get('cast')          or "—"
            plot            = series_info.get('plot')          or "—"

            #Set series info box texts
            self.series_info_box.name.setText(f"{series_name}")
            self.series_info_box.release_date.setText(f"Release date: {release_date}")
            self.series_info_box.genre.setText(f"Genre: {genre}")
            self.series_info_box.num_seasons.setText(f"Seasons: {seasons}")
            self.series_info_box.duration.setText(
                f"Episode duration: {duration if (duration and str(duration) != '0') else '—'} min"
            )
            self.series_info_box.rating.setText(
                f"Rating: {rating if (rating and str(rating) != '0') else '—'}"
            )
            self.series_info_box.director.setText(f"Director: {director}")
            self.series_info_box.cast.setText(f"Cast: {cast}")
            self.series_info_box.description.setText(f"Description: {plot}")

            #Get youtube trailer code
            yt_code = series_info.get('youtube_trailer', 0)
            if yt_code:
                self.series_info_box.yt_code = yt_code

                #Make YouTube button visible
                self.series_info_box.trailer.setEnabled(True)
            else:
                self.series_info_box.yt_code = None

                #Make YouTube button invisible
                self.series_info_box.trailer.setEnabled(False)

            #Get TMDB code
            tmdb_code = series_info.get('tmdb', 0)
            if tmdb_code:
                self.series_info_box.tmdb_code = tmdb_code

                #Make TMDB button visible
                self.series_info_box.tmdb.setEnabled(True)
            else:
                self.series_info_box.tmdb_code = None

                #Make TMDB button invisible
                self.series_info_box.tmdb.setEnabled(False)

            #Update progress bar
            if not series_info:
                # print(f"Series info was empty: {series_info}")
                self.set_progress_bar(100, "Failed loading Series info", "error")
            else:
                self.set_progress_bar(100, "Loaded Series info")

    def fetch_image(self, img_url, stream_type):
        image_fetcher = ImageFetcher(img_url, stream_type, self)
        image_fetcher.signals.finished.connect(self.process_image_data)
        image_fetcher.signals.error.connect(self.on_fetch_data_error)
        self.threadpool.start(image_fetcher)

    def process_image_data(self, image_data, stream_type):
        try:
            # Construct QPixmap on the GUI thread after the worker returns bytes.
            image = QPixmap()
            image.loadFromData(image_data)
            if image.isNull():
                image = QPixmap(self.path_to_no_img)

            if stream_type == 'Series':
                #Set series image
                self.series_info_box.cover.setPixmap(image.scaledToWidth(self.series_info_box.maxCoverWidth))
            elif stream_type == 'Movies':
                #Set movie image
                self.movies_info_box.cover.setPixmap(image.scaledToWidth(self.movies_info_box.maxCoverWidth))
            elif stream_type == 'Live':
                #Set live tv image
                self.live_info_box.cover.setPixmap(image.scaledToWidth(self.live_info_box.maxCoverHeight))
        except Exception as e:
            print(f"Failed processing image: {e}")

    def favorite_button_pressed(self, stream_type, info_box):
        try:
            #Get current selected item and stream id
            current_sel_item = self.streaming_list_widgets[stream_type].currentItem()

            #Check if an item is selected
            if not current_sel_item:
                #Otherwise return from function
                return

            #Check if inside series navigation
            if self.series_navigation_level != 0 and stream_type == "Series":
                return

            data = current_sel_item.data(Qt.UserRole)

            #Check if item data is valid
            if not data:
                return

            #Check if stream type is series
            if stream_type == "Series":
                stream_id = data.get('series_id', -1)
            else:
                stream_id = data.get('stream_id', -1)

            is_fav = False

            #loop through all streaming entries
            for idx, entry in enumerate(self.entries_per_stream_type[stream_type]):
                #Match to current data streaming id
                if entry['stream_id' if not (stream_type == "Series") else 'series_id'] == stream_id:
                    #Check if item is favorite
                    is_fav = self.entries_per_stream_type[stream_type][idx].get('favorite', False)

                    #toggle favorite
                    is_fav = not is_fav

                    #Set favorite parameter
                    self.entries_per_stream_type[stream_type][idx]['favorite'] = is_fav

            #Change fav button colour
            info_box.set_favorite(is_fav)
            
            #Set favorite parameter
            data['favorite'] = is_fav

            #Set data to currently selected item
            current_sel_item.setData(Qt.UserRole, data)

            set_favorite(self.favorites_file, stream_type, stream_id, is_fav)

            # Only the Favorites view changes here. Other cached category lists keep
            # references to the same entry dictionaries and remain valid.
            stream_cache = self.category_view_cache.get(stream_type, {})
            favorite_keys = [key for key in stream_cache if key[0] == 'favorites']
            for key in favorite_keys:
                stream_cache.pop(key, None)

            item_cache = self.category_item_cache.get(stream_type, {})
            favorite_item_keys = [key for key in item_cache if key[0] == 'favorites']
            for key in favorite_item_keys:
                item_cache.pop(key, None)

            # A Favorites view currently attached to the widget is also stale. Mark
            # it as non-cacheable so switching away does not preserve the old rows.
            active_key = self.active_category_view_key.get(stream_type)
            if active_key and active_key[0] == 'favorites':
                self.active_category_view_key[stream_type] = None

            self._refresh_category_count_labels(stream_type)

        except Exception as e:
            self.animate_progress(0, 100, "Failed adding to favorites", "error")

            print(f"Failed adding to favorites: {e}")

    def _favorites_in_user_order(self, stream_type):
        # Returns the entries in `entries_per_stream_type[stream_type]` whose ids appear
        # in favorites.json, ordered by their position in that file (i.e. by the order
        # in which the user marked them). Falls back to catalog order if the file is
        # missing/corrupt — see issue #17.
        entries = self.entries_per_stream_type.get(stream_type, []) or []
        return entries_in_favorite_order(self.favorites_file, stream_type, entries)

    def _category_view_key(self, stream_type, category_name, category_id=None):
        """Build the cache key shared by prepared entries and Qt list items."""
        sorting_enabled, sort_order = self._sorting_for_category(
            stream_type, category_name, category_id
        )
        preference_key = self._category_sort_preference_key(
            category_name, category_id
        )
        return (preference_key, sorting_enabled, sort_order)

    def _entries_for_category_view(self, stream_type, category_name, category_id=None):
        """Return a cached entry order for one top-level category selection."""
        is_favorites = category_name == self.fav_categories_text
        cache_key = self._category_view_key(
            stream_type, category_name, category_id
        )

        stream_cache = self.category_view_cache[stream_type]
        cached_entries = stream_cache.get(cache_key)
        if cached_entries is not None:
            return cached_entries

        if is_favorites:
            prepared_entries = self._favorites_in_user_order(stream_type)
        elif category_name == self.all_categories_text:
            prepared_entries = self._entries_in_visible_categories(stream_type)
        else:
            prepared_entries = [
                entry for entry in self.entries_per_stream_type[stream_type]
                if entry.get('category_id') == category_id
            ]

        sorting_enabled, sort_order = self._sorting_for_category(
            stream_type, category_name, category_id
        )
        if sorting_enabled:
            prepared_entries.sort(
                key=lambda entry: entry.get('name', '').casefold(),
                reverse=(sort_order == 1)
            )

        stream_cache[cache_key] = prepared_entries
        return prepared_entries

    def category_item_clicked(self, clicked_item):
        try:
            sender = self.sender()
            stream_type = {
                self.category_list_live: 'LIVE',
                self.category_list_movies: 'Movies',
                self.category_list_series: 'Series'
            }.get(sender)

            if not stream_type:
                return

            selected_item = sender.currentItem()
            if not selected_item:
                return

            #Check if the item is already selected
            if selected_item == self.prev_clicked_category_item[stream_type]:
                return

            #Save to previous clicked
            self.prev_clicked_category_item[stream_type] = selected_item

            selected_item_data = selected_item.data(Qt.UserRole) or {}
            selected_item_text = selected_item_data.get(
                'category_name', selected_item.text()
            )

            #Check if All and Favorites category are not selected
            if (selected_item_text != self.all_categories_text and selected_item_text != self.fav_categories_text):
                category_id = selected_item_data['category_id']

            self.set_progress_bar(0, "Loading items")

            was_nested_series_view = (
                stream_type == 'Series' and self.series_navigation_level != 0
            )
            if stream_type == 'Series':
                # A category selection always starts at the series-list root.
                self.series_navigation_level = 0
                self.prev_double_clicked_streaming_item = 0

            is_favorites_view = (selected_item_text == self.fav_categories_text)

            prepared_entries = self._entries_for_category_view(
                stream_type,
                selected_item_text,
                None if is_favorites_view or selected_item_text == self.all_categories_text else category_id
            )
            self.currently_loaded_streams[stream_type] = list(prepared_entries)

            list_widget = self.streaming_list_widgets[stream_type]
            target_view_key = self._category_view_key(
                stream_type, selected_item_text,
                None if is_favorites_view or selected_item_text == self.all_categories_text else category_id
            )
            # The list now represents a different category. Update the search bar's
            # visual sorting state as well, otherwise its menu keeps the last action
            # clicked in the previous category even though the new order is correct.
            self.streaming_search_bars[stream_type].current_sorting = (
                target_view_key[1], target_view_key[2]
            )
            list_widget.setSortingEnabled(False)
            list_widget.setUpdatesEnabled(False)
            try:
                active_view_key = self.active_category_view_key.get(stream_type)
                search_is_empty = not self.streaming_search_bars[stream_type].text()
                if (
                    active_view_key is not None
                    and search_is_empty
                    and not was_nested_series_view
                ):
                    # Detach from the end so row removal stays O(n), then restore the
                    # original order before storing the reusable item objects.
                    detached_items = [
                        list_widget.takeItem(row)
                        for row in range(list_widget.count() - 1, -1, -1)
                    ]
                    detached_items.reverse()
                    self.category_item_cache[stream_type][active_view_key] = detached_items
                else:
                    # Search results and nested Series rows must never replace a
                    # complete cached category root view.
                    list_widget.clear()

                cached_items = self.category_item_cache[stream_type].pop(
                    target_view_key, None
                )
                if cached_items is not None:
                    for item in cached_items:
                        list_widget.addItem(item)
                else:
                    # Let Qt create all text rows in one native batch. Assigning the
                    # dictionaries afterwards retains the existing click handlers.
                    list_widget.addItems([
                        entry.get('name', '') for entry in prepared_entries
                    ])
                    for row, entry in enumerate(prepared_entries):
                        list_widget.item(row).setData(Qt.UserRole, entry)

                    if not prepared_entries:
                        list_widget.addItem("No items in list...")

                self.active_category_view_key[stream_type] = target_view_key
            finally:
                list_widget.setUpdatesEnabled(True)
                list_widget.viewport().update()

            # Reset the viewport only after the batch has been installed.
            list_widget.scrollToTop()

            #Check if list is empty after process
            self.set_progress_bar(100, "Loading finished")

        except Exception as e:
            print(f"Failed: {e}")

    def start_online_worker(self, stream_id, url):
        # Bail out early if the user disabled the traffic-light check.
        if not getattr(self, 'stream_status_enabled', True):
            return

        # Run the stream-status probe on the dedicated pool — see issue #74.
        online_worker = OnlineWorker(stream_id, url, self)
        online_worker.signals.finished.connect(self.process_stream_status)
        online_worker.signals.error.connect(self.on_stream_status_error)
        self.status_threadpool.start(online_worker)

    def on_stream_status_error(self, error_msg):
        print(f"Failed processing streaming status: {error_msg}")

        #Set stream status to unknown
        self.live_info_box.stream_status.setPixmap(
            self.status_pixmap(self.path_to_unknown_status_icon, 24)
        )

    def process_stream_status(self, stream_id, stream_status):
        try:
            #Ensure user hasn't changed live channel before request came through
            last_clicked_item = self.prev_clicked_streaming_item.data(Qt.UserRole)
            if (stream_id != last_clicked_item['stream_id']):
                return

            if (stream_status == "True"):
                self.live_info_box.stream_status.setPixmap(
                    self.status_pixmap(self.path_to_online_status_icon, 24)
                )
            elif (stream_status == "Maybe"):
                self.live_info_box.stream_status.setPixmap(
                    self.status_pixmap(self.path_to_maybe_status_icon, 24)
                )
            else:
                self.live_info_box.stream_status.setPixmap(
                    self.status_pixmap(self.path_to_offline_status_icon, 24)
                )
        except Exception as e:
            print(f"Failed processing streaming status: {e}")

    def start_epg_worker(self, stream_id):
        #Create EPG thread worker that will fetch EPG data
        epg_worker = EPGWorker(self.server, self.username, self.password, stream_id, self)

        #Connect functions to signals
        epg_worker.signals.finished.connect(self.process_epg_data)
        epg_worker.signals.error.connect(self.on_epg_fetch_error)

        #Start EPG thread
        self.threadpool.start(epg_worker)

    def on_epg_fetch_error(self, error_msg):
        print(f"Failed fetching EPG data: {error_msg}")
        self.set_progress_bar(100, "Failed loading EPG data", "error")

        #Set list view
        item = QTreeWidgetItem(["--/--/----", "--:--", "--:--", "Failed loading EPG data..."])
        self.live_info_box.live_EPG_info.addTopLevelItem(item)

    def process_epg_data(self, epg_data):
        try:
            #Clear EPG data
            self.live_info_box.live_EPG_info.clear()

            #Check if EPG data is empty
            if not epg_data:
                item = QTreeWidgetItem(["--/--/----", "--:--", "--:--", "No EPG Data Available..."])

                self.live_info_box.live_EPG_info.addTopLevelItem(item)

                self.set_progress_bar(100, "No EPG data")
                return

            #Get current time
            current_timestamp = time.mktime(datetime.now().timetuple())

            items = []

            #Loop through EPG data
            for epg_entry in epg_data:
                #Get EPG data
                start_timestamp = epg_entry['start_time']
                stop_timestamp  = epg_entry['stop_time']
                program_name    = epg_entry['program_name']
                description     = epg_entry['description']
                date            = epg_entry['date']

                #Convert timestamps to string in correct format
                start_time = start_timestamp.strftime("%H:%M")
                stop_time = stop_timestamp.strftime("%H:%M")

                #Convert stop time to unix timebase so it can be used for calculating
                unix_stop_time = time.mktime(stop_timestamp.timetuple())

                #Compute time difference
                time_diff = unix_stop_time - current_timestamp

                if time_diff >= 0:
                    #Create EPG item
                    item    = QTreeWidgetItem([date, start_time, stop_time, program_name])
                    label   = QLabel(description)
                    label.setWordWrap(True)
                    desc    = QTreeWidgetItem()
                    item.addChild(desc)

                    #Add label widget to description. This way it is word wrapped correctly
                    self.live_info_box.live_EPG_info.setItemWidget(desc, 3, label)

                    #Append item to list
                    items.append(item)

            #Add all items to EPG treeview
            self.live_info_box.live_EPG_info.addTopLevelItems(items)

            #Update progress bar
            self.set_progress_bar(100, "Loaded EPG data")

        except Exception as e:
            print(f"Failed processing EPG: {e}")
            self.set_progress_bar(100, "Failed processing EPG data", "error")

    def streaming_item_clicked(self, clicked_item):
        try:
            # print("single clicked")

            #Check if clicked item is valid
            if not clicked_item:
                return

            #Check if clicked item is already selected
            if (clicked_item == self.prev_clicked_streaming_item):
                return

            #Save to previous item
            self.prev_clicked_streaming_item = clicked_item

            #Get clicked item data
            clicked_item_data = clicked_item.data(Qt.UserRole)

            # Season rows contain episode lists rather than stream dictionaries.
            # They have no top-level metadata to display on a single click.
            if not isinstance(clicked_item_data, dict):
                return

            #Get if clicked item is favorite
            is_fav = clicked_item_data.get('favorite', False)

            stream_type = clicked_item_data.get('stream_type', '')

            #Skip when back button or already loaded series info
            if clicked_item.text() == self.go_back_text or ('series' in stream_type and self.series_navigation_level > 0):
                return

            #Show EPG data if live tv clicked
            if 'live' in stream_type:
                self.set_progress_bar(0, "Loading EPG data")

                #Set favorite button according to favorite value
                self.live_info_box.set_favorite(is_fav)

                #Set TV channel name in info window
                self.live_info_box.EPG_box_label.setText(f"{clicked_item_data['name']}")

                #Clear Stream Status indicator
                self.live_info_box.stream_status.setPixmap(
                    self.status_pixmap(self.path_to_unknown_status_icon, 25)
                )

                #Clear EPG data
                self.live_info_box.live_EPG_info.clear()
                item = QTreeWidgetItem(["...", "...", "...", "Loading EPG Data..."])
                self.live_info_box.live_EPG_info.addTopLevelItem(item)

                #Fetch cover image
                self.fetch_image(clicked_item_data['stream_icon'], 'Live')

                # Fetch stream status
                self.start_online_worker(clicked_item_data['stream_id'], clicked_item_data['url'])

                #Fetch EPG data
                self.start_epg_worker(clicked_item_data['stream_id'])

            #Show movie info if movie clicked
            elif 'movie' in stream_type:
                self.set_progress_bar(0, "Loading Movie info")

                #Set favorite button according to favorite value
                self.movies_info_box.set_favorite(is_fav)

                #Set loading image
                self.movies_info_box.cover.setPixmap(QPixmap(self.path_to_loading_img).scaledToWidth(self.series_info_box.maxCoverWidth))

                #Set movie info box texts
                self.movies_info_box.name.setText(f"{clicked_item_data['name']}")
                self.movies_info_box.release_date.setText(f"Release date: ...")
                self.movies_info_box.country.setText(f"Country: ...")
                self.movies_info_box.genre.setText(f"Genre: ...")
                self.movies_info_box.duration.setText(f"Duration: ...")
                self.movies_info_box.rating.setText(f"Rating: ...")
                self.movies_info_box.director.setText(f"Director: ...")
                self.movies_info_box.cast.setText(f"Cast: ...")
                self.movies_info_box.description.setText(f"Description: ...")

                #Reset YouTube and TMDB codes
                self.movies_info_box.yt_code = None
                self.movies_info_box.tmdb_code = None

                #Make YouTube and TMDB buttons invisible
                self.movies_info_box.trailer.setEnabled(False)
                self.movies_info_box.tmdb.setEnabled(False)

                #Get vod info and vod data
                self.fetch_vod_info(clicked_item_data['stream_id'])

            #Show series info if series clicked
            elif 'series' in stream_type:
                #Check if not at navigation top level
                if (self.series_navigation_level != 0):
                    return

                self.set_progress_bar(0, "Loading Series info")

                #Set favorite button according to favorite value
                self.series_info_box.set_favorite(is_fav)

                #Set loading image
                self.series_info_box.cover.setPixmap(QPixmap(self.path_to_loading_img).scaledToWidth(self.series_info_box.maxCoverWidth))

                #Set series info box texts
                self.series_info_box.name.setText(f"{clicked_item_data['name']}")
                self.series_info_box.release_date.setText(f"Release date: ...")
                self.series_info_box.genre.setText(f"Genre: ...")
                self.series_info_box.num_seasons.setText(f"Seasons: ...")
                self.series_info_box.duration.setText(f"Episode duration: ... min")
                self.series_info_box.rating.setText(f"Rating: ...")
                self.series_info_box.director.setText(f"Director: ...")
                self.series_info_box.cast.setText(f"Cast: ...")
                self.series_info_box.description.setText(f"Description: ...")

                #Reset YouTube and TMDB codes
                self.series_info_box.yt_code = None
                self.series_info_box.tmdb_code = None

                #Make YouTube and TMDB buttons invisible
                self.series_info_box.trailer.setEnabled(False)
                self.series_info_box.tmdb.setEnabled(False)

                #Fetch series info data
                self.fetch_series_info(clicked_item_data['series_id'], False)

        except Exception as e:
            print(f"Failed item single click: {e}")

    def streaming_item_double_clicked(self, clicked_item):
        try:
            # print("Double clicked")

            #Check if clicked item is valid
            if not clicked_item:
                return

            #Get clicked item data
            clicked_item_text = clicked_item.text()
            clicked_item_data = clicked_item.data(Qt.UserRole)

            #Check if item data is valid and not go back item
            if not clicked_item_data and clicked_item_text != self.go_back_text:
                return

            #Try to get stream type from item data
            try:
                stream_type = clicked_item_data['stream_type']
            except:
                stream_type = ''

            #Prevent loading the same series navigation levels multiple times
            if 'series' in stream_type and self.series_navigation_level < 2 and clicked_item == self.prev_double_clicked_streaming_item:
                return

            print(f"stream_type: {stream_type}")

            #Save to previous double clicked item
            self.prev_double_clicked_streaming_item = clicked_item

            #Have different action depending on the navigation level
            match self.series_navigation_level:
                case 0: #Highest level, either LIVE, VOD or series
                    if clicked_item_text == self.go_back_text:
                        return

                    if 'live' in stream_type or 'movie' in stream_type:
                        self.play_item(clicked_item_data['url'])

                    elif 'series' in stream_type:
                        self.series_navigation_level = 1
                        self.show_seasons(clicked_item_data)

                case 1: #Series seasons
                    if clicked_item_text == self.go_back_text:
                        self.series_navigation_level = 0
                        self.go_back_to_level(self.series_navigation_level)
                        
                    else:
                        self.series_navigation_level = 2
                        self.show_episodes(clicked_item_data)

                case 2: #Series episodes
                    if clicked_item_text == self.go_back_text:
                        self.series_navigation_level = 1
                        self.go_back_to_level(self.series_navigation_level)
                        
                    else:
                        #Play episode
                        self.play_item(clicked_item_data['url'])

        except Exception as e:
            print(f"failed item double click: {e}")

    def streaming_item_keyboard_activated(self, item):
        """Apply the normal selection work, then open or play the chosen entry."""
        self.streaming_item_clicked(item)
        self.streaming_item_double_clicked(item)

    def go_back_to_level(self, series_navigation_level):
        self.set_progress_bar(0, "Loading items")

        #Clear series list widget
        self.streaming_list_widgets['Series'].clear()

        #Reset scrollbar position to top
        self.streaming_list_widgets['Series'].scrollToTop()

        if series_navigation_level == 0:    #From seasons back to series list
            for entry in self.currently_loaded_streams['Series']:
                item = QListWidgetItem(entry['name'])
                item.setData(Qt.UserRole, entry)

                self.streaming_list_widgets['Series'].addItem(item)

        elif series_navigation_level == 1:  #From episodes back to seasons list
            #Add go back item
            go_back_item = QListWidgetItem(self.go_back_text)
            go_back_item.setIcon(self.go_back_icon)
            self.streaming_list_widgets['Series'].addItem(go_back_item)

            # Same natural ordering as the initial season list (issue #18).
            def _season_sort_key(k):
                try:
                    return (0, int(k))
                except (TypeError, ValueError):
                    return (1, str(k).lower())

            for season in sorted(self.currently_loaded_streams['Seasons'].keys(), key=_season_sort_key):
                item = QListWidgetItem(f"Season {season}")
                item.setData(Qt.UserRole, self.currently_loaded_streams['Seasons'][season])

                self.streaming_list_widgets['Series'].addItem(item)

        self.animate_progress(0, 100, "Loading finished")

    def show_seasons(self, seasons_data):
        self.set_progress_bar(0, "Loading items")

        #Fetch series info data
        self.fetch_series_info(seasons_data['series_id'], True)

    def show_episodes(self, episodes_data):
        self.set_progress_bar(0, "Loading items")

        #Clear series list
        self.streaming_list_widgets['Series'].clear()

        #Reset scrollbar position to top
        self.streaming_list_widgets['Series'].scrollToTop()

        #Add go back item
        go_back_item = QListWidgetItem(self.go_back_text)
        go_back_item.setIcon(self.go_back_icon)
        self.streaming_list_widgets['Series'].addItem(go_back_item)

        #Clear episodes list so it can be filled again
        self.currently_loaded_streams['Episodes'].clear()

        #Show episodes in list
        for episode in episodes_data:
            #Create episode item
            item = QListWidgetItem(f"{episode['title']}")

            #Make playable url
            container_extension = episode['container_extension']
            episode_id          = episode['id']

            fmt = self.series_url_format
            # If the format does not include the container extension placeholder, skip it
            if ".{container_extension}" not in fmt:
                container_extension = ""
                # Optionally remove any trailing dot left in format
                fmt = fmt.replace(".{container_extension}", "")
                
            # Construct the URL
            playable_url = fmt.format(
                server=self.server,
                username=self.username,
                password=self.password,
                stream_id=episode_id,
                container_extension=container_extension
            )
            # playable_url = f"{self.server}/series/{self.username}/{self.password}/{episode_id}.{container_extension}"

            #Add new 'url' key to episode data
            episode['url'] = playable_url

            #Set data to the episode item
            item.setData(Qt.UserRole, episode)

            #Append episode data to the currently loaded list for search functionality
            self.currently_loaded_streams['Episodes'].append(episode)

            #Add episode item to series list
            self.streaming_list_widgets['Series'].addItem(item)

        self.animate_progress(0, 100, "Loading finished")

    def play_item(self, url):
        if not url:
            self.animate_progress(0, 100, "Stream URL not found", "error")

            #Create warning message box to indicate error
            error_dialog = QMessageBox()
            error_dialog.setIcon(QMessageBox.Warning)
            error_dialog.setWindowTitle("Invalid stream URL")
            error_dialog.setText(f"Invalid stream URL!\nPlease try again.\n\nURL: {url}")

            #Set only OK button
            error_dialog.setStandardButtons(QMessageBox.Ok)

            #Show error dialog
            error_dialog.exec_()
            return

        if self.external_player_command:
            try:
                print(f"Going to play: {private_url_log_reference(url)}")
                self.animate_progress(0, 100, "Loading player for streaming")

                # Embedded VLC marker — short-circuit before constructing any subprocess
                # command. The marker is set when the user picks "Embedded VLC" in
                # Settings (so we don't store a real path that could be invoked by accident).
                if self.external_player_command == "<embedded-vlc>":
                    self._play_embedded(url)
                    return

                launch_external_player(
                    self.external_player_command,
                    url,
                    user_agent=self.current_user_agent,
                )

            except ExternalPlayerNotExecutableError:
                self.animate_progress(
                    0, 100, "Selected player is not executable", "error"
                )
            except Exception as e:
                import traceback
                self.animate_progress(0, 100, "Failed playing stream", "error")
                print(
                    "Failed playing stream "
                    f"[{private_url_log_reference(url)}]: {e}"
                )
                traceback.print_exc()
                try:
                    error_dialog = QMessageBox(self)
                    error_dialog.setIcon(QMessageBox.Warning)
                    error_dialog.setWindowTitle("Player failed to launch")
                    error_dialog.setText(
                        f"Could not launch the external player.\n\n"
                        f"Player: {self.external_player_command}\n"
                        f"Error: {e}\n\n"
                        f"See {path.join(writable_data_directory(), 'log.txt')} "
                        f"for the full traceback."
                    )
                    error_dialog.setStandardButtons(QMessageBox.Ok)
                    error_dialog.exec_()
                except Exception:
                    pass
        else:
            self.set_progress_bar(100, "No media player configured", "error")
            #Create warning message box to indicate error
            error_dialog = QMessageBox()
            error_dialog.setIcon(QMessageBox.Warning)
            error_dialog.setWindowTitle("No Media Player")
            error_dialog.setText("No media player configured!\nPlease configure a media player.")

            #Set only OK button
            error_dialog.setStandardButtons(QMessageBox.Ok)

            #Show error dialog
            error_dialog.exec_()

    def choose_external_player(self):
        #Open file dialog box in order to select media player program
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.ExistingFile)

        if sys.platform.startswith('win'):
            file_dialog.setNameFilter("Executable files (*.exe *.bat, *.com)")
        else:
            file_dialog.setNameFilter("Executable files (*)")

        file_dialog.setWindowTitle("Select External Media Player")

        if file_dialog.exec_():
            file_paths = file_dialog.selectedFiles()

            if len(file_paths) > 0:
                self.external_player_command = file_paths[0]
                self.last_external_player_command = self.external_player_command

                self.save_external_player_command()
                self._refresh_current_player_label()

                self.animate_progress(0, 100, "Selected external media player")
                return True

        # Keep the previously active mode when the file dialog is cancelled.
        self._refresh_current_player_label()
        return False

    def use_external_player(self, checked):
        """Activate the remembered external player or ask for one when absent."""
        if not checked:
            return

        remembered_command = getattr(self, "last_external_player_command", "") or ""
        if remembered_command:
            self.external_player_command = remembered_command
            self.save_external_player_command()
            self._refresh_current_player_label()
            self.animate_progress(0, 100, "External media player enabled")
            return

        # Selecting External player without a remembered executable immediately opens
        # the chooser. Cancelling restores the mode represented by the active command.
        self.choose_external_player()

    def use_embedded_player(self):
        # User clicked "Use Internal Player (VLC)". Check libvlc is reachable BEFORE
        # we persist the choice — otherwise the user gets a silent failure later
        # when they try to play something.
        if not EmbeddedPlayerWindow.is_available():
            self.set_progress_bar(100, "Internal VLC player unavailable", "error")
            fallback_command = (
                getattr(self, "last_external_player_command", "") or ""
            )
            self.external_player_command = fallback_command
            self.save_external_player_command()
            self._refresh_current_player_label()
            self._show_internal_vlc_unavailable(fallback_command)
            return

        self.external_player_command = "<embedded-vlc>"
        self.save_external_player_command()
        self._refresh_current_player_label()
        self.animate_progress(0, 100, "Internal VLC player enabled")

    def _show_internal_vlc_unavailable(self, fallback_command=""):
        """Explain the VLC requirement and any automatic external fallback."""
        if fallback_command:
            fallback_message = (
                "IPTV Player has switched to your previously selected external "
                "media player."
            )
        else:
            fallback_message = (
                "No external media player has been selected yet. Select External "
                "player in Settings and choose an installed media player."
            )

        error_dialog = QMessageBox(self)
        error_dialog.setIcon(QMessageBox.Warning)
        error_dialog.setWindowTitle("Internal VLC unavailable")
        error_dialog.setText(
            "Internal VLC requires a compatible VLC installation on this "
            "computer, but VLC could not be found.\n\n"
            "Install the latest VLC version from https://www.videolan.org/vlc/, "
            "restart IPTV Player, and try again.\n\n"
            f"{fallback_message}"
        )
        error_dialog.setStandardButtons(QMessageBox.Ok)
        error_dialog.exec_()

    def _refresh_current_player_label(self):
        if not hasattr(self, "current_player_label"):
            return
        cmd = getattr(self, "external_player_command", "") or ""

        # Updating the radio buttons from persisted state must not trigger their
        # activation handlers and reopen the external-player chooser at startup.
        self.internal_player_radio.blockSignals(True)
        self.external_player_radio.blockSignals(True)
        if cmd == "<embedded-vlc>":
            self.current_player_label.setText(
                "Active player: Internal VLC (using the installed VLC engine)"
            )
            self.internal_player_radio.setChecked(True)
            self.external_player_radio.setChecked(False)
        elif cmd:
            self.current_player_label.setText(f"Active player: {cmd}")
            self.internal_player_radio.setChecked(False)
            self.external_player_radio.setChecked(True)
        else:
            self.current_player_label.setText("No player selected")
            self.internal_player_radio.setChecked(False)
            self.external_player_radio.setChecked(False)
        self.internal_player_radio.blockSignals(False)
        self.external_player_radio.blockSignals(False)

        remembered_command = getattr(self, "last_external_player_command", "") or ""
        self.external_player_path.setText(remembered_command)
        external_mode = self.external_player_radio.isChecked()
        self.external_player_path.setEnabled(external_mode)
        self.choose_player_button.setEnabled(external_mode)
        self.internal_player_settings_button.setEnabled(
            self.internal_player_radio.isChecked()
        )

    def _play_embedded(self, url):
        try:
            playlist, current_idx, title = self._collect_visible_playlist(url)
            self._ensure_embedded_player_process()
            self._embedded_player_command_queue.put({
                'command': 'play',
                'url': url,
                'title': title,
                'playlist': playlist,
                'index': current_idx
            })
            self.animate_progress(0, 100, "Playing in internal player")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.animate_progress(0, 100, "Failed playing stream", "error")
            print(
                "Embedded play failed "
                f"[{private_url_log_reference(url)}]: {e}"
            )

    def _ensure_embedded_player_process(self):
        """Start the isolated player process and its private command channel."""
        if (
            self._embedded_player_process is not None
            and self._embedded_player_process.poll() is None
            and self._embedded_player_command_queue is not None
        ):
            return

        self._close_embedded_player_listener()
        auth_key = os.urandom(32)
        if is_windows:
            family = 'AF_PIPE'
            address = rf'\\.\pipe\iptv-player-{uuid.uuid4().hex}'
        else:
            import tempfile
            family = 'AF_UNIX'
            address = path.join(
                tempfile.gettempdir(), f'iptv-player-{uuid.uuid4().hex}.sock'
            )

        listener = Listener(address=address, family=family, authkey=auth_key)
        environment = os.environ.copy()
        environment['IPTV_PLAYER_IPC_ADDRESS'] = address
        environment['IPTV_PLAYER_IPC_FAMILY'] = family
        environment['IPTV_PLAYER_IPC_AUTH'] = auth_key.hex()
        environment['IPTV_PLAYER_USER_AGENT'] = self.current_user_agent or ''
        environment['IPTV_PLAYER_THEME'] = self.theme_select_box.currentText()
        environment['IPTV_PLAYER_SEEK_STEP'] = str(self.internal_seek_step_seconds)
        environment['IPTV_PLAYER_VOLUME_STEP'] = str(self.internal_volume_step_percent)
        environment['IPTV_PLAYER_SPEED_STEP'] = str(self.internal_speed_step)
        environment['IPTV_PLAYER_AUDIO_LANGUAGE'] = self.internal_audio_language
        environment['IPTV_PLAYER_SUBTITLE_LANGUAGE'] = self.internal_subtitle_language
        environment['IPTV_PLAYER_SETTINGS_FILE'] = path.abspath(self.user_data_file)

        if getattr(sys, 'frozen', False):
            # Tell recent PyInstaller bootloaders that this is a new application
            # instance, rather than one of their own internal worker processes.
            environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
            command = [sys.executable, '--embedded-player-process']
        else:
            command = [sys.executable, path.abspath(__file__), '--embedded-player-process']

        creation_flags = subprocess.CREATE_NO_WINDOW if is_windows else 0
        try:
            process = subprocess.Popen(
                command,
                env=environment,
                creationflags=creation_flags
            )
        except Exception:
            listener.close()
            raise

        command_queue = queue.Queue()
        self._embedded_player_process = process
        self._embedded_player_listener = listener
        self._embedded_player_command_queue = command_queue

        def send_commands():
            connection = None
            try:
                connection = listener.accept()
                while True:
                    payload = command_queue.get()
                    if payload is None:
                        break
                    connection.send(payload)
            except (EOFError, OSError, BrokenPipeError) as error:
                print(f"Internal player command channel closed: {error}")
            finally:
                if connection is not None:
                    connection.close()
                listener.close()

        self._embedded_player_sender_thread = threading.Thread(
            target=send_commands,
            name='EmbeddedPlayerCommandSender',
            daemon=True
        )
        self._embedded_player_sender_thread.start()

    def _close_embedded_player_listener(self):
        """Close resources left by an earlier isolated player instance."""
        if self._embedded_player_listener is not None:
            try:
                self._embedded_player_listener.close()
            except OSError:
                pass
        self._embedded_player_listener = None
        self._embedded_player_command_queue = None

    def _stop_embedded_player_process(self):
        """Stop the isolated player when the main application exits."""
        if self._embedded_player_command_queue is not None:
            self._embedded_player_command_queue.put({'command': 'quit'})
            self._embedded_player_command_queue.put(None)
        process = self._embedded_player_process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        self._embedded_player_process = None
        self._close_embedded_player_listener()

    def _collect_visible_playlist(self, url):
        # Build the player's sidebar list from what's CURRENTLY VISIBLE in the main
        # window — i.e. iterate the actual QListWidget the user just clicked from,
        # not the cached `currently_loaded_streams` array. For Series in episode
        # mode (navigation level 2) that means the list shows episodes of the open
        # season; for movies it's the open category; for LIVE it's the open category.
        try:
            current_tab_idx = self.tab_widget.currentIndex()
            tab_name = self.tab_widget.tabText(current_tab_idx)
            stream_type = {'LIVE': 'LIVE', 'Movies': 'Movies', 'Series': 'Series'}.get(tab_name, 'LIVE')

            list_widget = self.streaming_list_widgets.get(stream_type)
            playlist = []
            current_idx = 0
            title = ""

            if list_widget is not None:
                for i in range(list_widget.count()):
                    item = list_widget.item(i)
                    if item is None:
                        continue
                    text = item.text()
                    # Skip the "Go back" row and any placeholder rows that have no data.
                    if text == self.go_back_text or text == "No items in list..." or text == "No search results found...":
                        continue
                    data = item.data(Qt.UserRole)
                    if not isinstance(data, dict):
                        continue
                    u = data.get('url')
                    name = data.get('name') or data.get('title') or text
                    if not u:
                        # Series-level rows (no URL) — drop them so Next/Prev only walks playable items.
                        continue
                    playlist.append({'name': name, 'url': u})
                    if u == url:
                        current_idx = len(playlist) - 1
                        title = name

            if not playlist:
                sel = self.streaming_list_widgets[stream_type].currentItem() if list_widget else None
                title = sel.text() if sel else ""
                playlist = [{'name': title or url, 'url': url}]
                current_idx = 0

            return playlist, current_idx, title
        except Exception as e:
            print(f"Could not build embedded playlist: {e}")
            return [{'name': url, 'url': url}], 0, ""

    def search_bar_key_pressed(self, e, search_bar, list_content_type, stream_type, list_widgets, history_list, history_list_idx):
        search_history_size = len(history_list)
        text = search_bar.text()

        match e.key():
            case Qt.Key_Return:
                # list_widgets[stream_type].clear()
                
                history_list_idx[0] = 0

                if text:
                    history_list.insert(0, text)

                    if search_history_size >= self.max_search_history_size:
                        history_list.pop(-1)

                self.search_in_list(list_content_type, stream_type, text)

            case Qt.Key_Up:
                #Check if list is empty
                if not history_list:
                    return

                history_list_idx[0] += 1
                if history_list_idx[0] >= search_history_size:
                    history_list_idx[0] = search_history_size - 1

                search_bar.setText(history_list[history_list_idx[0]])

            case Qt.Key_Down:
                #Check if list is empty
                if not history_list:
                    return

                history_list_idx[0] -= 1
                if history_list_idx[0] < 0:
                    history_list_idx[0] = -1
                    search_bar.clear()
                else:
                    search_bar.setText(history_list[history_list_idx[0]])

            case Qt.Key_Left:
                search_bar.cursorBackward(False, 1)

            case Qt.Key_Right:
                search_bar.cursorForward(False, 1)

            case Qt.Key_Backspace:
                search_bar.backspace()

            case Qt.Key_Delete:
                if search_bar.cursorPosition() < len(text):
                    search_bar.cursorForward(False, 1)
                    search_bar.backspace()

            case Qt.Key_Home:
                if search_bar.cursorPosition() != 0:
                    search_bar.setCursorPosition(0)

            case Qt.Key_End:
                if search_bar.cursorPosition() != len(text):
                    search_bar.setCursorPosition(len(text))

            case _:
                search_bar.insert(e.text())
                # e.accept()

    def search_in_list(self, list_content_type, stream_type, text):
        try:
            self.set_progress_bar(0, f"Loading search results...")
            # Every normalized query word must occur somewhere in the candidate.
            # Substring matching intentionally allows partial words without adding
            # fuzzy-search complexity or unpredictable similarity thresholds.
            search_terms = normalize_search_text(text).split()

            #If searching in category list
            if list_content_type == 'category':
                list_widget = self.category_list_widgets[stream_type]
                matching_entries = [
                    entry for entry in self.currently_loaded_categories[stream_type]
                    if title_matches_search(
                        entry.get('category_name', ''), search_terms
                    )
                ]
                category_list_enabled, category_list_order = (
                    self._sorting_for_category_list(stream_type)
                )
                matching_entries = ordered_catalog_entries(
                    matching_entries,
                    category_list_enabled,
                    descending=(category_list_order == 1),
                    title_key='category_name',
                )
                matching_entries.sort(
                    key=lambda entry: search_relevance_key(
                        entry.get('category_name', ''), search_terms
                    )
                )

                # Build the final order once. Keeping Qt automatic sorting enabled
                # while inserting thousands of matches causes repeated O(n log n)
                # work and can make the interface appear frozen.
                list_widget.setSortingEnabled(False)
                list_widget.setUpdatesEnabled(False)
                try:
                    list_widget.clear()
                    for entry in matching_entries:
                        item = self._new_category_item(stream_type, entry)
                        list_widget.addItem(item)

                    #if search bar is empty
                    if not search_terms:
                        # Add 'All' and 'Favorites' categories to top
                        itemAll = self._new_category_item(
                            stream_type, {'category_name': self.all_categories_text}
                        )
                        list_widget.insertItem(0, itemAll)

                        itemFav = self._new_category_item(
                            stream_type, {'category_name': self.fav_categories_text}
                        )
                        list_widget.insertItem(1, itemFav)

                    #Check if no search results found
                    if not list_widget.count():
                        list_widget.addItem("No search results found...")
                finally:
                    list_widget.setUpdatesEnabled(True)
                    list_widget.viewport().update()

            #If searching in streaming content list
            elif list_content_type == 'streaming':
                #Check if list is empty
                if not self.currently_loaded_streams[stream_type]:
                    return

                list_widget = self.streaming_list_widgets[stream_type]
                list_widget.setSortingEnabled(False)
                list_widget.setUpdatesEnabled(False)
                try:
                    list_widget.clear()
                    navigation_level = (
                        self.series_navigation_level if stream_type == 'Series' else 0
                    )

                    match navigation_level:
                        case 0: #LIVE/VOD/Series
                            matching_entries = [
                                entry for entry in self.currently_loaded_streams[stream_type]
                                if title_matches_search(
                                    entry.get('name', ''), search_terms
                                )
                            ]
                            matching_entries = ordered_catalog_entries(
                                matching_entries,
                                self.sorting_enabled,
                                descending=(self.sorting_order == 1),
                            )
                            matching_entries.sort(
                                key=lambda entry: search_relevance_key(
                                    entry.get('name', ''), search_terms
                                )
                            )
                            for entry in matching_entries:
                                item = QListWidgetItem(entry['name'])
                                item.setData(Qt.UserRole, entry)
                                list_widget.addItem(item)
                        case 1: #Seasons
                            list_widget.addItem(self.go_back_text)

                            seasons = [
                                season for season in self.currently_loaded_streams['Seasons']
                                if title_matches_search(
                                    f"season {season}", search_terms
                                )
                            ]
                            if self.sorting_enabled:
                                seasons = ordered_season_keys(
                                    seasons,
                                    descending=(self.sorting_order == 1),
                                )
                            seasons.sort(
                                key=lambda season: search_relevance_key(
                                    f"season {season}", search_terms
                                )
                            )
                            for season in seasons:
                                item = QListWidgetItem(f"Season {season}")
                                item.setData(Qt.UserRole, self.currently_loaded_streams['Seasons'][season])
                                list_widget.addItem(item)
                        case 2: #Episodes
                            list_widget.addItem(self.go_back_text)
                            matching_episodes = [
                                episode for episode in self.currently_loaded_streams['Episodes']
                                if title_matches_search(
                                    episode.get('title', ''), search_terms
                                )
                            ]
                            matching_episodes = ordered_catalog_entries(
                                matching_episodes,
                                self.sorting_enabled,
                                descending=(self.sorting_order == 1),
                                title_key='title',
                            )
                            matching_episodes.sort(
                                key=lambda episode: search_relevance_key(
                                    episode.get('title', ''), search_terms
                                )
                            )
                            for episode in matching_episodes:
                                item = QListWidgetItem(episode['title'])
                                item.setData(Qt.UserRole, episode)
                                list_widget.addItem(item)

                    #Check if no search results found
                    num_of_items = list_widget.count()
                    if not (num_of_items - (navigation_level > 0)):
                        list_widget.addItem("No search results found...")
                finally:
                    list_widget.setUpdatesEnabled(True)
                    list_widget.viewport().update()

            self.set_progress_bar(100, f"Loaded search results")
        except Exception as e:
            print(f"search in list failed: {e}")

    def load_external_player_command(self):
        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError):
            config = configparser.ConfigParser()

        if config.has_option('ExternalPlayer', 'Command'):
            command = config['ExternalPlayer'].get('Command', '')
            remembered_command = config['ExternalPlayer'].get('LastExternalCommand', '')
            if command and command != "<embedded-vlc>":
                remembered_command = command
            self.last_external_player_command = remembered_command

            # VLC may have been removed after Internal VLC was selected. Validate
            # the saved choice before restoring it and reuse the last external player
            # when possible.
            if command == "<embedded-vlc>" and not EmbeddedPlayerWindow.is_available():
                command = remembered_command or ""
                config['ExternalPlayer']['Command'] = command
                try:
                    write_config_file(self.user_data_file, config)
                except OSError as error:
                    print(f"Could not save media player fallback: {error}")
                QTimer.singleShot(
                    0,
                    lambda fallback=command: self._show_internal_vlc_unavailable(
                        fallback
                    ),
                )
            return command

        # First-run default: prefer the internal libvlc-backed player when it's
        # actually usable on this machine. If libvlc isn't present we leave the
        # command empty so the user is nudged toward "Choose Media Player".
        try:
            if EmbeddedPlayerWindow.is_available():
                default_cmd = "<embedded-vlc>"
                # Persist the choice so the user can see "Active player: Internal VLC"
                # in Settings without having to click anything.
                config['ExternalPlayer'] = {'Command': default_cmd}
                self.last_external_player_command = ""
                try:
                    write_config_file(self.user_data_file, config)
                except OSError:
                    pass
                return default_cmd
        except Exception:
            pass

        self.last_external_player_command = ""
        QTimer.singleShot(0, self._show_internal_vlc_unavailable)
        return ""

    def save_external_player_command(self):
        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError):
            config = configparser.ConfigParser()

        # Store the active mode and the last external executable separately. Switching
        # to Internal VLC must not erase the path the user may want to select again.
        if self.external_player_command and self.external_player_command != "<embedded-vlc>":
            self.last_external_player_command = self.external_player_command
        remembered_command = getattr(self, "last_external_player_command", "") or ""
        config['ExternalPlayer'] = {
            'Command': self.external_player_command,
            'LastExternalCommand': remembered_command
        }

        try:
            write_config_file(self.user_data_file, config)
        except OSError as e:
            print(f"Could not write user data file: {e}")

    def open_address_book(self):
        dialog = AccountManager(self)
        self._prepare_dialog_theme(dialog)
        dialog.exec_()







def main():
    # A frozen one-file executable re-enters this module for its player child.
    # Handle that mode before configuring the main process and its log file.
    if '--embedded-player-process' in sys.argv:
        sys.exit(run_embedded_player_process())

    install_logging()
    app = QApplication(sys.argv)
    configure_qt_application(app)

    player = IPTVPlayerApp()
    player.show()
    QtWidgets.qApp.processEvents()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()




