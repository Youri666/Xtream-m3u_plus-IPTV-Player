"""Main Qt window: coordinate provider data, catalog views, and playback.

LIVE, Movies, and Series share list construction, search, sorting, and caches.
Series alone adds show/season/episode navigation. Provider workers return data
to GUI slots; the internal VLC window runs in a separate process. Account JSON
files hold catalog preferences and history, while the INI holds global settings.
"""

import sys
import os
from os import path
import time
import requests
import subprocess
import configparser
import ctypes
import json
import logging
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
    QTextEdit, QGridLayout, QMessageBox, QListView, QTreeWidget, QTreeWidgetItem, QComboBox, QSplitter,
    QGroupBox, QRadioButton, QButtonGroup, QToolButton
)

from iptv_player.ui.info_panels import LiveInfoBox, MovieInfoBox, SeriesInfoBox
from iptv_player.ui.player import EmbeddedPlayerWindow
from iptv_player.bootstrap import (
    configure_qt_application,
    install_logging,
    set_detailed_logging,
)
from iptv_player.constants import (
    CURRENT_CONFIG_SCHEMA_VERSION,
    CURRENT_VERSION,
    DEFAULT_INTERNAL_SEEK_STEP_SECONDS,
    DEFAULT_INTERNAL_SPEED_STEP,
    DEFAULT_INTERNAL_VOLUME_STEP_PERCENT,
    DEFAULT_HISTORY_SIZE,
    DEFAULT_RESUME_BEHAVIOR,
    DEFAULT_URL_FORMATS,
    GITHUB_REPO,
    REMEMBER_LIST_SORTING,
)
from iptv_player.config import (
    AdvancedPreferences,
    INTERNAL_VLC_COMMAND,
    InternalPlayerPreferences,
    application_resource_path,
    delete_account,
    load_account,
    load_account_id,
    load_accounts,
    load_auto_update_preference,
    load_content_preferences,
    remove_content_preferences,
    load_advanced_preferences,
    load_internal_player_preferences,
    load_player_preference,
    load_sorting_preference,
    load_theme_preference,
    load_startup_account,
    migrate_legacy_player_volume,
    migrate_user_data_file,
    parse_account,
    save_auto_update_preference,
    save_advanced_preferences,
    save_internal_player_preferences,
    save_player_preference,
    save_sorting_preference,
    save_startup_account,
    save_theme_preference,
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
    account_history_file,
    clear_history,
    entries_in_favorite_order,
    load_history,
    load_provider_preferences,
    migrate_legacy_favorites_file,
    provider_preferences_file,
    remove_account_data_files,
    record_history,
    remove_history_entry,
    repair_misclassified_history,
    resume_position,
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
from iptv_player.updater import fetch_latest_release, is_newer_version
from iptv_player.provider.network import (
    DEFAULT_ACCOUNT_INFO_REFRESH_INTERVAL,
    DEFAULT_CATALOG_CACHE_MAX_AGE_HOURS,
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


# Keep visual differences here; shared builders retain the named widget aliases
# used by content-specific handlers and persisted splitter settings.
CONTENT_TAB_SPECS = (
    {
        'stream_type': 'LIVE',
        'attribute': 'live',
        'label': 'LIVE',
        'category_search_placeholder': 'Search Live TV Categories...',
        'streaming_search_placeholder': 'Search Live TV Channels...',
        'info_box_class': LiveInfoBox,
        'info_minimum_width': 300,
    },
    {
        'stream_type': 'Movies',
        'attribute': 'movies',
        'label': 'Movies',
        'category_search_placeholder': 'Search Movies Categories...',
        'streaming_search_placeholder': 'Search Movies...',
        'info_box_class': MovieInfoBox,
        'info_minimum_width': 350,
    },
    {
        'stream_type': 'Series',
        'attribute': 'series',
        'label': 'Series',
        'category_search_placeholder': 'Search Series Categories...',
        'streaming_search_placeholder': 'Search Series...',
        'info_box_class': SeriesInfoBox,
        'info_minimum_width': 350,
    },
)
CONTENT_TYPES = tuple(spec['stream_type'] for spec in CONTENT_TAB_SPECS)



class IPTVPlayerApp(QMainWindow):
    """Own the active account's views and dispatch work to providers and players."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"IPTV Player {CURRENT_VERSION}")
        self.resize(1300, 900)

        self.user_agents = [
            "VLC/3.0.16 LibVLC/3.0.16",  # VLC
            "Kodi/20.2 (Linux; Android 13; SM-G998B) Android/13 Sys_CPU/armv8a App_Bitness/64 Version/20.2-(20.2.0)-Git:20230626-abc123",  # Kodi
            "Dalvik/2.1.0 (Linux; U; Android 13; Pixel 6 Pro Build/TQ2A.230505.002)",  # MX Player
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",  # Windows Chrome
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",  # Windows Firefox
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Safari/605.1.15",  # MacOS Safari
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.3351.83",  # Windows Edge
            "Mozilla/5.0 (Linux; Android 14; Pixel 7 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",  # Android Chrome
            "Mozilla/5.0 (Android 14; Mobile; rv:126.0) Gecko/126.0 Firefox/126.0",  # Android Firefox
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",  # iOS 17 Safari
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",  # Linux (Ubuntu + Chrome)
            "Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",  # Linux (Fedora + Firefox)
            "Mozilla/5.0 (X11; CrOS x86_64 15633.64.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",  # ChromeOS
            "Mozilla/5.0 (Linux; Android 13; SAMSUNG SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/24.0 Chrome/124.0.0.0 Mobile Safari/537.36",  # Samsung Internet
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
        self.history_base_file = path.join(self.data_directory, "provider_history.json")
        self.history_file = ""
        self.legacy_cache_file = path.join(self.data_directory, "all_cached_data.json")

        # The internal VLC UI runs in a second process. Commands are queued so
        # sending a large visible playlist can never block the main Qt event loop.
        self._embedded_player_process = None
        self._embedded_player_listener = None
        self._embedded_player_command_queue = None
        self._embedded_player_sender_thread = None
        self._embedded_player_event_queue = queue.Queue()

        # These defaults are replaced by persisted values during startup and are
        # sent to the isolated VLC process whenever it is started or reconfigured.
        self.internal_seek_step_seconds = DEFAULT_INTERNAL_SEEK_STEP_SECONDS
        self.internal_volume_step_percent = DEFAULT_INTERNAL_VOLUME_STEP_PERCENT
        self.internal_speed_step = DEFAULT_INTERNAL_SPEED_STEP
        self.internal_audio_language = ""
        self.internal_subtitle_language = ""
        self.internal_resume_behavior = DEFAULT_RESUME_BEHAVIOR
        self.history_size = DEFAULT_HISTORY_SIZE
        self.default_url_formats = dict(DEFAULT_URL_FORMATS)

        self.update_user_data_file()
        self._migrate_legacy_player_volume()

        self._init_resource_paths()

        self.setWindowIcon(QIcon(self.path_to_window_icon))

        self.default_font_size      = 10
        self.go_back_text           = " Go back"
        self.all_categories_text    = "All"
        self.fav_categories_text    = "Favorites"

        # Series uses three navigation levels: shows, seasons, and episodes.
        self.series_navigation_level = 0
        self.finished_fetching_series_info = False
        self.current_series_entry = None
        self.current_series_season = None
        self._pending_history_series = None

        self.streaming_search_history_list      = []
        self.streaming_search_history_list_idx  = [0]
        self.category_search_history_list       = []
        self.category_search_history_list_idx   = [0]
        self.max_search_history_size            = 30

        # Retain selections to avoid repeating expensive provider requests.
        self.prev_clicked_category_item = {
            stream_type: 0 for stream_type in CONTENT_TYPES
        }
        self.prev_clicked_streaming_item        = 0
        self.prev_double_clicked_streaming_item = 0

        self.categories_per_stream_type = {}
        self.entries_per_stream_type = {
            stream_type: [] for stream_type in CONTENT_TYPES
        }

        # Search operates on source data rather than the currently visible Qt rows.
        self.currently_loaded_categories = {
            stream_type: [] for stream_type in CONTENT_TYPES
        }
        self.category_item_counts = {
            stream_type: {} for stream_type in CONTENT_TYPES
        }
        self.currently_loaded_streams = {
            **{stream_type: [] for stream_type in CONTENT_TYPES},
            'Seasons': [],
            'Episodes': [],
        }

        # Cache the filtered and ordered entry lists used by category views. The
        # provider data is already cached, but preparing "All" again can still scan
        # and sort tens of thousands of Movies every time the user returns to it.
        self.category_view_cache = {
            stream_type: {} for stream_type in CONTENT_TYPES
        }
        # QListWidgetItem creation dominates category switching for very large
        # catalogs. Detached items can safely be kept and reattached when the same
        # view is opened again, making repeated switches effectively immediate.
        self.category_item_cache = {
            stream_type: {} for stream_type in CONTENT_TYPES
        }
        self.active_category_view_key = {
            stream_type: None for stream_type in CONTENT_TYPES
        }

        # Each content type can be hidden and omitted from provider requests.
        self.content_enabled = {
            stream_type: True for stream_type in CONTENT_TYPES
        }

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
            stream_type: {} for stream_type in CONTENT_TYPES
        }
        self.category_list_sort_preferences = {}

        # Store exclusions rather than visible ids so categories introduced by the
        # provider after an application update remain visible without user action.
        self.hidden_category_ids = {
            stream_type: set() for stream_type in CONTENT_TYPES
        }

        self.server            = ""
        self.username          = ""
        self.password          = ""
        self.live_url_format   = ""
        self.movie_url_format  = ""
        self.series_url_format = ""
        self.active_account_name = ""
        self.active_account_id = ""
        self._catalog_loaded = False
        self._catalog_request_generation = 0

        # Keep data, EPG, and image fetching ordered and gentle on the provider.
        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(1)

        # Stream-status probes run on a dedicated 2-thread pool so a slow LIVE channel
        # check can't block image or EPG fetching (issue #74).
        self.status_threadpool = QThreadPool()
        self.status_threadpool.setMaxThreadCount(2)

        # Whether the LIVE traffic-light stream-status check is enabled. The check
        # can be disabled in the Settings tab if a provider's streams are flaky and
        # the probe is producing false offline reports.
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
        self.player_event_timer = QTimer(self)
        self.player_event_timer.setInterval(100)
        self.player_event_timer.timeout.connect(self._process_embedded_player_events)
        self.player_event_timer.start()

        self.init_icons()

        self.init_tab_widget()

        self.init_iptv_info()
        self.init_history_tab()

        self.init_category_list_widgets()
        self.init_entry_list_widgets()
        self.init_info_boxes()

        self.init_search_bars()


        self.init_settings_tab()

        self.init_progress_bar()

        self.load_data_at_startup()

        self.content_splitters = {}
        for spec in CONTENT_TAB_SPECS:
            stream_type = spec['stream_type']
            attribute = spec['attribute']
            splitter = self._create_content_splitter(
                self.category_search_widgets[stream_type],
                self.category_list_widgets[stream_type],
                self.streaming_search_widgets[stream_type],
                self.streaming_list_widgets[stream_type],
                self.info_boxes[stream_type],
                info_minimum_width=spec['info_minimum_width'],
            )
            self.content_splitters[stream_type] = splitter
            setattr(self, f'{attribute}_splitter', splitter)
            self.content_tab_layouts[stream_type].addWidget(splitter)

        self.info_tab_layout.addWidget(self.iptv_info_text)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

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

    def _prewarm_embedded_player(self):
        """Initialize the selected internal VLC engine before the first playback."""
        try:
            self._ensure_embedded_player_process()
            self._embedded_player_command_queue.put({'command': 'warmup'})
        except Exception as error:
            logging.debug("Could not prewarm internal VLC: %s", error)

    def set_active_account(self, name):
        """Store the active account label and expose it in the window title."""
        self._reset_provider_view_state()
        self._catalog_loaded = False
        self._catalog_request_generation += 1
        self.active_account_name = str(name or "").strip()
        self.active_account_id = (
            load_account_id(self.user_data_file, self.active_account_name) or ""
        )
        logging.debug(
            "Active account changed: name=%r; id=%s",
            self.active_account_name,
            self.active_account_id or "none",
        )
        self.provider_preferences_file = (
            str(provider_preferences_file(
                self.provider_preferences_base_file, self.active_account_id
            ))
            if self.active_account_id else ""
        )
        self.history_file = (
            str(account_history_file(self.history_base_file, self.active_account_id))
            if self.active_account_id else ""
        )
        title = f"IPTV Player {CURRENT_VERSION}"
        if self.active_account_name:
            title = f"{title} ({self.active_account_name})"
        self.setWindowTitle(title)
        self._refresh_account_selectors(self.active_account_name)
        self._load_hidden_categories()
        self._load_account_sort_preferences()
        self._load_account_content_preferences()
        self.refresh_history_tab()

    def activate_saved_account(self, name):
        """Load one saved account and refresh its provider catalog."""
        parsed_account = parse_account(load_account(self.user_data_file, name))
        if parsed_account is None:
            return False

        method, fields = parsed_account
        if method == "manual":
            (
                self.server,
                self.username,
                self.password,
                self.live_url_format,
                self.movie_url_format,
                self.series_url_format,
            ) = fields
        elif method == "m3u_plus":
            (
                m3u_url,
                self.live_url_format,
                self.movie_url_format,
                self.series_url_format,
            ) = fields
            if not self.extract_credentials_from_m3u_plus_url(m3u_url):
                return False
        else:
            return False

        self.set_active_account(name)
        self.login()
        return True

    def delete_saved_account(self, name):
        """Delete a saved account and every JSON file owned by its stable id."""
        account_id = load_account_id(self.user_data_file, name)
        if not account_id or not delete_account(self.user_data_file, name):
            return False

        failures = remove_account_data_files(
            account_id,
            self.cache_file,
            self.favorites_base_file,
            self.provider_preferences_base_file,
            self.history_base_file,
        )
        for filename, error in failures:
            logging.warning(
                "Could not delete account data file %s: %s", filename, error
            )
        return True

    def _refresh_account_selectors(self, preferred_active_name=None):
        """Synchronize startup and active account selectors without activating one."""
        active_selector = getattr(self, "account_selector", None)
        startup_selector = getattr(self, "startup_account_selector", None)
        if active_selector is None or startup_selector is None:
            return

        account_names = list(load_accounts(self.user_data_file))
        startup_name = load_startup_account(self.user_data_file)
        active_selector.blockSignals(True)
        startup_selector.blockSignals(True)
        active_selector.clear()
        startup_selector.clear()
        startup_selector.addItem("None")
        if account_names:
            active_selector.addItems(account_names)
            startup_selector.addItems(account_names)
            selected_name = preferred_active_name or self.active_account_name
            active_index = active_selector.findText(
                selected_name, Qt.MatchFixedString
            )
            startup_index = startup_selector.findText(
                startup_name, Qt.MatchFixedString
            )
            active_selector.setCurrentIndex(active_index)
            startup_selector.setCurrentIndex(max(0, startup_index))
            active_selector.setEnabled(True)
            startup_selector.setEnabled(True)
        else:
            active_selector.addItem("No accounts configured")
            active_selector.setEnabled(False)
            startup_selector.setEnabled(False)
        active_selector.blockSignals(False)
        startup_selector.blockSignals(False)

    def _startup_account_changed(self, name):
        """Persist the account chosen for automatic loading at startup."""
        save_startup_account(self.user_data_file, name)

    def _quick_account_changed(self, name):
        """Activate the account explicitly chosen from the Settings selector."""
        if not name or name == self.active_account_name:
            return
        if not self.activate_saved_account(name):
            self._refresh_account_selectors(self.active_account_name)

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
            'path_to_live_icon': 'tv_tab_icon.ico',
            'path_to_movies_icon': 'movies_tab_icon.ico',
            'path_to_series_icon': 'series_tab_icon.ico',
            'path_to_home_icon': 'home_tab_icon.ico',
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
        """Restore window geometry and per-tab column widths."""
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
        self.tab_icon_size = QSize(24, 24)

        self.live_icon              = QIcon(self.path_to_live_icon)
        self.movies_icon            = QIcon(self.path_to_movies_icon)
        self.series_icon            = QIcon(self.path_to_series_icon)
        self.history_icon           = QIcon(self.path_to_home_icon)
        self.favorites_icon         = QIcon(self.path_to_favorites_icon)
        self.favorites_icon_colour  = QIcon(self.path_to_fav_colour_icon)
        self.info_icon              = QIcon(self.path_to_info_icon)
        self.settings_icon          = QIcon(self.path_to_settings_icon)

        self.account_manager_icon   = QIcon(self.path_to_account_icon)
        self.mediaplayer_icon       = QIcon(self.path_to_mediaplayer_icon)

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
            'live_icon': self.path_to_live_icon,
            'movies_icon': self.path_to_movies_icon,
            'series_icon': self.path_to_series_icon,
            'history_icon': self.path_to_home_icon,
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
                **{
                    spec['label']: getattr(self, f"{spec['attribute']}_icon")
                    for spec in CONTENT_TAB_SPECS
                },
                'History': self.history_icon,
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
        self.tab_widget = QTabWidget()

        self.history_tab  = QWidget()
        self.info_tab     = QWidget()
        settings_tab      = QWidget()

        self.history_tab_layout     = QHBoxLayout(self.history_tab)
        self.info_tab_layout        = QVBoxLayout(self.info_tab)
        self.settings_layout        = QGridLayout(settings_tab)

        self.content_tabs = {}
        self.content_tab_layouts = {}
        for spec in CONTENT_TAB_SPECS:
            stream_type = spec['stream_type']
            attribute = spec['attribute']
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)
            self.content_tabs[stream_type] = tab
            self.content_tab_layouts[stream_type] = tab_layout
            setattr(self, f'{attribute}_tab', tab)
            setattr(self, f'{attribute}_tab_layout', tab_layout)

        self.tab_widget.addTab(
            self.history_tab,
            self.history_icon,
            "History",
        )
        for spec in CONTENT_TAB_SPECS:
            self.tab_widget.addTab(
                self.content_tabs[spec['stream_type']],
                getattr(self, f"{spec['attribute']}_icon"),
                spec['label'],
            )
        self.tab_widget.addTab(self.info_tab,   self.info_icon,         "Info")
        self.tab_widget.addTab(settings_tab,    self.settings_icon,     "Settings")
        self.tab_widget.currentChanged.connect(self._on_current_tab_changed)

    def init_history_tab(self):
        """Create one recent-playback panel for each enabled content type."""
        self.history_widgets = {}
        self.history_groups = {}
        for stream_type, label in (
            ("LIVE", "LIVE"),
            ("Movies", "Movies"),
            ("Series", "Series"),
        ):
            group = QGroupBox(label)
            layout = QVBoxLayout(group)
            history_list = QTreeWidget()
            history_list.setColumnCount(2)
            history_list.setHeaderLabels(("Last viewed", "Title"))
            history_list.setRootIsDecorated(False)
            history_list.setAlternatingRowColors(True)
            history_list.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            history_list.header().setStretchLastSection(True)
            history_list.header().setSectionResizeMode(
                0, QtWidgets.QHeaderView.ResizeToContents
            )
            history_list.header().setSectionResizeMode(
                1, QtWidgets.QHeaderView.Stretch
            )
            history_list.itemActivated.connect(self._history_item_activated)
            layout.addWidget(history_list)
            self.history_groups[stream_type] = group
            self.history_widgets[stream_type] = history_list
            self.history_tab_layout.addWidget(group, 1)
        self.refresh_history_tab()

    def refresh_history_tab(self):
        """Reload the active account history into its three compact panels."""
        if not hasattr(self, "history_widgets"):
            return
        entries = load_history(self.history_file) if self.history_file else []
        for history_list in self.history_widgets.values():
            history_list.clear()
        for entry in entries:
            history_list = self.history_widgets.get(entry.get("type"))
            if history_list is None:
                continue
            timestamp = self._history_display_time(entry.get("last_viewed", ""))
            item = QTreeWidgetItem((timestamp, entry.get("title", "")))
            item.setData(0, Qt.UserRole, entry)
            history_list.addTopLevelItem(item)

    @staticmethod
    def _history_display_time(value):
        """Format an ISO timestamp using the computer's local time zone."""
        try:
            return datetime.fromisoformat(str(value)).astimezone().strftime(
                "%Y-%m-%d %H:%M"
            )
        except (TypeError, ValueError):
            return str(value)

    def _history_item_activated(self, item, _column=0):
        """Restore the source list for a history row without starting playback."""
        self._process_embedded_player_events()
        entry = item.data(0, Qt.UserRole) if item is not None else None
        if not isinstance(entry, dict):
            return
        if not self._catalog_loaded:
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Information)
            dialog.setWindowTitle("Catalog still loading")
            dialog.setText(
                "The provider catalog is not ready yet. Please try again when "
                "loading has finished."
            )
            dialog.setStandardButtons(QMessageBox.Ok)
            self._prepare_dialog_theme(dialog)
            dialog.exec_()
            return
        entry = next(
            (
                saved for saved in load_history(self.history_file)
                if saved.get("key") == entry.get("key")
            ),
            entry,
        )
        if entry.get("type") == "Series" and entry.get("series_id"):
            if self._open_history_series(entry):
                return
        elif self._open_history_catalog_entry(entry):
            return

        self._remove_unavailable_history_entry(entry)

    def _remove_unavailable_history_entry(self, entry):
        """Delete one stale history row and explain why it disappeared."""
        remove_history_entry(self.history_file, entry.get("key"))
        self.refresh_history_tab()
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Information)
        dialog.setWindowTitle("History item unavailable")
        dialog.setText(
            "This item is no longer available in the provider catalog and "
            "has been removed from History."
        )
        dialog.setStandardButtons(QMessageBox.Ok)
        self._prepare_dialog_theme(dialog)
        dialog.exec_()

    def _open_history_catalog_entry(self, history_entry):
        """Restore a LIVE or Movies category and select its remembered item."""
        stream_type = history_entry.get("type")
        if stream_type not in ("LIVE", "Movies"):
            return False
        stream_id = str(history_entry.get("stream_id", ""))
        catalog_entry = next(
            (
                entry for entry in self.entries_per_stream_type.get(stream_type, [])
                if str(entry.get("stream_id", "")) == stream_id
            ),
            None,
        )
        if catalog_entry is None:
            return False

        target_tab = self.live_tab if stream_type == "LIVE" else self.movies_tab
        self.tab_widget.setCurrentWidget(target_tab)
        category_item = self._history_category_item(
            stream_type, history_entry, catalog_entry
        )
        if category_item is None:
            return False
        category_list = self.category_list_widgets[stream_type]
        category_list.setCurrentItem(category_item)
        self.prev_clicked_category_item[stream_type] = 0
        category_list.itemClicked.emit(category_item)

        stream_list = self.streaming_list_widgets[stream_type]
        for row in range(stream_list.count()):
            stream_item = stream_list.item(row)
            data = stream_item.data(Qt.UserRole)
            if (
                isinstance(data, dict)
                and str(data.get("stream_id", "")) == stream_id
            ):
                stream_list.setCurrentItem(stream_item)
                stream_list.scrollToItem(stream_item)
                # Programmatic selection does not emit itemClicked. Run the same
                # handler as a real click so the EPG or movie panel is refreshed.
                self.prev_clicked_streaming_item = None
                self.streaming_item_clicked(stream_item)
                return True
        return False

    def _history_category_item(self, stream_type, history_entry, catalog_entry):
        """Find the saved source category, falling back to the provider category."""
        category_list = self.category_list_widgets[stream_type]
        source_name = history_entry.get("source_category_name", "")
        source_id = str(history_entry.get("source_category_id", ""))
        source_is_available = (
            source_name != self.fav_categories_text
            or bool(catalog_entry.get("favorite"))
        )
        actual_category_id = str(catalog_entry.get("category_id", ""))
        fallback_item = None
        all_item = None
        for row in range(category_list.count()):
            candidate = category_list.item(row)
            data = candidate.data(Qt.UserRole) or {}
            candidate_name = data.get("category_name", candidate.text())
            candidate_id = str(data.get("category_id", ""))
            if candidate_name == self.all_categories_text:
                all_item = candidate
            if candidate_id == actual_category_id:
                fallback_item = candidate
            if (
                source_is_available
                and candidate_name == source_name
                and candidate_id == source_id
            ):
                return candidate
        return fallback_item or all_item

    def _open_history_series(self, history_entry):
        """Restore the category and season where a history episode was launched."""
        series_id = str(history_entry.get("series_id", ""))
        series_entry = next(
            (
                entry for entry in self.entries_per_stream_type.get("Series", [])
                if str(entry.get("series_id", "")) == series_id
            ),
            None,
        )
        if series_entry is None:
            return False

        self.tab_widget.setCurrentWidget(self.series_tab)
        category_list = self.category_list_widgets["Series"]
        category_item = self._history_category_item(
            "Series", history_entry, series_entry
        )
        if category_item is None:
            return False

        category_list.setCurrentItem(category_item)
        # Emit the normal signal so list caches, sorting, and category state remain
        # identical to a category selected manually by the user.
        self.prev_clicked_category_item["Series"] = 0
        category_list.itemClicked.emit(category_item)

        series_list = self.streaming_list_widgets["Series"]
        series_item = next(
            (
                series_list.item(row) for row in range(series_list.count())
                if isinstance(series_list.item(row).data(Qt.UserRole), dict)
                and str(series_list.item(row).data(Qt.UserRole).get("series_id", ""))
                == series_id
            ),
            None,
        )
        if series_item is None:
            return False

        series_list.setCurrentItem(series_item)
        series_list.scrollToItem(series_item)
        # Refresh the Series information panel before entering its season view.
        self.prev_clicked_streaming_item = None
        self.streaming_item_clicked(series_item)
        self.current_series_entry = series_entry
        self.series_navigation_level = 1
        self._pending_history_series = dict(history_entry)
        self.show_seasons(series_entry)
        return True

    def _history_entry_url(self, entry):
        """Rebuild a private stream URL without persisting credentials in history."""
        stream_type = entry.get("type")
        stream_id = entry.get("stream_id")
        if not stream_id or stream_type not in ("LIVE", "Movies", "Series"):
            return ""
        template = {
            "LIVE": self.live_url_format,
            "Movies": self.movie_url_format,
            "Series": self.series_url_format,
        }[stream_type]
        extension = str(entry.get("container_extension", "") or "")
        if ".{container_extension}" not in template:
            extension = ""
            template = template.replace(".{container_extension}", "")
        try:
            return template.format(
                server=self.server,
                username=self.username,
                password=self.password,
                stream_id=stream_id,
                container_extension=extension,
            )
        except (KeyError, ValueError):
            return ""

    def init_search_bars(self):
        """Build independent category and title searches for each content tab."""
        for spec in CONTENT_TAB_SPECS:
            stream_type = spec['stream_type']
            category_search = QLineEdit()
            category_search.setPlaceholderText(
                spec['category_search_placeholder']
            )
            self.category_search_bars[stream_type] = category_search
            self.category_search_widgets[stream_type] = self.configure_search_bar(
                category_search,
                'category',
                stream_type,
                self.category_list_widgets,
                self.category_search_history_list,
                self.category_search_history_list_idx,
            )

            streaming_search = QLineEdit()
            streaming_search.setPlaceholderText(
                spec['streaming_search_placeholder']
            )
            self.streaming_search_bars[stream_type] = streaming_search
            self.streaming_search_widgets[stream_type] = self.configure_search_bar(
                streaming_search,
                'streaming',
                stream_type,
                self.streaming_list_widgets,
                self.streaming_search_history_list,
                self.streaming_search_history_list_idx,
            )

    def configure_search_bar(self, search_bar, list_content_type, stream_type, list_widgets, search_history_list, search_history_list_idx):
        sort_a_z        = QAction("A-Z", self)
        sort_z_a        = QAction("Z-A", self)
        sort_disabled   = QAction("Sorting disabled", self)
        for sorting_action in (sort_a_z, sort_z_a, sort_disabled):
            sorting_action.setCheckable(True)

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

        sorting_menu = QMenu(sort_button)
        sorting_menu.setTitle("Set sorting order:")
        sorting_group = QActionGroup(sorting_menu)
        sorting_group.setExclusive(True)
        sorting_group.addAction(sort_a_z)
        sorting_group.addAction(sort_z_a)
        sorting_group.addAction(sort_disabled)
        sorting_menu.addActions([sort_a_z, sort_z_a, sort_disabled])
        sort_button.setMenu(sorting_menu)

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
            stream_type: set() for stream_type in CONTENT_TYPES
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
                current.get('content_enabled', {}),
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

        is_top_level_stream_view = (
            list_content_type == 'streaming'
            and (stream_type != 'Series' or self.series_navigation_level == 0)
        )
        if is_top_level_stream_view and not sorting_enabled:
            # Disabling sorting must restore provider order rather than preserve
            # the order of the list that was previously sorted A-Z or Z-A.
            category_name, category_id = self._selected_category(stream_type)
            self.currently_loaded_streams[stream_type] = list(
                self._raw_entries_for_category(
                    stream_type, category_name, category_id
                )
            )

        self.sort_list(
            search_bar, list_content_type, stream_type, list_widgets,
            sorting_enabled, sort_order
        )

        if self.remember_category_sorting and list_content_type == 'streaming':
            category_name, category_id = self._selected_category(stream_type)
            self.active_category_view_key[stream_type] = self._category_view_key(
                stream_type, category_name, category_id
            )
        elif (
            list_content_type == 'streaming'
            and (stream_type != 'Series' or self.series_navigation_level == 0)
        ):
            # A temporary override must not be cached under the default-order key.
            # Leaving this category will discard its Qt items, so returning rebuilds
            # the view with the global sorting preference.
            self.active_category_view_key[stream_type] = None

    def clear_search(self, search_bar, list_content_type, stream_type, list_widgets, history_list_idx):
        search_bar.clear()

        history_list_idx[0] = -1

        self.search_in_list(list_content_type, stream_type, "")

    def sort_list(self, search_bar, list_content_type, stream_type, list_widgets, sorting_enabled, sort_order):
        """Rebuild a column in its chosen order, preserving navigation rows.

        Root catalogs use entry dictionaries; Series seasons and episodes use
        their own sources. Category columns always keep All and Favorites first.
        """
        # Keep the menu check mark synchronized even when a global setting invokes
        # sorting directly instead of going through applySortingChoice().
        search_bar.current_sorting = (sorting_enabled, sort_order)
        self.set_progress_bar(0, f"Sorting {stream_type} {list_content_type}")

        list_widget = list_widgets[stream_type]

        # Top-level stream catalogs can contain tens of thousands of rows. Qt's
        # native QListWidget sort runs entirely in the GUI thread and can freeze the
        # whole application for several seconds. Sort the lightweight dictionaries
        # first, then rebuild the widget without entering a nested event loop.
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
        if is_seasons_view:
            seasons_dict = self.currently_loaded_streams.get('Seasons', {}) or {}
            keys = list(seasons_dict.keys())
            if sorting_enabled:
                keys = ordered_season_keys(
                    keys, descending=(sort_order == 1)
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

        is_episodes_view = (
            list_content_type == 'streaming'
            and stream_type == 'Series'
            and getattr(self, 'series_navigation_level', 0) == 2
        )
        if is_episodes_view:
            episodes = list(
                self.currently_loaded_streams.get('Episodes', {}) or []
            )
            if sorting_enabled:
                episodes = ordered_catalog_entries(
                    episodes,
                    True,
                    descending=(sort_order == 1),
                    title_key='title',
                )

            list_widget.setSortingEnabled(False)
            list_widget.clear()
            go_back_item = QListWidgetItem(self.go_back_text)
            go_back_item.setIcon(self.go_back_icon)
            list_widget.addItem(go_back_item)
            for episode in episodes:
                item = QListWidgetItem(episode.get('title', ''))
                item.setData(Qt.UserRole, episode)
                list_widget.addItem(item)
            self.animate_progress(
                0, 100, f"Finished sorting {stream_type} {list_content_type}"
            )
            return

        # Keep automatic sorting disabled while changing the list. Enabling it here
        # already performs a sort, and the former explicit sortItems() call performed
        # the same expensive work a second time for large Movie catalogs.
        list_widget.setSortingEnabled(False)
        list_widget.setUpdatesEnabled(False)

        try:
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
        """Replace a stream list atomically with respect to queued UI events."""
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

                # Update progress without dispatching events while rows and their
                # metadata are being replaced. Reentrant callbacks can clear or
                # repopulate this same widget before this operation completes.
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
        self.category_list_widgets = {}
        for spec in CONTENT_TAB_SPECS:
            list_widget = KeyboardNavigableListWidget()
            list_widget.itemClicked.connect(self.category_item_clicked)
            list_widget.keyboardActivated.connect(self.category_item_clicked)
            list_widget.keyboardSelected.connect(self.category_item_clicked)
            self.category_list_widgets[spec['stream_type']] = list_widget
            setattr(self, f"category_list_{spec['attribute']}", list_widget)

        standard_icon_size = QSize(24, 24)
        for list_widget in self.category_list_widgets.values():
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
        self.streaming_list_widgets = {}
        for spec in CONTENT_TAB_SPECS:
            list_widget = KeyboardNavigableListWidget()
            list_widget.setLayoutMode(QListView.Batched)
            list_widget.setBatchSize(2000)
            list_widget.itemDoubleClicked.connect(
                self.streaming_item_double_clicked
            )
            list_widget.itemClicked.connect(self.streaming_item_clicked)
            list_widget.keyboardActivated.connect(
                self.streaming_item_keyboard_activated
            )
            list_widget.keyboardSelected.connect(self.streaming_item_clicked)
            self.streaming_list_widgets[spec['stream_type']] = list_widget
            setattr(self, f"streaming_list_{spec['attribute']}", list_widget)

        # Tab and Backtab switch directly between the two catalog columns.
        for stream_type in self.streaming_list_widgets:
            category_list = self.category_list_widgets[stream_type]
            streaming_list = self.streaming_list_widgets[stream_type]
            category_list.set_tab_target(streaming_list)
            streaming_list.set_tab_target(category_list)

        standard_icon_size = QSize(24, 24)
        for list_widget in self.streaming_list_widgets.values():
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
        self.info_boxes = {}
        for spec in CONTENT_TAB_SPECS:
            info_box = spec['info_box_class'](self)
            self.info_boxes[spec['stream_type']] = info_box
            setattr(self, f"{spec['attribute']}_info_box", info_box)

    def load_default_sorting_order(self):
        sorting_order = load_sorting_preference(self.user_data_file)

        print(f"loading default sorting order: {sorting_order}")

        self.default_sorting_order_box.setCurrentText(sorting_order)

        self._load_category_sort_preferences(None)

        match self.default_sorting_order_box.currentText():
            case "A-Z":
                self.sorting_enabled    = True
                self.sorting_order      = 0
                self.remember_category_sorting = False

            case "Z-A":
                self.sorting_enabled    = True
                self.sorting_order      = 1

                self.remember_category_sorting = False

            case "Remember per list":
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
            stream_type: {} for stream_type in CONTENT_TYPES
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
        # An account without a saved override must inherit the global setting.
        # This preserves "Sorting disabled" on a fresh installation.
        saved_fallback = saved.get('fallback', self.category_sort_fallback)
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
                current.get('content_enabled', {}),
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
        sorting_enabled = sorting_order in ("A-Z", "Z-A")
        sort_order = 1 if sorting_order == "Z-A" else 0
        print(
            f"sorting {sorting_order}"
            if sorting_enabled else "sorting disabled"
        )
        for stream_type in CONTENT_TYPES:
            self.sort_list(
                self.category_search_bars[stream_type],
                'category',
                stream_type,
                self.category_list_widgets,
                sorting_enabled,
                sort_order,
            )
            self.sort_list(
                self.streaming_search_bars[stream_type],
                'streaming',
                stream_type,
                self.streaming_list_widgets,
                sorting_enabled,
                sort_order,
            )

    def set_default_sorting_order(self, e, combobox):
        sorting_order = combobox.currentText()

        print(f"setting default sorting order: {sorting_order}")

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

            case "Remember per list":
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

        if sorting_order == REMEMBER_LIST_SORTING:
            # Reapply both the category-column order and the preference for the
            # category currently visible in each content tab.
            for stream_type in self.streaming_list_widgets:
                category_list_enabled, category_list_order = getattr(
                    self.category_search_bars[stream_type],
                    'current_sorting',
                    self._sorting_for_category_list(stream_type),
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

        save_sorting_preference(self.user_data_file, sorting_order)

    def init_settings_tab(self):
        self.settings_layout.setSpacing(20)
        self.settings_layout.setAlignment(Qt.AlignTop)

        self.address_book_button = QPushButton("IPTV accounts")
        self.address_book_button.setIcon(self.account_manager_icon)
        self.address_book_button.setToolTip("Manage IPTV accounts")
        self.address_book_button.clicked.connect(self.open_address_book)

        self.account_selector = QtWidgets.QComboBox()
        self.account_selector.setPlaceholderText("Select an IPTV account…")
        self.account_selector.setToolTip("Switch to another IPTV account")
        self.account_selector.setMinimumContentsLength(18)
        self.account_selector.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.account_selector.setMinimumWidth(220)
        self.account_selector.setMaximumWidth(320)
        self.account_selector.currentTextChanged.connect(
            self._quick_account_changed
        )

        self.startup_account_selector = QtWidgets.QComboBox()
        self.startup_account_selector.setToolTip(
            "Choose the IPTV account loaded automatically at startup"
        )
        self.startup_account_selector.setMinimumContentsLength(14)
        self.startup_account_selector.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.startup_account_selector.setMinimumWidth(180)
        self.startup_account_selector.setMaximumWidth(280)
        self.startup_account_selector.currentTextChanged.connect(
            self._startup_account_changed
        )
        self._refresh_account_selectors(load_startup_account(self.user_data_file))

        self.account_controls = QWidget()
        account_controls_layout = QHBoxLayout(self.account_controls)
        account_controls_layout.setContentsMargins(0, 0, 0, 0)
        account_controls_layout.setSpacing(8)
        account_controls_layout.addWidget(self.address_book_button, 1)
        account_controls_layout.addWidget(QLabel("Startup account:"))
        account_controls_layout.addWidget(self.startup_account_selector)
        account_controls_layout.addWidget(QLabel("Active account:"))
        account_controls_layout.addWidget(self.account_selector)

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
        for stream_type in CONTENT_TYPES:
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
            "A-Z", "Z-A", "Sorting disabled", REMEMBER_LIST_SORTING
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
        self.settings_layout.addWidget(self.account_controls,                0, 0, 1, 2)
        self.settings_layout.addWidget(self.content_group_box,               1, 0, 1, 2)
        self.settings_layout.addWidget(self.window_behavior_group_box,       2, 0, 1, 2)
        self.settings_layout.addWidget(self.sorting_group_box,               3, 0, 1, 2)
        self.settings_layout.addWidget(self.player_group_box,                4, 0, 1, 2)
        self.settings_layout.addWidget(self.advanced_settings_group_box,     5, 0, 1, 2)
        self.settings_layout.addWidget(self.updates_group_box,               6, 0, 1, 2)

    def load_default_content(self):
        # Content visibility belongs to an IPTV account. Until an account becomes
        # active, expose every tab rather than applying another provider's choice.
        self.content_enabled = {
            stream_type: True for stream_type in CONTENT_TYPES
        }

        self._apply_content_visibility()

        # Loading preferences must not trigger three redundant writes to userdata.ini.
        for stream_type, checkbox in self.content_checkboxes.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(self.content_enabled[stream_type])
            checkbox.blockSignals(False)

    def _load_account_content_preferences(self):
        """Load enabled content types belonging only to the active account."""
        if not self.provider_preferences_file:
            return
        current = load_provider_preferences(self.provider_preferences_file)
        saved = current.get('content_enabled', {})
        if not saved:
            # Import the former global choice once for the first account opened
            # after this migration; subsequent accounts start with all content.
            saved = load_content_preferences(self.user_data_file)
            try:
                save_provider_preferences(
                    self.provider_preferences_file,
                    current.get('hidden_categories', {}),
                    current.get('category_sorting', {}),
                    saved,
                )
                remove_content_preferences(self.user_data_file)
            except OSError as error:
                logging.warning("Could not migrate content preferences: %s", error)
        self.content_enabled = {
            stream_type: bool(saved.get(stream_type, True))
            for stream_type in CONTENT_TYPES
        }
        self._apply_content_visibility()
        for stream_type, checkbox in getattr(self, 'content_checkboxes', {}).items():
            checkbox.blockSignals(True)
            checkbox.setChecked(self.content_enabled[stream_type])
            checkbox.blockSignals(False)

    def _apply_content_visibility(self):
        """Show only enabled content tabs while keeping Info and Settings available."""
        for stream_type, tab in self.content_tabs.items():
            self.tab_widget.setTabVisible(
                self.tab_widget.indexOf(tab),
                self.content_enabled[stream_type]
            )
            history_group = getattr(self, "history_groups", {}).get(stream_type)
            if history_group is not None:
                history_group.setVisible(self.content_enabled[stream_type])
        history_index = self.tab_widget.indexOf(self.history_tab)
        self.tab_widget.setTabVisible(
            history_index, any(self.content_enabled.values())
        )

    def clear_active_history(self):
        """Clear playback history for the active account after confirmation."""
        if not self.history_file:
            return
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Question)
        dialog.setWindowTitle("Clear history")
        dialog.setText("Clear all playback history for the active account?")
        dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        dialog.setDefaultButton(QMessageBox.No)
        self._prepare_dialog_theme(dialog)
        if dialog.exec_() == QMessageBox.Yes:
            clear_history(self.history_file)
            self.refresh_history_tab()

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
        self.internal_resume_behavior = dialog.resume_behavior.currentData() or DEFAULT_RESUME_BEHAVIOR
        self.save_internal_player_settings()

        if self._embedded_player_command_queue is not None:
            self._embedded_player_command_queue.put({
                'command': 'control_steps',
                'seek_seconds': self.internal_seek_step_seconds,
                'volume_percent': self.internal_volume_step_percent,
                'speed_step': self.internal_speed_step,
                'audio_language': self.internal_audio_language,
                'subtitle_language': self.internal_subtitle_language,
                'resume_behavior': self.internal_resume_behavior,
            })

    def save_internal_player_settings(self):
        """Persist internal-player controls without replacing unrelated settings."""
        try:
            save_internal_player_preferences(
                self.user_data_file,
                InternalPlayerPreferences(
                    seek_step_seconds=self.internal_seek_step_seconds,
                    volume_step_percent=self.internal_volume_step_percent,
                    speed_step=self.internal_speed_step,
                    audio_language=self.internal_audio_language,
                    subtitle_language=self.internal_subtitle_language,
                    resume_behavior=self.internal_resume_behavior,
                ),
            )
        except OSError as error:
            print(f"Could not save internal player settings: {error}")

    def load_default_internal_player_settings(self):
        """Load bounded control steps so manual INI edits remain safe."""
        preferences = load_internal_player_preferences(self.user_data_file)
        self.internal_seek_step_seconds = preferences.seek_step_seconds
        self.internal_volume_step_percent = preferences.volume_step_percent
        self.internal_speed_step = preferences.speed_step
        self.internal_audio_language = preferences.audio_language
        self.internal_subtitle_language = preferences.subtitle_language
        self.internal_resume_behavior = preferences.resume_behavior

    def apply_network_settings(self, user_agent, connection_timeout, read_timeout,
                             live_status_timeout, live_status_retries,
                             stream_status_enabled, account_refresh_interval,
                             account_auto_refresh_enabled, catalog_cache_enabled,
                             catalog_cache_max_age_hours, detailed_logging_enabled,
                             history_size):
        """Apply and persist all advanced provider settings in one operation."""
        preferences = AdvancedPreferences(
            user_agent=user_agent or DEFAULT_USER_AGENT_HEADER,
            connection_timeout=connection_timeout,
            read_timeout=read_timeout,
            live_status_timeout=live_status_timeout,
            live_status_retries=live_status_retries,
            stream_status_enabled=stream_status_enabled,
            account_refresh_interval=account_refresh_interval,
            account_auto_refresh_enabled=account_auto_refresh_enabled,
            catalog_cache_enabled=catalog_cache_enabled,
            catalog_cache_max_age_hours=catalog_cache_max_age_hours,
            detailed_logging_enabled=detailed_logging_enabled,
            history_size=history_size,
        )

        try:
            save_advanced_preferences(self.user_data_file, preferences)
            self._apply_advanced_preferences(preferences)
            set_detailed_logging(detailed_logging_enabled)
            self.animate_progress(0, 100, "Network settings saved")
        except OSError as e:
            print(f"Could not write user data file: {e}")
            self.animate_progress(0, 100, f"Failed saving network settings: {e}", "error")

    def load_default_network_options(self):
        """Load and apply the persisted Advanced settings snapshot."""
        try:
            self._apply_advanced_preferences(
                load_advanced_preferences(self.user_data_file)
            )
        except Exception as e:
            print(f"Failed loading default timeout values: {e}")

    def _apply_advanced_preferences(self, preferences):
        """Apply advanced preferences to the UI and shared network runtime."""
        self.current_user_agent = preferences.user_agent
        NETWORK_SETTINGS.connection_timeout = preferences.connection_timeout
        NETWORK_SETTINGS.read_timeout = preferences.read_timeout
        NETWORK_SETTINGS.live_status_timeout = preferences.live_status_timeout
        NETWORK_SETTINGS.live_status_retries = preferences.live_status_retries
        self.stream_status_enabled = preferences.stream_status_enabled
        self.account_info_refresh_interval = preferences.account_refresh_interval
        self.account_info_auto_refresh_enabled = (
            preferences.account_auto_refresh_enabled
        )
        self.catalog_cache_enabled = preferences.catalog_cache_enabled
        self.catalog_cache_max_age_hours = preferences.catalog_cache_max_age_hours
        self.detailed_logging_enabled = preferences.detailed_logging_enabled
        self.history_size = preferences.history_size
        self._apply_stream_status_visibility()
        self._update_account_info_timer()

    def check_for_updates(self, enable_update_msg):
        try:
            print("Checking for updates")
            release = fetch_latest_release(
                GITHUB_REPO, NETWORK_SETTINGS.connection_timeout
            )

            # Only prompt when upstream is strictly newer than what we're running —
            # avoids a spurious "update available" dialog for fork/dev builds that
            # carry a higher version number.
            if is_newer_version(release.version, CURRENT_VERSION):
                update_dialog = QMessageBox(self)
                update_dialog.setIcon(QMessageBox.Question)
                update_dialog.setWindowTitle('Update Available')
                update_dialog.setText(
                    f"A new version ({release.version}) is available.\n"
                    "Do you want to visit the download page?"
                )
                update_dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                update_dialog.setDefaultButton(QMessageBox.Yes)
                self._prepare_dialog_theme(update_dialog)
                reply = update_dialog.exec_()

                if reply == QMessageBox.Yes:
                    QDesktopServices.openUrl(QUrl(release.download_page))

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
        save_auto_update_preference(self.user_data_file, bool(state))

    def load_default_auto_update(self):
        enabled = load_auto_update_preference(self.user_data_file)
        if enabled is None:
            enabled = True
            try:
                save_auto_update_preference(self.user_data_file, enabled)
            except OSError as e:
                print(f"Could not write user data file: {e}")

        if enabled:
            self.auto_update_checkbox.setCheckState(Qt.Checked)
            self.check_for_updates(False)

    def init_progress_bar(self):
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setFixedHeight(25)
        self.progress_bar.setTextVisible(True)
        self.set_progress_state("busy")

        self.playlist_progress_animation = QPropertyAnimation(self.progress_bar, b"value")
        self.playlist_progress_animation.setDuration(1000)  # longer duration for smoother animation
        self.playlist_progress_animation.setEasingCurve(QEasingCurve.InOutQuad)
        self._progress_animation_final_state = "success"
        self.playlist_progress_animation.finished.connect(
            self._finish_progress_animation
        )

    def load_data_at_startup(self):
        self.load_default_internal_player_settings()

        self.external_player_command = self.load_external_player_command()
        self._refresh_current_player_label()

        self.load_default_sorting_order()

        self._load_hidden_categories()

        self.load_default_content()

        self.load_default_auto_update()

        self.load_default_theme()

        # Load network and cache preferences before startup credentials can begin
        # provider requests in the background.
        self.load_default_network_options()

    def load_startup_credentials(self):
        # Load playlist on startup if enabled. A malformed/missing key here used to crash
        # the app right after the login screen (issue #92), so every access is guarded.
        try:
            selected_startup_account = load_startup_account(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError) as e:
            print(f"Failed reading user data file at startup: {e}")
            return

        if not selected_startup_account or selected_startup_account == 'None':
            return

        try:
            if not self.activate_saved_account(selected_startup_account):
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
        dialog.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
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
        try:
            save_theme_preference(self.user_data_file, theme_name)
        except OSError as e:
            print(f"Could not write user data file: {e}")

    def load_default_theme(self):
        mode = load_theme_preference(self.user_data_file)
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

    def toggle_content_type(self, stream_type, state):
        """Persist one content choice and immediately update tab visibility."""
        was_enabled = self.content_enabled[stream_type]
        is_enabled = bool(state)
        self.content_enabled[stream_type] = is_enabled
        self._apply_content_visibility()

        try:
            current = load_provider_preferences(self.provider_preferences_file)
            save_provider_preferences(
                self.provider_preferences_file,
                current.get('hidden_categories', {}),
                current.get('category_sorting', {}),
                self.content_enabled,
            )
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
        """Update progress without dispatching queued input or worker callbacks.

        Callers may be rebuilding Qt lists. Entering processEvents here would
        allow another callback to replace those lists halfway through the update.
        """
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

    def _finish_progress_animation(self):
        """Apply the success or failure color selected by animate_progress()."""
        self.set_progress_state(self._progress_animation_final_state)

    def login(self):
        self.set_progress_bar(0, "Logging in...")

        for tab_name, list_widget in self.streaming_list_widgets.items():
            list_widget.clear()

        for tab_name, list_widget in self.category_list_widgets.items():
            list_widget.clear()

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

        self.fetch_data_thread()

        self.set_progress_bar(0, "Going to fetch data...")

    def fetch_data_thread(self, force_refresh=False):
        logging.debug(
            "Catalog load requested: account_id=%s; force_refresh=%s; cache=%s",
            self.active_account_id or "none",
            force_refresh,
            self.catalog_cache_enabled,
        )
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
        self._catalog_request_generation += 1
        dataWorker.signals.request_generation = self._catalog_request_generation
        dataWorker.signals.finished.connect(self.process_data)
        dataWorker.signals.error.connect(self.on_fetch_data_error)
        dataWorker.signals.progress_bar.connect(self._catalog_progress)
        dataWorker.signals.show_error_msg.connect(self._catalog_error_message)
        dataWorker.signals.show_info_msg.connect(self._catalog_info_message)
        self.threadpool.start(dataWorker)

    def _current_catalog_signal(self):
        """Return whether a worker signal belongs to the selected account request."""
        generation = getattr(self.sender(), 'request_generation', None)
        return (
            generation is None
            or generation == self._catalog_request_generation
        )

    def _catalog_progress(self, start, end, text):
        if self._current_catalog_signal():
            self.animate_progress(start, end, text)

    def _catalog_error_message(self, title, message):
        if self._current_catalog_signal():
            self.show_error_msg(title, message)

    def _catalog_info_message(self, title, message):
        if self._current_catalog_signal():
            self.show_info_msg(title, message)

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

    def _on_current_tab_changed(self, index):
        """Apply tab-specific refresh and temporary sorting behavior."""
        logging.debug("Active tab changed: %s", self.tab_widget.tabText(index))
        if hasattr(self, 'category_search_bars'):
            stream_type = self.tab_widget.tabText(index)
            if stream_type in ('LIVE', 'Movies', 'Series'):
                self._restore_default_sorting_for_tab(stream_type)

        self._update_account_info_timer()
        if self._is_info_tab_visible():
            # Entering Info should show the current connection count immediately;
            # disabling auto-refresh affects only subsequent periodic requests.
            self.refresh_account_info()

    def _restore_default_sorting_for_tab(self, stream_type):
        """Discard temporary list sorting when a content tab is entered again."""
        if self.remember_category_sorting:
            return

        default_sorting = (self.sorting_enabled, self.sorting_order)
        category_search = self.category_search_bars[stream_type]
        streaming_search = self.streaming_search_bars[stream_type]
        category_needs_reset = (
            getattr(category_search, 'current_sorting', default_sorting)
            != default_sorting
        )
        streaming_needs_reset = (
            getattr(streaming_search, 'current_sorting', default_sorting)
            != default_sorting
        )

        if category_needs_reset:
            category_search.current_sorting = default_sorting
            if category_search.text():
                self.search_in_list(
                    'category', stream_type, category_search.text()
                )
            else:
                self.sort_list(
                    category_search,
                    'category',
                    stream_type,
                    self.category_list_widgets,
                    *default_sorting,
                )

        if not streaming_needs_reset:
            return
        streaming_search.current_sorting = default_sorting

        # Rebuild top-level content from its category source before applying a
        # default; the visible list currently holds a temporary order.
        is_top_level = stream_type != 'Series' or self.series_navigation_level == 0
        if is_top_level:
            category_name, category_id = self._selected_category(stream_type)
            prepared_entries = self._entries_for_category_view(
                stream_type, category_name, category_id
            )
            self.currently_loaded_streams[stream_type] = list(prepared_entries)
            self.active_category_view_key[stream_type] = self._category_view_key(
                stream_type, category_name, category_id
            )

        if streaming_search.text():
            self.search_in_list('streaming', stream_type, streaming_search.text())
        else:
            self.sort_list(
                streaming_search,
                'streaming',
                stream_type,
                self.streaming_list_widgets,
                *default_sorting,
            )

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
        """Install the current request's catalog and rebuild its visible lists.

        This GUI-thread transaction invalidates both data and Qt-item caches.
        Do not pump the event loop here: callbacks must see a complete snapshot.
        """
        if not self._current_catalog_signal():
            logging.debug("Ignoring catalog result from a previously selected account")
            return
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

        # Process categories and entries
        hidden_categories_changed = False
        for stream_type in self.entries_per_stream_type.keys():
            self.category_list_widgets[stream_type].clear()
            self.streaming_list_widgets[stream_type].clear()

            # A reload replaces the previous snapshot. Clearing these search sources
            # prevents duplicate and stale results after a content type is re-enabled.
            self.currently_loaded_streams[stream_type] = []
            self.currently_loaded_categories[stream_type] = []

            # Disabled types contain no newly requested data and stay out of the UI.
            if not self.content_enabled[stream_type]:
                continue

            # Fill currently loaded streams with current stream data
            for entry in self._entries_in_visible_categories(stream_type):
                self.currently_loaded_streams[stream_type].append(entry)

            # Remove exclusions for categories the current provider no longer sends.
            # Exclusions live in the account's preferences JSON; disabled content
            # types are skipped because their categories were not fetched.
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

            num_of_categories = len(visible_categories)
            prev_perc = 0
            for idx, category_item in enumerate(visible_categories):
                item = self._new_category_item(stream_type, category_item)

                self.category_list_widgets[stream_type].addItem(item)

                perc = (idx * 100) / max(1, num_of_categories)
                if (perc - prev_perc) > 10:
                    prev_perc = perc
                    self.set_progress_bar(int(perc), f"Loading {stream_type} categories: {idx} of {num_of_categories}")

            # Sort each first column with its remembered order when that mode is active.
            category_list_enabled, category_list_order = (
                self._sorting_for_category_list(stream_type)
            )
            self.sort_list(
                self.category_search_bars[stream_type], 'category', stream_type,
                self.category_list_widgets, category_list_enabled,
                category_list_order
            )

            # Build the stream list once in its final order. Keep queued UI events
            # outside this transaction so they only observe a complete catalog.
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

        if self.history_file:
            repair_misclassified_history(
                self.history_file,
                (
                    entry.get("stream_id")
                    for entry in self.entries_per_stream_type.get("LIVE", [])
                ),
                (
                    entry.get("stream_id")
                    for entry in self.entries_per_stream_type.get("Movies", [])
                ),
            )
            self.refresh_history_tab()

        self._catalog_loaded = True
        self.set_progress_bar(100, f"Finished loading")
        if self.external_player_command == INTERNAL_VLC_COMMAND:
            QTimer.singleShot(0, self._prewarm_embedded_player)

    def on_fetch_data_error(self, error_msg):
        if not self._current_catalog_signal():
            return
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
        movie_img_url = vod_info.get('movie_image', 0)

        self.fetch_image(movie_img_url, 'Movies')

        # If vod data is valid
        if vod_data:
            movie_name = vod_info.get('name', vod_data.get('name', 'No name Available...'))

            # If movie name is an empty string
            if not movie_name:
                movie_name = vod_data.get('name', 'No name Available...')

                if not movie_name:
                    movie_name = 'No name Available...'
        else:
            movie_name = vod_info.get('name', 'No name Available...')

        self.movies_info_box.name.setText(f"{movie_name}")
        self.movies_info_box.release_date.setText(f"Release date: {vod_info.get('releasedate') or '—'}")
        self.movies_info_box.country.setText(f"Country: {vod_info.get('country') or '—'}")
        self.movies_info_box.genre.setText(f"Genre: {vod_info.get('genre') or '—'}")
        self.movies_info_box.duration.setText(f"Duration: {vod_info.get('duration') or '—'}")
        self.movies_info_box.rating.setText(f"Rating: {vod_info.get('rating') or '—'}")
        self.movies_info_box.director.setText(f"Director: {vod_info.get('director') or '—'}")
        self.movies_info_box.cast.setText(f"Cast: {vod_info.get('actors') or '—'}")
        self.movies_info_box.description.setText(f"Description: {vod_info.get('description') or '—'}")

        yt_code = vod_info.get('youtube_trailer', 0)
        if yt_code:
            self.movies_info_box.yt_code = yt_code

            self.movies_info_box.trailer.setEnabled(True)
        else:
            self.movies_info_box.yt_code = None

            self.movies_info_box.trailer.setEnabled(False)

        tmdb_code = vod_info.get('tmdb_id', 0)
        if tmdb_code:
            self.movies_info_box.tmdb_code = tmdb_code

            self.movies_info_box.tmdb.setEnabled(True)
        else:
            self.movies_info_box.tmdb_code = None

            self.movies_info_box.tmdb.setEnabled(False)

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
        """Populate seasons for an open request, or update the series info panel.

        The episodes mapping is retained by season for later navigation without
        another provider request.
        """
        if not series_info_data:
            self.animate_progress(0, 100, "Failed fetching series info", "error")
            return

        if is_show_request:
            self.streaming_list_widgets['Series'].clear()

            self.streaming_list_widgets['Series'].scrollToTop()

            go_back_item = QListWidgetItem(self.go_back_text)
            go_back_item.setIcon(self.go_back_icon)
            self.streaming_list_widgets['Series'].addItem(go_back_item)

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
                item = QListWidgetItem(f"Season {season}")

                item.setData(Qt.UserRole, series_info_data['episodes'][season])

                self.streaming_list_widgets['Series'].addItem(item)

            pending = self._pending_history_series
            if isinstance(pending, dict):
                self._pending_history_series = None
                episode_found = False
                season_key = str(pending.get("season", ""))
                episodes = series_info_data['episodes'].get(season_key)
                if episodes is None:
                    try:
                        episodes = series_info_data['episodes'].get(int(season_key))
                    except (TypeError, ValueError):
                        episodes = None
                if episodes is not None:
                    self.current_series_season = season_key
                    self.series_navigation_level = 2
                    self.show_episodes(episodes)
                    episode_id = str(pending.get("stream_id", ""))
                    episode_list = self.streaming_list_widgets['Series']
                    for row in range(episode_list.count()):
                        episode_item = episode_list.item(row)
                        episode_data = episode_item.data(Qt.UserRole)
                        if (
                            isinstance(episode_data, dict)
                            and str(episode_data.get("id", "")) == episode_id
                        ):
                            episode_list.setCurrentItem(episode_item)
                            episode_list.scrollToItem(episode_item)
                            episode_found = True
                            break
                if not episode_found:
                    self._remove_unavailable_history_entry(pending)

            self.animate_progress(0, 100, "Loading finished")

        # Otherwise request came from single click to show only series info
        else:
            series_info = series_info_data['info']

            series_img_url = series_info.get('cover', 0)

            self.fetch_image(series_img_url, 'Series')

            series_name = series_info.get('name', 'No name Available...')
            if not series_name:
                # If series name is empty set replacement
                series_name = 'No name Available...'

            # Build the seasons list naturally — `", ".join(...)` avoids the trailing
            # comma the previous code left behind ("Seasons: 1," → "Seasons: 1").
            season_keys = [str(k) for k in series_info_data['episodes'].keys()]
            seasons = ", ".join(season_keys) if season_keys else "—"

            release_date    = series_info.get('releaseDate')   or "—"
            genre           = series_info.get('genre')         or "—"
            duration        = series_info.get('episode_run_time')
            rating          = series_info.get('rating')
            director        = series_info.get('director')      or "—"
            cast            = series_info.get('cast')          or "—"
            plot            = series_info.get('plot')          or "—"

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

            yt_code = series_info.get('youtube_trailer', 0)
            if yt_code:
                self.series_info_box.yt_code = yt_code

                self.series_info_box.trailer.setEnabled(True)
            else:
                self.series_info_box.yt_code = None

                self.series_info_box.trailer.setEnabled(False)

            tmdb_code = series_info.get('tmdb', 0)
            if tmdb_code:
                self.series_info_box.tmdb_code = tmdb_code

                self.series_info_box.tmdb.setEnabled(True)
            else:
                self.series_info_box.tmdb_code = None

                self.series_info_box.tmdb.setEnabled(False)

            if not series_info:
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
                self.series_info_box.cover.setPixmap(image.scaledToWidth(self.series_info_box.maxCoverWidth))
            elif stream_type == 'Movies':
                self.movies_info_box.cover.setPixmap(image.scaledToWidth(self.movies_info_box.maxCoverWidth))
            elif stream_type == 'Live':
                self.live_info_box.cover.setPixmap(image.scaledToWidth(self.live_info_box.maxCoverHeight))
        except Exception as e:
            print(f"Failed processing image: {e}")

    def favorite_button_pressed(self, stream_type, info_box):
        """Toggle a catalog favorite and invalidate the affected Favorites views.

        Nested Series rows describe seasons or episodes, so the target is their
        parent series. Removing it while browsing Favorites returns to that root.
        """
        try:
            current_sel_item = self.streaming_list_widgets[stream_type].currentItem()

            nested_series = (
                stream_type == "Series" and self.series_navigation_level != 0
            )
            if nested_series:
                # The information panel describes the parent series, not the
                # selected season, episode, or Go back navigation row.
                data = self.current_series_entry
            elif current_sel_item is not None:
                data = current_sel_item.data(Qt.UserRole)
            else:
                return

            if not data:
                return

            if stream_type == "Series":
                stream_id = data.get('series_id', -1)
            else:
                stream_id = data.get('stream_id', -1)

            is_fav = False

            for idx, entry in enumerate(self.entries_per_stream_type[stream_type]):
                if entry['stream_id' if not (stream_type == "Series") else 'series_id'] == stream_id:
                    is_fav = self.entries_per_stream_type[stream_type][idx].get('favorite', False)

                    is_fav = not is_fav

                    self.entries_per_stream_type[stream_type][idx]['favorite'] = is_fav

            # Change fav button colour
            info_box.set_favorite(is_fav)
            
            data['favorite'] = is_fav

            if not nested_series:
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

            # Selection identifies the visible category even when searching or
            # navigating has invalidated its cache key.
            category_name, _ = self._selected_category(stream_type)
            if category_name == self.fav_categories_text:
                if nested_series:
                    self.active_category_view_key[stream_type] = None
                    # Refresh the root source for both additions and removals.
                    # A removal also leaves the nested view below.
                    self.currently_loaded_streams[stream_type] = list(
                        self._entries_for_category_view(
                            stream_type, self.fav_categories_text
                        )
                    )
                    if not is_fav:
                        # Use normal category navigation to restore the Favorites
                        # root, including its sorting, cache, and keyboard state.
                        category_list = self.category_list_widgets[stream_type]
                        category_item = category_list.currentItem()
                        self.prev_clicked_category_item[stream_type] = None
                        category_list.itemClicked.emit(category_item)
                if not is_fav and not nested_series:
                    # The selected row no longer belongs in the visible Favorites
                    # view. Remove it immediately instead of making the user leave
                    # the category and return before the invalidated cache is seen.
                    list_widget = self.streaming_list_widgets[stream_type]
                    removed_row = list_widget.currentRow()
                    removed_item = list_widget.takeItem(removed_row)
                    del removed_item
                    self.currently_loaded_streams[stream_type] = [
                        entry
                        for entry in self.currently_loaded_streams[stream_type]
                        if entry.get(
                            'series_id' if stream_type == 'Series' else 'stream_id'
                        ) != stream_id
                    ]
                    self.prev_clicked_streaming_item = 0
                    if list_widget.count() == 0:
                        list_widget.addItem("No items in list...")

                    # The attached rows now represent the newly computed Favorites
                    # view and may safely be cached when another category is opened.
                    self.active_category_view_key[stream_type] = (
                        self._category_view_key(
                            stream_type, self.fav_categories_text
                        )
                    )

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
        cache_key = self._category_view_key(
            stream_type, category_name, category_id
        )

        stream_cache = self.category_view_cache[stream_type]
        cached_entries = stream_cache.get(cache_key)
        if cached_entries is not None:
            return cached_entries

        prepared_entries = self._raw_entries_for_category(
            stream_type, category_name, category_id
        )

        sorting_enabled, sort_order = self._sorting_for_category(
            stream_type, category_name, category_id
        )
        prepared_entries = ordered_catalog_entries(
            prepared_entries,
            sorting_enabled,
            descending=(sort_order == 1),
        )

        stream_cache[cache_key] = prepared_entries
        return prepared_entries

    def _raw_entries_for_category(self, stream_type, category_name, category_id=None):
        """Return a fresh category list in provider or favorite insertion order."""
        if category_name == self.fav_categories_text:
            return self._favorites_in_user_order(stream_type)
        if category_name == self.all_categories_text:
            return self._entries_in_visible_categories(stream_type)
        return [
            entry for entry in self.entries_per_stream_type[stream_type]
            if entry.get('category_id') == category_id
        ]

    def category_item_clicked(self, clicked_item):
        """Open a category using its cached rows or rebuild them from catalog data.

        The emitting list identifies the content type. Only complete root views
        can be cached; search results and nested Series rows are discarded.
        """
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

            if selected_item == self.prev_clicked_category_item[stream_type]:
                return

            self.prev_clicked_category_item[stream_type] = selected_item

            selected_item_data = selected_item.data(Qt.UserRole) or {}
            selected_item_text = selected_item_data.get(
                'category_name', selected_item.text()
            )
            logging.debug(
                "Category selected: type=%s; name=%r; id=%s",
                stream_type,
                selected_item_text,
                selected_item_data.get('category_id', 'synthetic'),
            )

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

            list_widget.scrollToTop()

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

        self.live_info_box.stream_status.setPixmap(
            self.status_pixmap(self.path_to_unknown_status_icon, 24)
        )

    def process_stream_status(self, stream_id, stream_status):
        try:
            # Ensure user hasn't changed live channel before request came through
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
        epg_worker = EPGWorker(self.server, self.username, self.password, stream_id, self)

        epg_worker.signals.finished.connect(self.process_epg_data)
        epg_worker.signals.error.connect(self.on_epg_fetch_error)

        self.threadpool.start(epg_worker)

    def on_epg_fetch_error(self, error_msg):
        print(f"Failed fetching EPG data: {error_msg}")
        self.set_progress_bar(100, "Failed loading EPG data", "error")

        item = QTreeWidgetItem(["--/--/----", "--:--", "--:--", "Failed loading EPG data..."])
        self.live_info_box.live_EPG_info.addTopLevelItem(item)

    def process_epg_data(self, epg_data):
        try:
            self.live_info_box.live_EPG_info.clear()

            if not epg_data:
                item = QTreeWidgetItem(["--/--/----", "--:--", "--:--", "No EPG Data Available..."])

                self.live_info_box.live_EPG_info.addTopLevelItem(item)

                self.set_progress_bar(100, "No EPG data")
                return

            current_timestamp = time.mktime(datetime.now().timetuple())

            items = []

            for epg_entry in epg_data:
                start_timestamp = epg_entry['start_time']
                stop_timestamp  = epg_entry['stop_time']
                program_name    = epg_entry['program_name']
                description     = epg_entry['description']
                date            = epg_entry['date']

                # Convert timestamps to string in correct format
                start_time = start_timestamp.strftime("%H:%M")
                stop_time = stop_timestamp.strftime("%H:%M")

                # Convert stop time to unix timebase so it can be used for calculating
                unix_stop_time = time.mktime(stop_timestamp.timetuple())

                # Compute time difference
                time_diff = unix_stop_time - current_timestamp

                if time_diff >= 0:
                    item    = QTreeWidgetItem([date, start_time, stop_time, program_name])
                    label   = QLabel(description)
                    label.setWordWrap(True)
                    desc    = QTreeWidgetItem()
                    item.addChild(desc)

                    self.live_info_box.live_EPG_info.setItemWidget(desc, 3, label)

                    items.append(item)

            self.live_info_box.live_EPG_info.addTopLevelItems(items)

            self.set_progress_bar(100, "Loaded EPG data")

        except Exception as e:
            print(f"Failed processing EPG: {e}")
            self.set_progress_bar(100, "Failed processing EPG data", "error")

    def streaming_item_clicked(self, clicked_item):
        """Refresh the selected title's information panel without starting playback."""
        try:

            if not clicked_item:
                return

            if (clicked_item == self.prev_clicked_streaming_item):
                return

            self.prev_clicked_streaming_item = clicked_item

            clicked_item_data = clicked_item.data(Qt.UserRole)

            # Season rows contain episode lists rather than stream dictionaries.
            # They have no top-level metadata to display on a single click.
            if not isinstance(clicked_item_data, dict):
                return

            is_fav = clicked_item_data.get('favorite', False)

            stream_type = clicked_item_data.get('stream_type', '')

            # Skip when back button or already loaded series info
            if clicked_item.text() == self.go_back_text or ('series' in stream_type and self.series_navigation_level > 0):
                return

            if 'live' in stream_type:
                self.set_progress_bar(0, "Loading EPG data")

                self.live_info_box.set_favorite(is_fav)

                self.live_info_box.EPG_box_label.setText(f"{clicked_item_data['name']}")

                self.live_info_box.stream_status.setPixmap(
                    self.status_pixmap(self.path_to_unknown_status_icon, 25)
                )

                self.live_info_box.live_EPG_info.clear()
                item = QTreeWidgetItem(["...", "...", "...", "Loading EPG Data..."])
                self.live_info_box.live_EPG_info.addTopLevelItem(item)

                self.fetch_image(clicked_item_data['stream_icon'], 'Live')

                self.start_online_worker(clicked_item_data['stream_id'], clicked_item_data['url'])

                self.start_epg_worker(clicked_item_data['stream_id'])

            elif 'movie' in stream_type:
                self.set_progress_bar(0, "Loading Movie info")

                self.movies_info_box.set_favorite(is_fav)

                self.movies_info_box.cover.setPixmap(QPixmap(self.path_to_loading_img).scaledToWidth(self.series_info_box.maxCoverWidth))

                self.movies_info_box.name.setText(f"{clicked_item_data['name']}")
                self.movies_info_box.release_date.setText(f"Release date: ...")
                self.movies_info_box.country.setText(f"Country: ...")
                self.movies_info_box.genre.setText(f"Genre: ...")
                self.movies_info_box.duration.setText(f"Duration: ...")
                self.movies_info_box.rating.setText(f"Rating: ...")
                self.movies_info_box.director.setText(f"Director: ...")
                self.movies_info_box.cast.setText(f"Cast: ...")
                self.movies_info_box.description.setText(f"Description: ...")

                self.movies_info_box.yt_code = None
                self.movies_info_box.tmdb_code = None

                self.movies_info_box.trailer.setEnabled(False)
                self.movies_info_box.tmdb.setEnabled(False)

                self.fetch_vod_info(clicked_item_data['stream_id'])

            elif 'series' in stream_type:
                if (self.series_navigation_level != 0):
                    return

                self.set_progress_bar(0, "Loading Series info")

                self.series_info_box.set_favorite(is_fav)

                self.series_info_box.cover.setPixmap(QPixmap(self.path_to_loading_img).scaledToWidth(self.series_info_box.maxCoverWidth))

                self.series_info_box.name.setText(f"{clicked_item_data['name']}")
                self.series_info_box.release_date.setText(f"Release date: ...")
                self.series_info_box.genre.setText(f"Genre: ...")
                self.series_info_box.num_seasons.setText(f"Seasons: ...")
                self.series_info_box.duration.setText(f"Episode duration: ... min")
                self.series_info_box.rating.setText(f"Rating: ...")
                self.series_info_box.director.setText(f"Director: ...")
                self.series_info_box.cast.setText(f"Cast: ...")
                self.series_info_box.description.setText(f"Description: ...")

                self.series_info_box.yt_code = None
                self.series_info_box.tmdb_code = None

                self.series_info_box.trailer.setEnabled(False)
                self.series_info_box.tmdb.setEnabled(False)

                self.fetch_series_info(clicked_item_data['series_id'], False)

        except Exception as e:
            print(f"Failed item single click: {e}")

    def streaming_item_double_clicked(self, clicked_item):
        """Play a channel/movie/episode or move through the Series hierarchy."""
        try:

            if not clicked_item:
                return

            clicked_item_text = clicked_item.text()
            clicked_item_data = clicked_item.data(Qt.UserRole)

            if not clicked_item_data and clicked_item_text != self.go_back_text:
                return

            # Try to get stream type from item data
            try:
                stream_type = clicked_item_data['stream_type']
            except (KeyError, TypeError):
                stream_type = ''

            # Prevent loading the same series navigation levels multiple times
            if 'series' in stream_type and self.series_navigation_level < 2 and clicked_item == self.prev_double_clicked_streaming_item:
                return

            print(f"stream_type: {stream_type}")

            self.prev_double_clicked_streaming_item = clicked_item

            # LIVE and Movies are always root-level entries. A nested Series view
            # must not affect how another tab classifies or launches its items.
            if 'live' in stream_type or 'movie' in stream_type:
                history_type = "LIVE" if 'live' in stream_type else "Movies"
                self.play_item(
                    clicked_item_data['url'],
                    clicked_item_data.get('name', clicked_item_text),
                    self._history_metadata(
                        history_type, clicked_item_data, clicked_item_text
                    ),
                )
                return

            # Series actions depend on the current show/season/episode level.
            match self.series_navigation_level:
                case 0:  # Highest level, either LIVE, VOD or series
                    if clicked_item_text == self.go_back_text:
                        return

                    if 'series' in stream_type:
                        self.current_series_entry = clicked_item_data
                        self.series_navigation_level = 1
                        self.show_seasons(clicked_item_data)

                case 1:  # Series seasons
                    if clicked_item_text == self.go_back_text:
                        self.series_navigation_level = 0
                        self.go_back_to_level(self.series_navigation_level)
                        
                    else:
                        self.current_series_season = clicked_item_text.removeprefix(
                            "Season "
                        )
                        self.series_navigation_level = 2
                        self.show_episodes(clicked_item_data)

                case 2:  # Series episodes
                    if clicked_item_text == self.go_back_text:
                        self.series_navigation_level = 1
                        self.go_back_to_level(self.series_navigation_level)
                        
                    else:
                        # Play episode
                        self.play_item(
                            clicked_item_data['url'],
                            clicked_item_data.get('title', clicked_item_text),
                            self._history_metadata(
                                "Series", clicked_item_data, clicked_item_text
                            ),
                        )

        except Exception as e:
            print(f"failed item double click: {e}")

    def streaming_item_keyboard_activated(self, item):
        """Apply the normal selection work, then open or play the chosen entry."""
        self.streaming_item_clicked(item)
        self.streaming_item_double_clicked(item)

    def go_back_to_level(self, series_navigation_level):
        """Rebuild the parent Series view from the retained root or season data."""
        self.set_progress_bar(0, "Loading items")

        self.streaming_list_widgets['Series'].clear()

        self.streaming_list_widgets['Series'].scrollToTop()

        if series_navigation_level == 0:  # From seasons back to series list
            for entry in self.currently_loaded_streams['Series']:
                item = QListWidgetItem(entry['name'])
                item.setData(Qt.UserRole, entry)

                self.streaming_list_widgets['Series'].addItem(item)

        elif series_navigation_level == 1:  # From episodes back to seasons list
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

        self.fetch_series_info(seasons_data['series_id'], True)

    def show_episodes(self, episodes_data):
        self.set_progress_bar(0, "Loading items")

        self.streaming_list_widgets['Series'].clear()

        self.streaming_list_widgets['Series'].scrollToTop()

        go_back_item = QListWidgetItem(self.go_back_text)
        go_back_item.setIcon(self.go_back_icon)
        self.streaming_list_widgets['Series'].addItem(go_back_item)

        self.currently_loaded_streams['Episodes'].clear()

        for episode in episodes_data:
            item = QListWidgetItem(f"{episode['title']}")

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
            episode['url'] = playable_url

            item.setData(Qt.UserRole, episode)

            self.currently_loaded_streams['Episodes'].append(episode)

            self.streaming_list_widgets['Series'].addItem(item)

        self.animate_progress(0, 100, "Loading finished")

    def _history_metadata(self, stream_type, data, fallback_title=""):
        """Build safe history metadata without including a provider URL."""
        # Identity excludes the source category: the same episode opened through
        # Favorites or All updates one history row, retaining its newest origin.
        if not isinstance(data, dict):
            return None
        stream_id = data.get("stream_id") or data.get("id")
        title = data.get("title") or data.get("name") or fallback_title
        if not stream_id or not title:
            return None
        metadata = {
            "key": f"{stream_type}:{stream_id}",
            "type": stream_type,
            "title": str(title),
            "stream_id": str(stream_id),
            "container_extension": data.get("container_extension", ""),
            "account_id": self.active_account_id,
        }
        category_name, category_id = self._selected_category(stream_type)
        metadata.update({
            "source_category_name": str(category_name or ""),
            "source_category_id": str(category_id or ""),
        })
        if stream_type == "Series" and self.current_series_entry:
            metadata.update({
                "series_id": str(self.current_series_entry.get("series_id", "")),
                "series_title": str(self.current_series_entry.get("name", "")),
                "series_category_id": str(
                    self.current_series_entry.get("category_id", "")
                ),
                "season": str(data.get("season", self.current_series_season or "")),
            })
        return metadata

    def _record_history_access(self, entry):
        """Move one playback entry to the top while preserving resume progress."""
        if not self.history_file or not isinstance(entry, dict):
            return entry
        merged = self._history_with_saved_progress(entry)
        merged["last_viewed"] = datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            record_history(self.history_file, merged, self.history_size)
            self.refresh_history_tab()
        except OSError as error:
            logging.warning("Could not update playback history: %s", error)
        return merged

    def _history_with_saved_progress(self, entry):
        """Merge safe catalog metadata with an existing playback position."""
        if not self.history_file or not isinstance(entry, dict):
            return entry
        previous = next(
            (
                item for item in load_history(self.history_file)
                if item.get("key") == entry.get("key")
            ),
            {},
        )
        merged = dict(previous)
        merged.update(entry)
        return merged

    def _choose_resume_position(self, entry):
        """Apply the configured resume policy to one previously started item."""
        if entry.get("type") == "LIVE":
            return 0
        position_ms = resume_position(entry)
        if not position_ms or self.internal_resume_behavior == "restart":
            return 0
        if self.internal_resume_behavior == "resume":
            return position_ms

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Question)
        dialog.setWindowTitle("Resume playback")
        dialog.setText(
            f"Resume '{entry.get('title', '')}' from "
            f"{self._format_history_position(position_ms)}?"
        )
        resume_button = dialog.addButton("Resume", QMessageBox.AcceptRole)
        dialog.addButton("Restart", QMessageBox.DestructiveRole)
        dialog.addButton(QMessageBox.Cancel)
        dialog.setDefaultButton(resume_button)
        self._prepare_dialog_theme(dialog)
        dialog.exec_()
        if dialog.clickedButton() is resume_button:
            return position_ms
        if dialog.standardButton(dialog.clickedButton()) == QMessageBox.Cancel:
            return None
        return 0

    @staticmethod
    def _format_history_position(position_ms):
        seconds = max(0, int(position_ms) // 1000)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"

    def play_item(self, url, title="", history_entry=None):
        # Drain progress sent by the reusable player before deciding whether the
        # selected media has a resumable position.
        self._process_embedded_player_events()
        if not url:
            self.animate_progress(0, 100, "Stream URL not found", "error")

            error_dialog = QMessageBox()
            error_dialog.setIcon(QMessageBox.Warning)
            error_dialog.setWindowTitle("Invalid stream URL")
            error_dialog.setText(f"Invalid stream URL!\nPlease try again.\n\nURL: {url}")

            error_dialog.setStandardButtons(QMessageBox.Ok)

            error_dialog.exec_()
            return

        if self.external_player_command:
            try:
                history_entry = self._history_with_saved_progress(history_entry)
                print(f"Going to play: {private_url_log_reference(url)}")

                # Embedded VLC marker — short-circuit before constructing any subprocess
                # command. The marker is set when the user picks "Embedded VLC" in
                # Settings (so we don't store a real path that could be invoked by accident).
                if self.external_player_command == INTERNAL_VLC_COMMAND:
                    resume_ms = self._choose_resume_position(history_entry or {})
                    if resume_ms is None:
                        return
                    history_entry = self._record_history_access(history_entry)
                    self._play_embedded(url, history_entry, resume_ms)
                    return

                self.animate_progress(0, 100, "Loading player for streaming")
                history_entry = self._record_history_access(history_entry)
                launch_external_player(
                    self.external_player_command,
                    url,
                    user_agent=self.current_user_agent,
                    title=title,
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
            error_dialog = QMessageBox()
            error_dialog.setIcon(QMessageBox.Warning)
            error_dialog.setWindowTitle("No Media Player")
            error_dialog.setText("No media player configured!\nPlease configure a media player.")

            error_dialog.setStandardButtons(QMessageBox.Ok)

            error_dialog.exec_()

    def choose_external_player(self):
        # Open file dialog box in order to select media player program
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
                self._stop_embedded_player_process()

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
            self._stop_embedded_player_process()
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

        self.external_player_command = INTERNAL_VLC_COMMAND
        self.save_external_player_command()
        self._refresh_current_player_label()
        self.animate_progress(0, 100, "Internal VLC player enabled")
        QTimer.singleShot(0, self._prewarm_embedded_player)

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
        if cmd == INTERNAL_VLC_COMMAND:
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

    def _play_embedded(self, url, history_entry=None, resume_ms=0):
        try:
            playlist, current_idx, title = self._collect_visible_playlist(
                url, history_entry
            )
            saved_history = {
                entry.get("key"): entry
                for entry in load_history(self.history_file)
            } if self.history_file else {}
            for playlist_entry in playlist:
                metadata = playlist_entry.get("history")
                if not isinstance(metadata, dict):
                    continue
                previous = saved_history.get(metadata.get("key"), {})
                merged = dict(previous)
                merged.update(metadata)
                playlist_entry["history"] = merged
            if history_entry and 0 <= current_idx < len(playlist):
                playlist[current_idx]['history'] = history_entry
            self._ensure_embedded_player_process()
            if is_windows and self._embedded_player_process is not None:
                try:
                    # Windows restricts foreground activation across processes.
                    # Grant the isolated player permission immediately before play.
                    ctypes.windll.user32.AllowSetForegroundWindow(
                        self._embedded_player_process.pid
                    )
                except Exception:
                    pass
            self._embedded_player_command_queue.put({
                'command': 'play',
                'url': url,
                'title': title,
                'playlist': playlist,
                'index': current_idx,
                'history': history_entry,
                'resume_ms': resume_ms,
                'keep_above_main': self.keep_on_top_checkbox.isChecked(),
            })
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

        self._embedded_player_process = None
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
        environment['IPTV_PLAYER_RESUME_BEHAVIOR'] = self.internal_resume_behavior
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
            # Capture this process's listener and queue, not mutable instance
            # fields that may already refer to a replacement player process.
            connection = None
            try:
                connection = listener.accept()
                def receive_events():
                    try:
                        while True:
                            event = connection.recv()
                            if isinstance(event, dict):
                                self._embedded_player_event_queue.put(event)
                    except (EOFError, OSError):
                        pass
                    finally:
                        # Wake the sender if the child exits while no command is
                        # queued. Otherwise every restart leaks one waiting thread.
                        command_queue.put(None)

                threading.Thread(
                    target=receive_events,
                    name='EmbeddedPlayerEventReceiver',
                    daemon=True,
                ).start()
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

    def _process_embedded_player_events(self):
        """Persist player progress events on the main application's GUI thread."""
        history_changed = False
        while True:
            try:
                event = self._embedded_player_event_queue.get_nowait()
            except queue.Empty:
                break
            event_type = event.get("event")
            if event_type == "player_window_ready":
                self._activate_embedded_player_window(
                    event.get("window_id"),
                    event.get("keep_topmost", False),
                )
                continue
            if event_type != "history_progress":
                continue
            entry = event.get("history")
            if not isinstance(entry, dict):
                continue
            account_id = entry.get("account_id") or self.active_account_id
            # Playback can outlive an account switch. Persist to the originating
            # account and refresh History only if that account is still selected.
            if not account_id:
                continue
            filename = account_history_file(self.history_base_file, account_id)
            try:
                record_history(filename, entry, self.history_size)
                history_changed = history_changed or (
                    account_id == self.active_account_id
                )
            except OSError as error:
                logging.warning("Could not save playback progress: %s", error)
        if history_changed:
            self.refresh_history_tab()

    def _activate_embedded_player_window(self, window_id, keep_topmost=False):
        """Activate the independent player from the foreground main process."""
        if not is_windows or not window_id:
            return
        try:
            hwnd = int(window_id)
            user32 = ctypes.windll.user32
            flags = 0x0001 | 0x0002 | 0x0040  # NOSIZE | NOMOVE | SHOWWINDOW
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, flags)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            if not keep_topmost:
                user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, flags)
        except Exception as error:
            logging.debug("Could not activate internal player window: %s", error)

    def _close_embedded_player_listener(self):
        """Close resources left by an earlier isolated player instance."""
        command_queue = self._embedded_player_command_queue
        sender_thread = self._embedded_player_sender_thread
        if command_queue is not None:
            command_queue.put(None)
        if self._embedded_player_listener is not None:
            try:
                self._embedded_player_listener.close()
            except OSError:
                pass
        if (
            sender_thread is not None
            and sender_thread is not threading.current_thread()
        ):
            sender_thread.join(timeout=1.0)
        self._embedded_player_listener = None
        self._embedded_player_command_queue = None
        self._embedded_player_sender_thread = None

    def _stop_embedded_player_process(self):
        """Stop the isolated player when the main application exits."""
        if self._embedded_player_command_queue is not None:
            self._embedded_player_command_queue.put({'command': 'quit'})
            self._embedded_player_command_queue.put(None)
        process = self._embedded_player_process
        if process is not None and process.poll() is None:
            try:
                # Give the player time to report its final playback position before
                # falling back to a forced termination during application shutdown.
                process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                try:
                    process.terminate()
                except OSError:
                    pass
        self._process_embedded_player_events()
        self._embedded_player_process = None
        self._close_embedded_player_listener()

    def _collect_visible_playlist(self, url, history_entry=None):
        # Build the player's sidebar list from what's CURRENTLY VISIBLE in the main
        # window — i.e. iterate the actual QListWidget the user just clicked from,
        # not the cached `currently_loaded_streams` array. For Series in episode
        # mode (navigation level 2) that means the list shows episodes of the open
        # season; for movies it's the open category; for LIVE it's the open category.
        try:
            current_tab_idx = self.tab_widget.currentIndex()
            tab_name = self.tab_widget.tabText(current_tab_idx)
            stream_type = {
                'LIVE': 'LIVE', 'Movies': 'Movies', 'Series': 'Series'
            }.get(tab_name)

            # History has no catalog list of its own. Build the sidebar from
            # recent items of the selected type so Series never inherits LIVE.
            if tab_name == 'History' and isinstance(history_entry, dict):
                stream_type = history_entry.get('type')
                playlist = []
                current_idx = 0
                title = history_entry.get('title', '')
                for entry in load_history(self.history_file):
                    if entry.get('type') != stream_type:
                        continue
                    entry_url = self._history_entry_url(entry)
                    if not entry_url:
                        continue
                    playlist.append({
                        'name': entry.get('title', entry_url),
                        'url': entry_url,
                        'history': entry,
                    })
                    if entry.get('key') == history_entry.get('key'):
                        current_idx = len(playlist) - 1
                if playlist:
                    return playlist, current_idx, title

            if stream_type is None:
                return [{
                    'name': (history_entry or {}).get('title', url),
                    'url': url,
                    'history': history_entry,
                }], 0, (history_entry or {}).get('title', '')

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
                    history_entry = self._history_metadata(
                        stream_type, data, name
                    )
                    playlist.append({
                        'name': name,
                        'url': u,
                        'history': history_entry,
                    })
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
                
                history_list_idx[0] = 0

                if text:
                    history_list.insert(0, text)

                    if search_history_size >= self.max_search_history_size:
                        history_list.pop(-1)

                self.search_in_list(list_content_type, stream_type, text)

            case Qt.Key_Up:
                if not history_list:
                    return

                history_list_idx[0] += 1
                if history_list_idx[0] >= search_history_size:
                    history_list_idx[0] = search_history_size - 1

                search_bar.setText(history_list[history_list_idx[0]])

            case Qt.Key_Down:
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

    def search_in_list(self, list_content_type, stream_type, text):
        """Filter source entries for the current column and Series navigation level.

        Searches rebuild visible rows without filtering the source in place, so
        clearing a query restores the full list. Stable relevance ranking keeps
        the selected sort order within each relevance group.
        """
        try:
            self.set_progress_bar(0, f"Loading search results...")
            # Every normalized query word must occur somewhere in the candidate.
            # Substring matching intentionally allows partial words without adding
            # fuzzy-search complexity or unpredictable similarity thresholds.
            search_terms = normalize_search_text(text).split()

            # If searching in category list
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

                    # if search bar is empty
                    if not search_terms:
                        itemAll = self._new_category_item(
                            stream_type, {'category_name': self.all_categories_text}
                        )
                        list_widget.insertItem(0, itemAll)

                        itemFav = self._new_category_item(
                            stream_type, {'category_name': self.fav_categories_text}
                        )
                        list_widget.insertItem(1, itemFav)

                    if not list_widget.count():
                        list_widget.addItem("No search results found...")
                finally:
                    list_widget.setUpdatesEnabled(True)
                    list_widget.viewport().update()

            # If searching in streaming content list
            elif list_content_type == 'streaming':
                if not self.currently_loaded_streams[stream_type]:
                    return

                list_widget = self.streaming_list_widgets[stream_type]
                active_sorting = getattr(
                    self.streaming_search_bars[stream_type],
                    'current_sorting',
                    (self.sorting_enabled, self.sorting_order),
                )
                active_sorting_enabled, active_sort_order = active_sorting
                list_widget.setSortingEnabled(False)
                list_widget.setUpdatesEnabled(False)
                try:
                    list_widget.clear()
                    navigation_level = (
                        self.series_navigation_level if stream_type == 'Series' else 0
                    )

                    match navigation_level:
                        case 0:  # LIVE/VOD/Series
                            matching_entries = [
                                entry for entry in self.currently_loaded_streams[stream_type]
                                if title_matches_search(
                                    entry.get('name', ''), search_terms
                                )
                            ]
                            matching_entries = ordered_catalog_entries(
                                matching_entries,
                                active_sorting_enabled,
                                descending=(active_sort_order == 1),
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
                        case 1:  # Seasons
                            list_widget.addItem(self.go_back_text)

                            seasons = [
                                season for season in self.currently_loaded_streams['Seasons']
                                if title_matches_search(
                                    f"season {season}", search_terms
                                )
                            ]
                            if active_sorting_enabled:
                                seasons = ordered_season_keys(
                                    seasons,
                                    descending=(active_sort_order == 1),
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
                        case 2:  # Episodes
                            list_widget.addItem(self.go_back_text)
                            matching_episodes = [
                                episode for episode in self.currently_loaded_streams['Episodes']
                                if title_matches_search(
                                    episode.get('title', ''), search_terms
                                )
                            ]
                            matching_episodes = ordered_catalog_entries(
                                matching_episodes,
                                active_sorting_enabled,
                                descending=(active_sort_order == 1),
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
        preference = load_player_preference(self.user_data_file)
        if preference.configured:
            command = preference.command
            remembered_command = preference.last_external_command
            self.last_external_player_command = remembered_command

            # VLC may have been removed after Internal VLC was selected. Validate
            # the saved choice before restoring it and reuse the last external player
            # when possible.
            if command == INTERNAL_VLC_COMMAND and not EmbeddedPlayerWindow.is_available():
                command = remembered_command or ""
                try:
                    save_player_preference(
                        self.user_data_file, command, remembered_command
                    )
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
                default_cmd = INTERNAL_VLC_COMMAND
                # Persist the choice so the user can see "Active player: Internal VLC"
                # in Settings without having to click anything.
                self.last_external_player_command = ""
                try:
                    save_player_preference(self.user_data_file, default_cmd)
                except OSError:
                    pass
                return default_cmd
        except Exception:
            pass

        self.last_external_player_command = ""
        QTimer.singleShot(0, self._show_internal_vlc_unavailable)
        return ""

    def save_external_player_command(self):
        # Store the active mode and the last external executable separately. Switching
        # to Internal VLC must not erase the path the user may want to select again.
        if (
            self.external_player_command
            and self.external_player_command != INTERNAL_VLC_COMMAND
        ):
            self.last_external_player_command = self.external_player_command
        remembered_command = getattr(self, "last_external_player_command", "") or ""

        try:
            save_player_preference(
                self.user_data_file,
                self.external_player_command,
                remembered_command,
            )
        except OSError as e:
            print(f"Could not write user data file: {e}")

    def open_address_book(self):
        dialog = AccountManager(self)
        self._prepare_dialog_theme(dialog)
        dialog.exec_()
        self._refresh_account_selectors(self.active_account_name)







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
