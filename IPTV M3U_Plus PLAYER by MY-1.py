import sys
import os
from os import path
import time
import requests
import subprocess
import configparser
import re
import json
import html
from lxml import etree, html
from datetime import datetime
from dateutil import parser, tz
import xml.etree.ElementTree as ET
from PyQt5.QtGui import QIcon, QFont, QImage, QPixmap, QColor, QDesktopServices, QIntValidator, QPalette
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize, QObject, pyqtSignal, 
    QRunnable, pyqtSlot, QThreadPool, QModelIndex, QAbstractItemModel, QVariant, QUrl
)
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QLineEdit, QLabel, QPushButton,
    QListWidget, QWidget, QFileDialog, QCheckBox, QSizePolicy, QHBoxLayout,
    QDialog, QFormLayout, QDialogButtonBox, QTabWidget, QListWidgetItem,
    QSpinBox, QMenu, QAction, QTextEdit, QGridLayout, QMessageBox, QListView,
    QTreeWidget, QTreeWidgetItem, QTreeView, QAction, QMenu, QComboBox, QSplitter
)

from AccountManager import AccountManager
from CustomPyQtWidgets import LiveInfoBox, MovieInfoBox, SeriesInfoBox, EmbeddedPlayerWindow
import Threadpools
from Threadpools import FetchDataWorker, SearchWorker, OnlineWorker, EPGWorker, MovieInfoFetcher, SeriesInfoFetcher, ImageFetcher

CURRENT_VERSION = "V2.00.00"

is_windows  = sys.platform.startswith('win')
is_mac      = sys.platform.startswith('darwin')
is_linux    = sys.platform.startswith('linux')

GITHUB_REPO = "Youri666/Xtream-m3u_plus-IPTV-Player"

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

        self.user_data_file = "userdata.ini"
        self.favorites_file = "favorites.json"
        self.cache_file     = "all_cached_data.json"
        # Default values for URL formats
        self.default_url_formats = {
            'live': "{server}/live/{username}/{password}/{stream_id}.{container_extension}",
            'movie': "{server}/movie/{username}/{password}/{stream_id}.{container_extension}",
            'series': "{server}/series/{username}/{password}/{stream_id}.{container_extension}"
        }

        # Update the .ini file if needed to maintain backward compatibility.
        self.updateUserDataFile()

        self.path_to_window_icon            = path.abspath(path.join(path.dirname(__file__), 'Images/TV_icon.ico'))
        self.path_to_no_img                 = path.abspath(path.join(path.dirname(__file__), 'Images/no_image.jpg'))
        self.path_to_loading_img            = path.abspath(path.join(path.dirname(__file__), 'Images/loading-icon.png'))
        self.path_to_404_img                = path.abspath(path.join(path.dirname(__file__), 'Images/404_not_found.png'))
        
        self.path_to_yt_img                 = path.abspath(path.join(path.dirname(__file__), 'Images/yt_icon_rgb.png'))
        self.path_to_tmdb_img               = path.abspath(path.join(path.dirname(__file__), 'Images/primary_full-TMDB.svg'))
        
        self.path_to_home_icon              = path.abspath(path.join(path.dirname(__file__), 'Images/home_tab_icon.ico'))
        self.path_to_live_icon              = path.abspath(path.join(path.dirname(__file__), 'Images/tv_tab_icon.ico'))
        self.path_to_movies_icon            = path.abspath(path.join(path.dirname(__file__), 'Images/movies_tab_icon.ico'))
        self.path_to_series_icon            = path.abspath(path.join(path.dirname(__file__), 'Images/series_tab_icon.ico'))
        self.path_to_favorites_icon         = path.abspath(path.join(path.dirname(__file__), 'Images/favorite_tab_icon.ico'))
        self.path_to_fav_colour_icon        = path.abspath(path.join(path.dirname(__file__), 'Images/favorite_tab_icon_colour.ico'))
        self.path_to_online_status_icon     = path.abspath(path.join(path.dirname(__file__), 'Images/online_status.png'))
        self.path_to_offline_status_icon    = path.abspath(path.join(path.dirname(__file__), 'Images/offline_status.png'))
        self.path_to_maybe_status_icon      = path.abspath(path.join(path.dirname(__file__), 'Images/maybe_status.png'))
        self.path_to_unknown_status_icon    = path.abspath(path.join(path.dirname(__file__), 'Images/unknown_status.png'))
        self.path_to_info_icon              = path.abspath(path.join(path.dirname(__file__), 'Images/info_tab_icon.ico'))
        self.path_to_settings_icon          = path.abspath(path.join(path.dirname(__file__), 'Images/settings_tab_icon.ico'))
        
        self.path_to_search_icon            = path.abspath(path.join(path.dirname(__file__), 'Images/search_bar_icon.ico'))
        self.path_to_sorting_icon           = path.abspath(path.join(path.dirname(__file__), 'Images/sorting_icon.ico'))
        self.path_to_clear_btn_icon         = path.abspath(path.join(path.dirname(__file__), 'Images/clear_button_icon.ico'))
        self.path_to_go_back_icon           = path.abspath(path.join(path.dirname(__file__), 'Images/go_back_icon.ico'))

        self.path_to_account_icon           = path.abspath(path.join(path.dirname(__file__), 'Images/account_manager_icon.ico'))
        self.path_to_mediaplayer_icon       = path.abspath(path.join(path.dirname(__file__), 'Images/film_camera_icon.ico'))

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
        self.currently_loaded_streams = {
            'LIVE': [],
            'Movies': [],
            'Series': [],
            'Seasons': [],
            'Episodes': []
        }

        # Whether to request the VODs or not
        self.vods_enabled = True

        #Create search bar dicts
        self.category_search_bars   = {}
        self.streaming_search_bars  = {}

        #Create sorting all lists setting variable. Set sorting to A-Z by default.
        self.sorting_enabled    = True
        self.sorting_order      = 0

        #Credentials
        self.server            = ""
        self.username          = ""
        self.password          = ""
        self.live_url_format   = ""
        self.movie_url_format  = ""
        self.series_url_format = ""

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

        self.initIcons()

        self.initTabWidget()

        self.initIPTVinfo()

        self.initCategoryListWidgets()
        self.initEntryListWidgets()
        self.initInfoBoxes()

        self.initSearchBars()

        # self.initHomeTab()

        self.initSettingsTab()

        self.initProgressBar()        

        #Load default settings after GUI has been initialized
        self.loadDataAtStartup()

        #Create live tv tab splitter
        live_splitter = QSplitter(Qt.Horizontal)

        # Column 0 widget (category)
        live_category_container = QWidget()
        live_category_layout = QVBoxLayout(live_category_container)
        live_category_layout.setContentsMargins(0, 0, 0, 0)
        live_category_layout.addWidget(self.category_search_bars["LIVE"])
        live_category_layout.addWidget(self.category_list_live)

        # Set width limits
        live_category_container.setMinimumWidth(150)

        # Column 1 widget (streaming)
        live_streaming_container = QWidget()
        live_streaming_layout = QVBoxLayout(live_streaming_container)
        live_streaming_layout.setContentsMargins(0, 0, 0, 0)
        live_streaming_layout.addWidget(self.streaming_search_bars["LIVE"])
        live_streaming_layout.addWidget(self.streaming_list_live)

        # Set width limits
        live_streaming_container.setMinimumWidth(150)

        # Column 2 widget (live info)
        live_info_box_container = QWidget()
        live_info_box_layout = QVBoxLayout(live_info_box_container)
        live_info_box_layout.setContentsMargins(0, 0, 0, 0)
        live_info_box_layout.addWidget(self.live_info_box)

        # Set width limits
        live_info_box_container.setMinimumWidth(300)

        # Add widgets to splitter
        live_splitter.addWidget(live_category_container)
        live_splitter.addWidget(live_streaming_container)
        live_splitter.addWidget(live_info_box_container)

        # Stretch ratios (initial splitter sizes)
        live_splitter.setSizes([200, 200, 300])  # Initial widths

        live_splitter.setCollapsible(0, False)  # Prevent collapsing column 0
        live_splitter.setCollapsible(1, False)  # Prevent collapsing column 1
        live_splitter.setCollapsible(2, False)  # prevent collapsing column 2

        # Add splitter to live tab layout
        self.live_tab_layout.addWidget(live_splitter)


        #Create movies tab splitter
        movies_splitter = QSplitter(Qt.Horizontal)

        # Column 0 widget (category)
        movies_category_container = QWidget()
        movies_category_layout = QVBoxLayout(movies_category_container)
        movies_category_layout.setContentsMargins(0, 0, 0, 0)
        movies_category_layout.addWidget(self.category_search_bars["Movies"])
        movies_category_layout.addWidget(self.category_list_movies)

        # Set width limits
        movies_category_container.setMinimumWidth(150)

        # Column 1 widget (streaming)
        movies_streaming_container = QWidget()
        movies_streaming_layout = QVBoxLayout(movies_streaming_container)
        movies_streaming_layout.setContentsMargins(0, 0, 0, 0)
        movies_streaming_layout.addWidget(self.streaming_search_bars["Movies"])
        movies_streaming_layout.addWidget(self.streaming_list_movies)

        # Set width limits
        movies_streaming_container.setMinimumWidth(150)

        # Column 2 widget (movies info)
        movies_info_box_container = QWidget()
        movies_info_box_layout = QVBoxLayout(movies_info_box_container)
        movies_info_box_layout.setContentsMargins(0, 0, 0, 0)
        movies_info_box_layout.addWidget(self.movies_info_box)

        # Set width limits
        movies_info_box_container.setMinimumWidth(350)

        # Add widgets to splitter
        movies_splitter.addWidget(movies_category_container)
        movies_splitter.addWidget(movies_streaming_container)
        movies_splitter.addWidget(movies_info_box_container)

        # Stretch ratios (initial splitter sizes)
        movies_splitter.setSizes([200, 200, 300])  # Initial widths

        movies_splitter.setCollapsible(0, False)  # Prevent collapsing column 0
        movies_splitter.setCollapsible(1, False)  # Prevent collapsing column 1
        movies_splitter.setCollapsible(2, False)  # prevent collapsing column 2

        # Add splitter to movies tab layout
        self.movies_tab_layout.addWidget(movies_splitter)


        #Create series tab splitter
        series_splitter = QSplitter(Qt.Horizontal)

        # Column 0 widget (category)
        series_category_container = QWidget()
        series_category_layout = QVBoxLayout(series_category_container)
        series_category_layout.setContentsMargins(0, 0, 0, 0)
        series_category_layout.addWidget(self.category_search_bars["Series"])
        series_category_layout.addWidget(self.category_list_series)

        # Set width limits
        series_category_container.setMinimumWidth(150)

        # Column 1 widget (streaming)
        series_streaming_container = QWidget()
        series_streaming_layout = QVBoxLayout(series_streaming_container)
        series_streaming_layout.setContentsMargins(0, 0, 0, 0)
        series_streaming_layout.addWidget(self.streaming_search_bars["Series"])
        series_streaming_layout.addWidget(self.streaming_list_series)

        # Set width limits
        series_streaming_container.setMinimumWidth(150)

        # Column 2 widget (series info)
        series_info_box_container = QWidget()
        series_info_box_layout = QVBoxLayout(series_info_box_container)
        series_info_box_layout.setContentsMargins(0, 0, 0, 0)
        series_info_box_layout.addWidget(self.series_info_box)

        # Set width limits
        series_info_box_container.setMinimumWidth(350)

        # Add widgets to splitter
        series_splitter.addWidget(series_category_container)
        series_splitter.addWidget(series_streaming_container)
        series_splitter.addWidget(series_info_box_container)

        # Stretch ratios (initial splitter sizes)
        series_splitter.setSizes([200, 200, 300])  # Initial widths

        series_splitter.setCollapsible(0, False)  # Prevent collapsing column 0
        series_splitter.setCollapsible(1, False)  # Prevent collapsing column 1
        series_splitter.setCollapsible(2, False)  # prevent collapsing column 2

        # Add splitter to series tab layout
        self.series_tab_layout.addWidget(series_splitter)
        
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

    def updateUserDataFile(self):
        # Load the configuration file. A corrupted .ini must not crash the app —
        # fall back to a fresh config so the user can re-add accounts.
        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError) as e:
            print(f"User data file is corrupt, ignoring it: {e}")
            try:
                os.rename(self.user_data_file, self.user_data_file + ".bak")
            except OSError:
                pass
            return

        # Check if 'Credentials' section exists
        if 'Credentials' not in config:
            return

        for account_name, data in config['Credentials'].items():
            parts = data.split('|')

            # Required total length and which fields are the URL-format tail.
            if data.startswith('manual|'):
                required_length = 7  # manual|server|user|pass|live_fmt|movie_fmt|series_fmt+1 leading tag
            elif data.startswith('m3u_plus|'):
                required_length = 5  # m3u_plus|url|live_fmt|movie_fmt|series_fmt+1 leading tag
            else:
                continue

            # Append default URL formats for whichever ones are missing at the tail.
            if len(parts) < required_length:
                defaults = [self.default_url_formats['live'],
                            self.default_url_formats['movie'],
                            self.default_url_formats['series']]
                missing = required_length - len(parts)
                # Take the LAST `missing` defaults (the tail of the list), not the first —
                # the first defaults that exist in `parts` are for live/movie, missing ones are at the end.
                parts += defaults[-missing:]
                config['Credentials'][account_name] = "|".join(parts)

        try:
            with open(self.user_data_file, 'w') as config_file:
                config.write(config_file)
        except OSError as e:
            print(f"Could not persist user data file: {e}")

    def initIcons(self):
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

    def initTabWidget(self):
        #Create tab widget
        self.tab_widget = QTabWidget()

        #Create tabs
        home_tab        = QWidget()
        live_tab        = QWidget()
        movies_tab      = QWidget()
        series_tab      = QWidget()
        favorites_tab   = QWidget()
        info_tab        = QWidget()
        settings_tab    = QWidget()

        #Create layouts for tabs
        self.home_tab_layout        = QVBoxLayout(home_tab)
        self.live_tab_layout        = QVBoxLayout(live_tab)
        self.movies_tab_layout      = QVBoxLayout(movies_tab)
        self.series_tab_layout      = QVBoxLayout(series_tab)
        self.favorites_tab_layout   = QGridLayout(favorites_tab)
        self.info_tab_layout        = QVBoxLayout(info_tab)
        self.settings_layout        = QGridLayout(settings_tab)

        #Add created tabs to tab widget with their names
        # self.tab_widget.addTab(home_tab,        self.home_icon,         "Home")
        self.tab_widget.addTab(live_tab,        self.live_icon,         "LIVE")
        self.tab_widget.addTab(movies_tab,      self.movies_icon,       "Movies")
        self.tab_widget.addTab(series_tab,      self.series_icon,       "Series")
        # self.tab_widget.addTab(favorites_tab,   self.favorites_icon,    "Favorites")
        self.tab_widget.addTab(info_tab,        self.info_icon,         "Info")
        self.tab_widget.addTab(settings_tab,    self.settings_icon,     "Settings")

    def initSearchBars(self):
        #Initialize search bars for category lists
        self.category_search_bars["LIVE"] = QLineEdit()
        self.category_search_bars["LIVE"].setPlaceholderText("Search Live TV Categories...")
        self.configSearchBar(self.category_search_bars["LIVE"], 'category', 'LIVE', self.category_list_widgets, self.category_search_history_list, self.category_search_history_list_idx)

        self.category_search_bars["Movies"] = QLineEdit()
        self.category_search_bars["Movies"].setPlaceholderText("Search Movies Categories...")
        self.configSearchBar(self.category_search_bars["Movies"], 'category', 'Movies', self.category_list_widgets, self.category_search_history_list, self.category_search_history_list_idx)

        self.category_search_bars["Series"] = QLineEdit()
        self.category_search_bars["Series"].setPlaceholderText("Search Series Categories...")
        self.configSearchBar(self.category_search_bars["Series"], 'category', 'Series', self.category_list_widgets, self.category_search_history_list, self.category_search_history_list_idx)

        #Initialize search bars for streaming content lists
        self.streaming_search_bars["LIVE"] = QLineEdit()
        self.streaming_search_bars["LIVE"].setPlaceholderText("Search Live TV Channels...")
        self.configSearchBar(self.streaming_search_bars["LIVE"], 'streaming', 'LIVE', self.streaming_list_widgets, self.streaming_search_history_list, self.streaming_search_history_list_idx)

        self.streaming_search_bars["Movies"] = QLineEdit()
        self.streaming_search_bars["Movies"].setPlaceholderText("Search Movies...")
        self.configSearchBar(self.streaming_search_bars["Movies"], 'streaming', 'Movies', self.streaming_list_widgets, self.streaming_search_history_list, self.streaming_search_history_list_idx)

        self.streaming_search_bars["Series"] = QLineEdit()
        self.streaming_search_bars["Series"].setPlaceholderText("Search Series...")
        self.configSearchBar(self.streaming_search_bars["Series"], 'streaming', 'Series', self.streaming_list_widgets, self.streaming_search_history_list, self.streaming_search_history_list_idx)

    def configSearchBar(self, search_bar, list_content_type, stream_type, list_widgets, search_history_list, search_history_list_idx):
        #Create sorting actions
        sort_a_z        = QAction("A-Z", self)
        sort_z_a        = QAction("Z-A", self)
        sort_disabled   = QAction("Sorting disabled", self)

        #Add search icon
        search_bar.addAction(self.search_icon, QLineEdit.LeadingPosition)

        #Create sorting action menu
        sorting_menu = QMenu()
        sorting_menu.setTitle("Set sorting order:")
        sorting_menu.addActions([sort_a_z, sort_z_a, sort_disabled])

        #Create sorting button
        sort_action = QAction(self.sorting_icon, "sort", self)
        sort_action.setMenu(sorting_menu)
        search_bar.addAction(sort_action, QLineEdit.TrailingPosition)

        #Connect functions to sorting actions
        sort_a_z.triggered.connect(lambda: self.sortList(search_bar, list_content_type, stream_type, list_widgets, True, 0))
        sort_z_a.triggered.connect(lambda: self.sortList(search_bar, list_content_type, stream_type, list_widgets, True, 1))
        sort_disabled.triggered.connect(lambda: self.sortList(search_bar, list_content_type, stream_type, list_widgets, False, 0))

        #Create clear search button
        clear_action = QAction(self.clear_btn_icon, "clear", self)
        search_bar.addAction(clear_action, QLineEdit.TrailingPosition)

        #Connect function to clear search action
        clear_action.triggered.connect(lambda: self.clearSearch(search_bar, list_content_type, stream_type, list_widgets, search_history_list_idx))

        #Connect function to process search bar key presses
        search_bar.keyPressEvent = lambda e: self.SearchBarKeyPressed(e, 
            search_bar, list_content_type, stream_type, list_widgets, search_history_list, search_history_list_idx)

    def clearSearch(self, search_bar, list_content_type, stream_type, list_widgets, history_list_idx):
        #Clear search bar
        search_bar.clear()

        #Reset list history index to -1
        history_list_idx[0] = -1

        #Search for nothing so list will be reset
        self.search_in_list(list_content_type, stream_type, "")

    def sortList(self, search_bar, list_content_type, stream_type, list_widgets, sorting_enabled, sort_order):
        self.set_progress_bar(0, f"Sorting {stream_type} {list_content_type}")

        #Get list
        list_widget = list_widgets[stream_type]

        # The Seasons view (Series tab, navigation level 1) needs numeric ordering, not Qt's
        # default text sort — otherwise "Season 10" comes before "Season 2". Issue #18.
        is_seasons_view = (
            list_content_type == 'streaming'
            and stream_type == 'Series'
            and getattr(self, 'series_navigation_level', 0) == 1
        )
        if is_seasons_view and sorting_enabled:
            seasons_dict = self.currently_loaded_streams.get('Seasons', {}) or {}

            def _season_sort_key(k):
                try:
                    return (0, int(k))
                except (TypeError, ValueError):
                    return (1, str(k).lower())

            keys = sorted(seasons_dict.keys(), key=_season_sort_key)
            if sort_order == 1:
                keys.reverse()

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

        #Enable or disable sorting
        list_widget.setSortingEnabled(sorting_enabled)

        #Remove 'All' and 'Favorites' category items
        if list_content_type == 'category':
            matches = []
            for text in [self.all_categories_text, self.fav_categories_text]:
                matches.extend(list_widget.findItems(text, Qt.MatchExactly))

            for item in matches:
                idx = list_widget.row(item)
                list_widget.takeItem(idx)

        if sorting_enabled:
            #When sorting is enabled, set sort order, 0: A-Z, 1: Z-A
            list_widget.sortItems(sort_order)

        else:
            #When sorting is disabled, reload list manually
            if list_content_type == 'category':
                self.category_list_widgets[stream_type].clear()

                for entry in self.currently_loaded_categories[stream_type]:
                    item = QListWidgetItem(entry['category_name'])
                    item.setData(Qt.UserRole, entry)

                    self.category_list_widgets[stream_type].addItem(item)

            elif list_content_type == 'streaming':
                self.streaming_list_widgets[stream_type].clear()

                for entry in self.currently_loaded_streams[stream_type]:
                    item = QListWidgetItem(entry['name'])
                    item.setData(Qt.UserRole, entry)

                    self.streaming_list_widgets[stream_type].addItem(item)

        #Disable sorting
        list_widget.setSortingEnabled(False)

        if list_content_type == 'category':
            #Add 'All' and 'Favorites' categories to top
            itemAll = QListWidgetItem(self.all_categories_text)
            itemAll.setData(Qt.UserRole, {'category_name': self.all_categories_text})
            self.category_list_widgets[stream_type].insertItem(0, itemAll)

            itemFav = QListWidgetItem(self.fav_categories_text)
            itemFav.setData(Qt.UserRole, {'category_name': self.fav_categories_text})
            self.category_list_widgets[stream_type].insertItem(1, itemFav)

        self.animate_progress(0, 100, f"Finished sorting {stream_type} {list_content_type}")

    def initIPTVinfo(self):
        self.iptv_info_text = QTextEdit()
        self.iptv_info_text.setReadOnly(True)

        default_font = QFont()
        default_font.setPointSize(self.default_font_size)

        self.iptv_info_text.setFont(default_font)

    def initCategoryListWidgets(self):
        #Create lists for categories
        self.category_list_live     = QListWidget()
        self.category_list_movies   = QListWidget()
        self.category_list_series   = QListWidget()

        #Enable sorting
        # self.category_list_live.setSortingEnabled(True)
        # self.category_list_movies.setSortingEnabled(True)
        # self.category_list_series.setSortingEnabled(True)

        #Connect functions to category list events
        self.category_list_live.itemClicked.connect(self.category_item_clicked)
        self.category_list_movies.itemClicked.connect(self.category_item_clicked)
        self.category_list_series.itemClicked.connect(self.category_item_clicked)

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
                QListWidget::item {
                    padding-top: 5px;
                    padding-bottom: 5px;
                }
            """)

    def initEntryListWidgets(self):
        #Create lists for channels
        self.streaming_list_live      = QListWidget()
        self.streaming_list_movies    = QListWidget()
        self.streaming_list_series    = QListWidget()

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

        #Put entry lists in list
        self.streaming_list_widgets = {
            'LIVE': self.streaming_list_live,
            'Movies': self.streaming_list_movies,
            'Series': self.streaming_list_series,
        }

        #Configure visuals of the lists
        standard_icon_size = QSize(24, 24)
        for list_widget in [self.streaming_list_live, self.streaming_list_movies, self.streaming_list_series]:
            list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            list_widget.setIconSize(standard_icon_size)
            list_widget.setStyleSheet("""
                QListWidget::item {
                    padding-top: 5px;
                    padding-bottom: 5px;
                }
            """)

    def initInfoBoxes(self):
        #Create Movies and Series info box
        self.live_info_box   = LiveInfoBox(self)
        self.movies_info_box = MovieInfoBox(self)
        self.series_info_box = SeriesInfoBox(self)

    def initHomeTab(self):
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

    def loadDefaultSortingOrder(self):
        sorting_order = ""

        config = configparser.ConfigParser()
        config.read(self.user_data_file)

        if 'Sorting order' in config:
            # self.external_player_command = config['ExternalPlayer'].get('Command', '')
            sorting_order = config['Sorting order'].get('Order', '')

        print(f"loading default sorting order: {sorting_order}")

        if not sorting_order:
            #Set default order to A-Z
            self.default_sorting_order_box.setCurrentText("A-Z")

        else:
            self.default_sorting_order_box.setCurrentText(sorting_order)

        #Set sorting variables
        match self.default_sorting_order_box.currentText():
            case "A-Z":
                self.sorting_enabled    = True
                self.sorting_order      = 0

            case "Z-A":
                self.sorting_enabled    = True
                self.sorting_order      = 1

            case _:
                self.sorting_enabled    = False
                self.sorting_order      = 0

    def setAllSortingOrder(self, sorting_order):
        match sorting_order:
            case "A-Z":
                print("sorting A-Z")
                self.sortList(self.category_search_bars["LIVE"], 'category', "LIVE", self.category_list_widgets, True, 0)
                self.sortList(self.category_search_bars["Movies"], 'category', "Movies", self.category_list_widgets, True, 0)
                self.sortList(self.category_search_bars["Series"], 'category', "Series", self.category_list_widgets, True, 0)

                self.sortList(self.streaming_search_bars["LIVE"], 'streaming', "LIVE", self.streaming_list_widgets, True, 0)
                self.sortList(self.streaming_search_bars["Movies"], 'streaming', "Movies", self.streaming_list_widgets, True, 0)
                self.sortList(self.streaming_search_bars["Series"], 'streaming', "Series", self.streaming_list_widgets, True, 0)

            case "Z-A":
                print("sorting Z-A")
                self.sortList(self.category_search_bars["LIVE"], 'category', "LIVE", self.category_list_widgets, True, 1)
                self.sortList(self.category_search_bars["Movies"], 'category', "Movies", self.category_list_widgets, True, 1)
                self.sortList(self.category_search_bars["Series"], 'category', "Series", self.category_list_widgets, True, 1)

                self.sortList(self.streaming_search_bars["LIVE"], 'streaming', "LIVE", self.streaming_list_widgets, True, 1)
                self.sortList(self.streaming_search_bars["Movies"], 'streaming', "Movies", self.streaming_list_widgets, True, 1)
                self.sortList(self.streaming_search_bars["Series"], 'streaming', "Series", self.streaming_list_widgets, True, 1)

            case _:
                print("sorting disabled")
                self.sortList(self.category_search_bars["LIVE"], 'category', "LIVE", self.category_list_widgets, False, 0)
                self.sortList(self.category_search_bars["Movies"], 'category', "Movies", self.category_list_widgets, False, 0)
                self.sortList(self.category_search_bars["Series"], 'category', "Series", self.category_list_widgets, False, 0)

                self.sortList(self.streaming_search_bars["LIVE"], 'streaming', "LIVE", self.streaming_list_widgets, False, 0)
                self.sortList(self.streaming_search_bars["Movies"], 'streaming', "Movies", self.streaming_list_widgets, False, 0)
                self.sortList(self.streaming_search_bars["Series"], 'streaming', "Series", self.streaming_list_widgets, False, 0)

    def setDefaultSortingOrder(self, e, combobox):
        sorting_order = combobox.currentText()

        print(f"setting default sorting order: {sorting_order}")

        #Set sorting variables
        match sorting_order:
            case "A-Z":
                self.sorting_enabled    = True
                self.sorting_order      = 0

            case "Z-A":
                self.sorting_enabled    = True
                self.sorting_order      = 1

            case _:
                self.sorting_enabled    = False
                self.sorting_order      = 0

        self.setAllSortingOrder(sorting_order)

        config = configparser.ConfigParser()
        config.read(self.user_data_file)

        config['Sorting order'] = {'Order': sorting_order}

        with open(self.user_data_file, 'w') as config_file:
            config.write(config_file)

    def initSettingsTab(self):
        #Create items in settings tab
        self.settings_layout.setSpacing(20)
        self.settings_layout.setAlignment(Qt.AlignTop)

        self.address_book_button = QPushButton("IPTV accounts")
        self.address_book_button.setIcon(self.account_manager_icon)
        self.address_book_button.setToolTip("Manage IPTV accounts")
        self.address_book_button.clicked.connect(self.open_address_book)

        self.choose_player_button = QPushButton("Choose Media Player")
        self.choose_player_button.setIcon(self.mediaplayer_icon)
        self.choose_player_button.setToolTip("Set the Media Player used for watching content, use e.g. VLC or SMPlayer")
        self.choose_player_button.clicked.connect(self.choose_external_player)

        self.use_embedded_player_button = QPushButton("Use Internal Player (VLC)")
        self.use_embedded_player_button.setIcon(self.mediaplayer_icon)
        self.use_embedded_player_button.setToolTip(
            "Play streams inside this window using the built-in libvlc backend.\n"
            "Requires VLC to be installed on this machine — download from videolan.org."
        )
        self.use_embedded_player_button.clicked.connect(self.use_embedded_player)

        self.current_player_label = QLabel("")
        self.current_player_label.setStyleSheet("color: #5b8def;")

        self.vods_enabled_checkbox = QCheckBox("VODs enabled")
        self.vods_enabled_checkbox.setToolTip("Load the Movies/Series tabs for the IPTV account")
        self.vods_enabled_checkbox.stateChanged.connect(self.toggleVODs)

        self.keep_on_top_checkbox = QCheckBox("Keep on top")
        self.keep_on_top_checkbox.setToolTip("Keep the application on top of all windows")
        self.keep_on_top_checkbox.stateChanged.connect(self.toggleKeepOnTop)

        self.default_sorting_order_box = QComboBox()
        self.default_sorting_order_box.addItems(["A-Z", "Z-A", "Sorting disabled"])
        self.default_sorting_order_box.currentTextChanged.connect(lambda e: self.setDefaultSortingOrder(e, self.default_sorting_order_box))

        # self.cache_on_startup_checkbox = QCheckBox("Startup with cached data")
        # self.cache_on_startup_checkbox.setToolTip("Loads the cached IPTV data on startup to reduce startup time.\nNote that the cached data only changes if you manually reload it once in a while.")
        # self.cache_on_startup_checkbox.stateChanged.connect(self.toggle_cache_on_startup)

        # self.reload_data_btn = QPushButton("Reload data")
        # self.reload_data_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_BrowserReload))
        # self.reload_data_btn.setToolTip("Click this to manually reload the IPTV data.\nNote that this only has effect if \'Startup with cached data\' is checked.")

        self.select_user_agent_box = QComboBox()
        self.select_user_agent_box.addItems(self.user_agents)
        self.select_user_agent_box.currentTextChanged.connect(lambda e: self.userAgentSelected(e, self.select_user_agent_box))

        self.update_checker = QPushButton("Check for updates")
        self.update_checker.clicked.connect(lambda: self.checkForUpdates(True))

        self.auto_update_checkbox = QCheckBox("Auto check for updates")
        self.auto_update_checkbox.setToolTip("Automatically check for updates at startup")
        self.auto_update_checkbox.stateChanged.connect(self.toggleAutoUpdate)

        self.stream_status_checkbox = QCheckBox("Show LIVE stream status indicator")
        self.stream_status_checkbox.setToolTip(
            "Show the green/red traffic light next to a LIVE channel.\n"
            "Disable if your provider's stream status probes are flaky or slow."
        )
        self.stream_status_checkbox.stateChanged.connect(self.toggleStreamStatus)

        self.theme_select_box = QComboBox()
        self.theme_select_box.addItems(["System", "Light", "Dark"])
        self.theme_select_box.setToolTip("Switch between Light, Dark, or follow the OS setting (default).")
        self.theme_select_box.currentTextChanged.connect(self.themeChanged)

        #Set timeout integer validator
        timeout_validator = QIntValidator(0, 999)

        self.set_connection_timeout = QLineEdit()
        self.set_connection_timeout.setFixedWidth(100)
        self.set_connection_timeout.setValidator(timeout_validator)
        self.set_connection_timeout.returnPressed.connect(lambda: self.setTimeout(self.set_connection_timeout))

        self.set_read_timeout = QLineEdit()
        self.set_read_timeout.setFixedWidth(100)
        self.set_read_timeout.setValidator(timeout_validator)
        self.set_read_timeout.returnPressed.connect(lambda: self.setTimeout(self.set_read_timeout))

        self.set_live_status_timeout = QLineEdit()
        self.set_live_status_timeout.setFixedWidth(100)
        self.set_live_status_timeout.setValidator(timeout_validator)
        self.set_live_status_timeout.returnPressed.connect(lambda: self.setTimeout(self.set_live_status_timeout))

        #Add widgets to settings tab layout
        self.settings_layout.addWidget(self.address_book_button,                            0, 0)
        self.settings_layout.addWidget(self.choose_player_button,                           0, 1)
        self.settings_layout.addWidget(self.use_embedded_player_button,                     0, 2)
        self.settings_layout.addWidget(self.current_player_label,                          10, 0, 1, 3)
        self.settings_layout.addWidget(self.vods_enabled_checkbox,                          1, 0)
        self.settings_layout.addWidget(self.keep_on_top_checkbox,                           2, 0)
        self.settings_layout.addWidget(QLabel("Default sorting order: "),                   3, 0)
        self.settings_layout.addWidget(self.default_sorting_order_box,                      3, 1)
        self.settings_layout.addWidget(self.update_checker,                                 4, 0)
        self.settings_layout.addWidget(self.auto_update_checkbox,                           4, 1)
        self.settings_layout.addWidget(self.stream_status_checkbox,                         9, 0)
        self.settings_layout.addWidget(QLabel("Theme: "),                                  11, 0)
        self.settings_layout.addWidget(self.theme_select_box,                              11, 1)

        #Advanced options
        self.settings_layout.addWidget(QLabel("Select User-Agent (Advanced option): "),         5, 0)
        self.settings_layout.addWidget(self.select_user_agent_box,                              5, 1)
        self.settings_layout.addWidget(QLabel("Set connection timeout (Advanced option): "),    6, 0)
        self.settings_layout.addWidget(self.set_connection_timeout,                             6, 1)
        self.settings_layout.addWidget(QLabel("Set read timeout (Advanced option): "),          7, 0)
        self.settings_layout.addWidget(self.set_read_timeout,                                   7, 1)
        self.settings_layout.addWidget(QLabel("Set live status timeout (Advanced option): "),   8, 0)
        self.settings_layout.addWidget(self.set_live_status_timeout,                            8, 1)

        # self.settings_layout.addWidget(self.cache_on_startup_checkbox,  2, 0)
        # self.settings_layout.addWidget(self.reload_data_btn,            3, 0)

    def userAgentSelected(self, e, combobox):
        #Get selected text
        user_agent = combobox.currentText()

        #Set current user agent
        self.current_user_agent = user_agent

        #Save selected user agent to userdata
        config = configparser.ConfigParser()
        config.read(self.user_data_file)

        config['User-Agent'] = {'user-agent': user_agent}

        with open(self.user_data_file, 'w') as config_file:
            config.write(config_file)

    def loadDefaultUserAgent(self):
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
            self.current_user_agent = Threadpools.DEFAULT_USER_AGENT_HEADER

        #Update combobox to selection
        self.select_user_agent_box.setCurrentText(self.current_user_agent)

    def loadDefaultVODs(self):
        #Read userdata config file
        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError):
            config = configparser.ConfigParser()

        #Check if defined in config. Otherwise set to default
        if config.has_option('VOD', 'enabled'):
            self.vods_enabled = (config['VOD']['enabled'] == 'True')
        else:
            self.vods_enabled = True

        #Update tabs to match config
        self.tab_widget.setTabEnabled(1, self.vods_enabled)
        self.tab_widget.setTabEnabled(2, self.vods_enabled)

        #Update checkbox to match config
        if self.vods_enabled:
            self.vods_enabled_checkbox.setCheckState(Qt.Checked)
        else:
            self.vods_enabled_checkbox.setCheckState(Qt.Unchecked)

    def setTimeout(self, lineedit):
        try: 
            #Get timeout value from lineedit
            value = lineedit.text()

            #If value is invalid
            if not value:
                raise Exception(f"Value entered is not valid: {value}!")

            #Save selected user agent to userdata
            config = configparser.ConfigParser()
            config.read(self.user_data_file)

            #If Timeouts section not yet exists create it
            if "Timeouts" not in config:
                config["Timeouts"] = {}

            #Check which timeout value has been changed
            match lineedit:
                case self.set_connection_timeout:
                    Threadpools.CONNECTION_TIMEOUT = int(value)

                    config['Timeouts']['CONNECTION_TIMEOUT'] = value

                case self.set_read_timeout:
                    Threadpools.READ_TIMEOUT = int(value)

                    config['Timeouts']['READ_TIMEOUT'] = value

                case self.set_live_status_timeout:
                    Threadpools.LIVE_STATUS_TIMEOUT = int(value)

                    config['Timeouts']['LIVE_STATUS_TIMEOUT'] = value

            #Write config file
            with open(self.user_data_file, 'w') as config_file:
                config.write(config_file)

            self.animate_progress(0, 100, f"Succesfully adjusted setting")

        except Exception as e:
            # print("Failed setting timeout: ")
            self.animate_progress(0, 100, f"Failed setting timeout: {e}")

    def loadDefaultTimeout(self):
        try:
            #Read userdata config file
            config = configparser.ConfigParser()
            config.read(self.user_data_file)

            #Set default values
            tmp_connection_timeout  = str(Threadpools.CONNECTION_TIMEOUT)
            tmp_read_timeout        = str(Threadpools.READ_TIMEOUT)
            tmp_live_status_timeout = str(Threadpools.LIVE_STATUS_TIMEOUT)

            #Check if defined in config
            if config.has_section("Timeouts"):
                if config.has_option("Timeouts", "CONNECTION_TIMEOUT"):
                    #Set connection timeout if defined
                    Threadpools.CONNECTION_TIMEOUT = int(config['Timeouts']['CONNECTION_TIMEOUT'])
                    tmp_connection_timeout = config['Timeouts']['CONNECTION_TIMEOUT']

                if config.has_option("Timeouts", "READ_TIMEOUT"):
                    #Set read timeout if defined
                    Threadpools.READ_TIMEOUT = int(config['Timeouts']['READ_TIMEOUT'])
                    tmp_read_timeout = config['Timeouts']['READ_TIMEOUT']

                if config.has_option("Timeouts", "LIVE_STATUS_TIMEOUT"):
                    #Set live status timeout if defined
                    Threadpools.LIVE_STATUS_TIMEOUT = int(config['Timeouts']['LIVE_STATUS_TIMEOUT'])
                    tmp_live_status_timeout = config['Timeouts']['LIVE_STATUS_TIMEOUT']
                    
            #Set values in corresponding LineEdit widgets
            self.set_connection_timeout.setText(tmp_connection_timeout)
            self.set_read_timeout.setText(tmp_read_timeout)
            self.set_live_status_timeout.setText(tmp_live_status_timeout)

        except Exception as e:
            print(f"Failed loading default timeout values: {e}")

    def _version_tuple(self, v):
        # "V1.03.02" -> (1, 3, 2). Used so the update checker doesn't prompt when
        # the current build is AHEAD of upstream (e.g. an unreleased fork build).
        return tuple(int(x) for x in re.findall(r'\d+', v or ""))

    def checkForUpdates(self, enable_update_msg):
        try:
            print("Checking for updates")

            #Create github api url to fetch data from
            git_api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

            #Request data from url. Pair a small read-timeout with the connection timeout —
            #without one a slow GitHub response can block the main thread indefinitely
            #(the previous code only set the connection timeout).
            git_resp = requests.get(git_api_url, timeout=(Threadpools.CONNECTION_TIMEOUT, 5))

            #Get data and latest version
            data = git_resp.json()
            latest_version = data['tag_name']

            #Only prompt when upstream is strictly newer than what we're running —
            #avoids a spurious "update available" dialog for fork/dev builds that
            #carry a higher version number.
            if self._version_tuple(latest_version) > self._version_tuple(CURRENT_VERSION):
                #If not up to date ask if user wants to go to download page
                reply = QMessageBox.question(self, 'Update Available',
                                             f"A new version ({latest_version}) is available.\n"
                                             "Do you want to visit the download page?",
                                             QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)

                #If user wants to go to download page, open latest version page
                if reply == QMessageBox.Yes:
                    latest_version_url = data['html_url']

                    QDesktopServices.openUrl(QUrl(latest_version_url))

            #Current version is up to date
            elif enable_update_msg:
                QMessageBox.information(self, 'No Update', "You are using the latest version.")

            else:
                self.animate_progress(0, 100, "No update available")

        except Exception as e:
            print(f"Failed update checker: {e}")

            if enable_update_msg:
                QMessageBox.warning(self, 'Failed update checker', "Failed checking for updates.\nPlease try again.")
            else:
                self.animate_progress(0, 100, "Failed checking for updates")

    def toggleAutoUpdate(self, state):
        checked = bool(state)

        config = configparser.ConfigParser()
        config.read(self.user_data_file)

        config['Updater'] = {'auto-update-checker': checked}

        with open(self.user_data_file, 'w') as config_file:
            config.write(config_file)

    def loadDefaultAutoUpdate(self):
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
                self.checkForUpdates(False)

        #If not enable the auto-update-checker by default
        else:
            #Write default value to userdata file
            config['Updater'] = {'auto-update-checker': True}

            try:
                with open(self.user_data_file, 'w') as config_file:
                    config.write(config_file)
            except OSError as e:
                print(f"Could not write user data file: {e}")

            #Set checkbox checked
            self.auto_update_checkbox.setCheckState(Qt.Checked)

            #Check for updates
            self.checkForUpdates(False)

    def initProgressBar(self):
        #Create progress bar
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setFixedHeight(25)
        self.progress_bar.setTextVisible(True)

        #Animate progress bar
        self.playlist_progress_animation = QPropertyAnimation(self.progress_bar, b"value")
        self.playlist_progress_animation.setDuration(1000)  # longer duration for smoother animation
        self.playlist_progress_animation.setEasingCurve(QEasingCurve.InOutQuad)

    def loadDataAtStartup(self):
        #Load external media player
        self.external_player_command = self.load_external_player_command()
        self._refresh_current_player_label()

        #Load default sorting setting
        self.loadDefaultSortingOrder()

        #Load default user agent
        self.loadDefaultUserAgent()

        #Load if VODs enabled
        self.loadDefaultVODs()

        #Load default auto update checker
        self.loadDefaultAutoUpdate()

        #Load stream-status toggle (issue #74)
        self.loadDefaultStreamStatus()

        #Apply persisted theme (Light / Dark / System) — default System
        self.loadDefaultTheme()

        #Load startup credentials
        self.loadStartupCredentials()

        #Load default timeouts
        self.loadDefaultTimeout()

    def loadStartupCredentials(self):
        # Load playlist on startup if enabled. A malformed/missing key here used to crash
        # the app right after the login screen (issue #92), so every access is guarded.
        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError) as e:
            print(f"Failed reading user data file at startup: {e}")
            return

        if 'Startup credentials' not in config:
            return

        selected_startup_account = config['Startup credentials'].get('startup_credentials', '')
        if not selected_startup_account or selected_startup_account == 'None':
            return

        if 'Credentials' not in config or selected_startup_account not in config['Credentials']:
            return

        try:
            data = config['Credentials'][selected_startup_account]
            parts = data.split('|')

            if data.startswith('manual|') and len(parts) >= 7:
                server, username, password, live_url_format, movie_url_format, series_url_format = parts[1:7]

                self.server            = server
                self.username          = username
                self.password          = password
                self.live_url_format   = live_url_format
                self.movie_url_format  = movie_url_format
                self.series_url_format = series_url_format

                self.login()

            elif data.startswith('m3u_plus|') and len(parts) >= 5:
                m3u_url, live_url_format, movie_url_format, series_url_format = parts[1:5]

                self.live_url_format   = live_url_format
                self.movie_url_format  = movie_url_format
                self.series_url_format = series_url_format

                if self.extract_credentials_from_m3u_plus_url(m3u_url):
                    self.login()
            else:
                print(f"Skipping startup account '{selected_startup_account}': data is malformed.")
        except Exception as e:
            print(f"Failed loading startup account: {e}")

    def toggleKeepOnTop(self, state):
        if state == Qt.Checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()

    def _is_system_dark(self):
        # On Windows 10/11, AppsUseLightTheme=0 means dark, 1 means light.
        # Other OSes: fall back to checking the current palette's window-bg luminance.
        if is_windows:
            try:
                import winreg
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                ) as key:
                    value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                    return value == 0
            except OSError:
                return False
        try:
            app = QtWidgets.qApp
            bg = app.palette().color(QPalette.Window)
            # Rough perceived-luminance check.
            return (0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()) < 128
        except Exception:
            return False

    def _apply_theme(self, theme_name):
        # Theme names: "System", "Light", "Dark". Anything else falls back to System.
        app = QtWidgets.qApp
        if theme_name == "Dark" or (theme_name == "System" and self._is_system_dark()):
            palette = QPalette()
            palette.setColor(QPalette.Window,          QColor(45, 45, 48))
            palette.setColor(QPalette.WindowText,      Qt.white)
            palette.setColor(QPalette.Base,            QColor(30, 30, 30))
            palette.setColor(QPalette.AlternateBase,   QColor(45, 45, 48))
            palette.setColor(QPalette.ToolTipBase,     QColor(45, 45, 48))
            palette.setColor(QPalette.ToolTipText,     Qt.white)
            palette.setColor(QPalette.Text,            Qt.white)
            palette.setColor(QPalette.Button,          QColor(45, 45, 48))
            palette.setColor(QPalette.ButtonText,      Qt.white)
            palette.setColor(QPalette.BrightText,      Qt.red)
            palette.setColor(QPalette.Link,            QColor(91, 141, 239))
            palette.setColor(QPalette.Highlight,       QColor(91, 141, 239))
            palette.setColor(QPalette.HighlightedText, Qt.black)
            palette.setColor(QPalette.Disabled, QPalette.Text,       QColor(127, 127, 127))
            palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(127, 127, 127))
            app.setPalette(palette)
        else:
            # Fusion's built-in light palette.
            app.setPalette(app.style().standardPalette())

    def themeChanged(self, theme_name):
        self._apply_theme(theme_name)
        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError):
            config = configparser.ConfigParser()
        config['Theme'] = {'mode': theme_name}
        try:
            with open(self.user_data_file, 'w') as config_file:
                config.write(config_file)
        except OSError as e:
            print(f"Could not write user data file: {e}")

    def loadDefaultTheme(self):
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

    def toggleStreamStatus(self, state):
        checked = bool(state)
        self.stream_status_enabled = checked

        # Reset the indicator to "unknown" when disabling so the UI doesn't keep a
        # stale green/red dot from the previous probe.
        if not checked:
            try:
                self.live_info_box.stream_status.setPixmap(
                    QPixmap(self.path_to_unknown_status_icon).scaledToWidth(24)
                )
            except Exception:
                pass

        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError):
            config = configparser.ConfigParser()
        config['StreamStatus'] = {'enabled': str(checked)}
        try:
            with open(self.user_data_file, 'w') as config_file:
                config.write(config_file)
        except OSError as e:
            print(f"Could not write user data file: {e}")

    def loadDefaultStreamStatus(self):
        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError):
            config = configparser.ConfigParser()

        if config.has_option('StreamStatus', 'enabled'):
            self.stream_status_enabled = (config['StreamStatus']['enabled'] == 'True')
        else:
            self.stream_status_enabled = True

        self.stream_status_checkbox.setCheckState(
            Qt.Checked if self.stream_status_enabled else Qt.Unchecked
        )

    def toggleVODs(self, state):
        checked = bool(state)

        self.vods_enabled = checked
        self.tab_widget.setTabEnabled(1, checked)
        self.tab_widget.setTabEnabled(2, checked)

        config = configparser.ConfigParser()
        config.read(self.user_data_file)
        config['VOD'] = {'enabled': checked}
        with open(self.user_data_file, 'w') as config_file:
            config.write(config_file)
    
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
        from urllib.parse import urlparse, parse_qs

        def _show_invalid():
            self.animate_progress(0, 100, "Invalid m3u_plus or m3u URL")
            dlg = QMessageBox(self)
            dlg.setWindowTitle("Error!")
            dlg.setText("M3U plus URL is invalid!\nPlease enter a valid Xtream get.php URL.")
            dlg.exec()

        def _parse(candidate_url):
            parsed = urlparse(candidate_url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                return None
            # Accept any path that ends with /get.php — some providers use a prefix path.
            if not parsed.path.endswith('/get.php'):
                return None
            qs = parse_qs(parsed.query)
            username = (qs.get('username') or [None])[0]
            password = (qs.get('password') or [None])[0]
            if not username or not password:
                return None
            # Build the server origin from the parsed URL (preserves port if present).
            server = f"{parsed.scheme}://{parsed.netloc}"
            return server, username, password

        try:
            result = _parse(url)

            # If it doesn't parse directly, the user may have pasted a shortened URL.
            # Follow redirects once (HEAD with a small timeout) and try the resolved URL.
            if result is None and url.lower().startswith(('http://', 'https://')):
                try:
                    resp = requests.head(url, allow_redirects=True, timeout=5)
                    if resp.url and resp.url != url:
                        print(f"Resolved shortened URL: {url} -> {resp.url}")
                        result = _parse(resp.url)
                except requests.RequestException as e:
                    print(f"Could not resolve URL '{url}': {e}")

            if result:
                self.server, self.username, self.password = result
                return True

            _show_invalid()
            return False
        except Exception as e:
            print(f"Error extracting credentials: {e}")
            self.animate_progress(0, 100, "Error extracting credentials")
            return False

    def set_progress_text(self, text):
        self.progress_bar.setFormat(text)
        QtWidgets.qApp.processEvents()
        # QtWidgets.qApp.sendPostedEvents()

    def set_progress_bar(self, val, text):
        self.progress_bar.setFormat(text)
        self.progress_bar.setValue(val)
        QtWidgets.qApp.processEvents()

    def animate_progress(self, start, end, text):
        self.playlist_progress_animation.stop()
        self.playlist_progress_animation.setStartValue(start)
        self.playlist_progress_animation.setEndValue(end)
        self.set_progress_text(text)
        self.playlist_progress_animation.start()
        QtWidgets.qApp.processEvents()

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

        #Start IPTV data fetch thread
        self.fetch_data_thread()

        self.set_progress_bar(0, "Going to fetch data...")

    def fetch_data_thread(self):
        dataWorker = FetchDataWorker(self.server, self.username, self.password, self.live_url_format, self.movie_url_format, self.series_url_format, self, self.vods_enabled)
        dataWorker.signals.finished.connect(self.process_data)
        dataWorker.signals.error.connect(self.on_fetch_data_error)
        dataWorker.signals.progress_bar.connect(self.animate_progress)
        dataWorker.signals.show_error_msg.connect(self.show_error_msg)
        dataWorker.signals.show_info_msg.connect(self.show_info_msg)
        self.threadpool.start(dataWorker)

    def process_data(self, iptv_info, categories_per_stream_type, entries_per_stream_type):
        print("Going to process IPTV data now")

        self.categories_per_stream_type = categories_per_stream_type
        self.entries_per_stream_type    = entries_per_stream_type

        self.set_progress_bar(0, "Processing received data...")

        #Process IPTV info
        user_info   = iptv_info.get("user_info", {})
        server_info = iptv_info.get("server_info", {})

        hostname    = server_info.get("url", "Unknown")
        port        = server_info.get("port", "Unknown")
        if hostname == "Unknown" or port == "Unknown":
            host = "Unknown"
        else:
            host = f"http://{hostname}:{port}"

        username                = user_info.get("username", "Unknown")
        password                = user_info.get("password", "Unknown")
        max_connections         = user_info.get("max_connections", "Unknown")
        active_connections      = user_info.get("active_cons", "Unknown")
        status                  = user_info.get("status", "Unknown")
        expire_timestamp        = user_info.get("exp_date", 0)
        created_at_timestamp    = user_info.get("created_at", 0)

        #If a value is given
        if expire_timestamp:
            #Convert date time variable to string
            expiry = datetime.fromtimestamp(int(expire_timestamp)).strftime("%B %d, %Y")
        else:
            expiry = "Unknown"

        #If a value is given
        if created_at_timestamp:
            #Convert date time variable to string
            created_at = datetime.fromtimestamp(int(created_at_timestamp)).strftime("%B %d, %Y")
        else:
            created_at = "Unknown"

        if user_info.get("is_trial") == "1":
            trial = "Yes"
        else:
            trial = "No"

        timezone = server_info.get("timezone", "Unknown")

        formatted_data = (
            f"Host: {host}\n"
            f"Username: {username}\n"
            f"Password: {password}\n"
            f"Max Connections: {max_connections}\n"
            f"Active Connections: {active_connections}\n"
            f"Timezone: {timezone}\n"
            f"Trial: {trial}\n"
            f"Status: {status}\n"
            f"Created At: {created_at}\n"
            f"Expiry: {expiry}\n"
        )

        #Set formatted data to iptv info tab
        self.iptv_info_text.setText(formatted_data)
        QtWidgets.qApp.processEvents()

        #Process categories and entries
        for stream_type in self.entries_per_stream_type.keys():
            #Clear category and streaming list
            self.category_list_widgets[stream_type].clear()
            self.streaming_list_widgets[stream_type].clear()

            #Skip VODs if option enabled
            if self.vods_enabled is False and (stream_type == 'Movies' or stream_type == 'Series'):
                continue

            #Fill currently loaded streams with current stream data
            for entry in self.entries_per_stream_type[stream_type]:
                self.currently_loaded_streams[stream_type].append(entry)

            #Fill currently loaded categories with current category data
            for entry in self.categories_per_stream_type[stream_type]:
                self.currently_loaded_categories[stream_type].append(entry)

            #Add categories in category list
            num_of_categories = len(self.categories_per_stream_type[stream_type])
            prev_perc = 0
            for idx, category_item in enumerate(self.categories_per_stream_type[stream_type]):
                item = QListWidgetItem(category_item['category_name'])
                item.setData(Qt.UserRole, category_item)
                # item.setIcon(channel_icon)

                #Add item to list
                self.category_list_widgets[stream_type].addItem(item)

                perc = (idx * 100) / num_of_categories
                if (perc - prev_perc) > 10:
                    prev_perc = perc
                    self.set_progress_bar(int(perc), f"Loading {stream_type} categories: {idx} of {num_of_categories}")
                    QtWidgets.qApp.processEvents()

            #Sort category list
            self.sortList(self.category_search_bars[stream_type], 'category', stream_type, self.category_list_widgets, self.sorting_enabled, self.sorting_order)

            #Add streams in streaming list
            num_of_entries = len(self.entries_per_stream_type[stream_type])
            prev_perc = 0
            for idx, entry in enumerate(self.entries_per_stream_type[stream_type]):
                item = QListWidgetItem(entry['name'])
                item.setData(Qt.UserRole, entry)
                # item.setIcon(channel_icon)

                self.streaming_list_widgets[stream_type].addItem(item)

                perc = (idx * 100) / num_of_entries
                if (perc - prev_perc) > 10:
                    prev_perc = perc
                    self.set_progress_bar(int(perc), f"Loading {stream_type} streams: {idx} of {num_of_entries}")
                    QtWidgets.qApp.processEvents()

            #Sort streaming list
            self.sortList(self.streaming_search_bars[stream_type], 'streaming', stream_type, self.streaming_list_widgets, self.sorting_enabled, self.sorting_order)

        self.set_progress_bar(100, f"Finished loading")
        QtWidgets.qApp.processEvents()

    def on_fetch_data_error(self, error_msg):
        print(f"Error occurred while fetching data: {error_msg}")
        self.set_progress_bar(100, "Failed fetching data")

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
            self.set_progress_bar(100, "Failed loading Movie info")
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
            self.animate_progress(0, 100, "Failed fetching series info")
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
                self.set_progress_bar(100, "Failed loading Series info")
            else:
                self.set_progress_bar(100, "Loaded Series info")

    def fetch_image(self, img_url, stream_type):
        image_fetcher = ImageFetcher(img_url, stream_type, self)
        image_fetcher.signals.finished.connect(self.process_image_data)
        image_fetcher.signals.error.connect(self.on_fetch_data_error)
        self.threadpool.start(image_fetcher)

    def process_image_data(self, image, stream_type):
        try:
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

    def favButtonPressed(self, stream_type, info_box):
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
            info_box.setFavorite(is_fav)
            
            #Set favorite parameter
            data['favorite'] = is_fav

            #Set data to currently selected item
            current_sel_item.setData(Qt.UserRole, data)

            fav_data = {}

            if path.isfile(self.favorites_file):
                try:
                    with open(self.favorites_file, 'r') as fav_file:
                        fav_data = json.load(fav_file)
                except (OSError, ValueError) as e:
                    print(f"Could not read favorites file, starting fresh: {e}")
                    fav_data = {}

            fav_key = 'series_ids' if stream_type == "Series" else 'stream_ids'
            ids = fav_data.get(fav_key) or []

            if is_fav:
                # Remove first to avoid duplicates if the entry was already in the list,
                # then append so the freshly-marked item sits at the end of the order
                # (issue #17 — preserve add-order in the Favorites view).
                ids = [i for i in ids if i != stream_id]
                ids.append(stream_id)
            else:
                ids = [i for i in ids if i != stream_id]

            fav_data[fav_key] = ids

            with open(self.favorites_file, 'w') as fav_file:
                json.dump(fav_data, fav_file, indent=4)

        except Exception as e:
            self.animate_progress(0, 100, "Failed adding to favorites")

            print(f"Failed adding to favorites: {e}")

    def _favorites_in_user_order(self, stream_type):
        # Returns the entries in `entries_per_stream_type[stream_type]` whose ids appear
        # in favorites.json, ordered by their position in that file (i.e. by the order
        # in which the user marked them). Falls back to catalog order if the file is
        # missing/corrupt — see issue #17.
        entries = self.entries_per_stream_type.get(stream_type, []) or []
        id_field = 'series_id' if stream_type == 'Series' else 'stream_id'
        fav_key  = 'series_ids' if stream_type == 'Series' else 'stream_ids'

        fav_data = {}
        if path.isfile(self.favorites_file):
            try:
                with open(self.favorites_file, 'r') as fav_file:
                    fav_data = json.load(fav_file)
            except (OSError, ValueError) as e:
                print(f"Could not read favorites file: {e}")

        ordered_ids = fav_data.get(fav_key, []) or []
        if not ordered_ids:
            # No favorites file order to follow — fall back to catalog scan, in catalog order.
            return [e for e in entries if e.get('favorite')]

        # Build a fast lookup, then return entries in favorites.json order, skipping
        # any ids that no longer exist in the catalog (e.g. removed by the provider).
        by_id = {e.get(id_field): e for e in entries}
        return [by_id[i] for i in ordered_ids if i in by_id]

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

            selected_item_text = selected_item.text()
            selected_item_data = selected_item.data(Qt.UserRole)

            #Check if All and Favorites category are not selected
            if (selected_item_text != self.all_categories_text and selected_item_text != self.fav_categories_text):
                category_id = selected_item_data['category_id']

            self.set_progress_bar(0, "Loading items")

            if stream_type == 'Series':
                #Reset navigation level
                self.series_navigation_level = 0

            #Clear items in list
            self.streaming_list_widgets[stream_type].clear()
            self.currently_loaded_streams[stream_type].clear()

            #Reset scrollbar position to top
            self.streaming_list_widgets[stream_type].scrollToTop()

            is_favorites_view = (selected_item_text == self.fav_categories_text)

            # For the Favorites view, walk the favorites.json id list so items
            # appear in the order the user marked them — not alphabetically and not
            # in the order the provider returned the catalog (issue #17).
            if is_favorites_view:
                ordered_entries = self._favorites_in_user_order(stream_type)
                for entry in ordered_entries:
                    item = QListWidgetItem(entry['name'])
                    item.setData(Qt.UserRole, entry)
                    self.currently_loaded_streams[stream_type].append(entry)
                    self.streaming_list_widgets[stream_type].addItem(item)
            else:
                for entry in self.entries_per_stream_type[stream_type]:
                    if selected_item_text == self.all_categories_text:
                        item = QListWidgetItem(entry['name'])
                        item.setData(Qt.UserRole, entry)

                        self.currently_loaded_streams[stream_type].append(entry)
                        self.streaming_list_widgets[stream_type].addItem(item)

                    elif entry.get('category_id') == category_id:
                        item = QListWidgetItem(entry['name'])
                        item.setData(Qt.UserRole, entry)

                        self.currently_loaded_streams[stream_type].append(entry)
                        self.streaming_list_widgets[stream_type].addItem(item)

            #Check if list is empty after process
            if self.streaming_list_widgets[stream_type].count() == 0:
                #Add list is empty text
                item = QListWidgetItem("No items in list...")

                self.streaming_list_widgets[stream_type].addItem(item)
            elif not is_favorites_view:
                #Sort list — but never re-sort the Favorites list, since that would
                #destroy the user's add-order (issue #17).
                self.sortList(self.streaming_search_bars[stream_type], 'streaming', stream_type, self.streaming_list_widgets, self.sorting_enabled, self.sorting_order)

            self.animate_progress(0, 100, "Loading finished")

        except Exception as e:
            print(f"Failed: {e}")

    def startOnlineWorker(self, stream_id, url):
        # Bail out early if the user disabled the traffic-light check.
        if not getattr(self, 'stream_status_enabled', True):
            return

        # Run the stream-status probe on the dedicated pool — see issue #74.
        online_worker = OnlineWorker(stream_id, url, self)
        online_worker.signals.finished.connect(self.ProcessStreamStatus)
        online_worker.signals.error.connect(self.onProcessStreamStatusError)
        self.status_threadpool.start(online_worker)

    def onProcessStreamStatusError(self, error_msg):
        print(f"Failed processing streaming status: {error_msg}")

        #Set stream status to unknown
        self.live_info_box.stream_status.setPixmap(QPixmap(self.path_to_unknown_status_icon).scaledToWidth(24))

    def ProcessStreamStatus(self, stream_id, stream_status):
        try:
            #Ensure user hasn't changed live channel before request came through
            last_clicked_item = self.prev_clicked_streaming_item.data(Qt.UserRole)
            if (stream_id != last_clicked_item['stream_id']):
                return

            if (stream_status == "True"):
                self.live_info_box.stream_status.setPixmap(QPixmap(self.path_to_online_status_icon).scaledToWidth(24))
            elif (stream_status == "Maybe"):
                self.live_info_box.stream_status.setPixmap(QPixmap(self.path_to_maybe_status_icon).scaledToWidth(24))
            else:
                self.live_info_box.stream_status.setPixmap(QPixmap(self.path_to_offline_status_icon).scaledToWidth(24))
        except Exception as e:
            print(f"Failed processing streaming status: {e}")

    def startEPGWorker(self, stream_id):
        #Create EPG thread worker that will fetch EPG data
        epg_worker = EPGWorker(self.server, self.username, self.password, stream_id, self)

        #Connect functions to signals
        epg_worker.signals.finished.connect(self.ProcessEPGData)
        epg_worker.signals.error.connect(self.onEPGFetchError)

        #Start EPG thread
        self.threadpool.start(epg_worker)

    def onEPGFetchError(self, error_msg):
        print(f"Failed fetching EPG data: {error_msg}")
        self.set_progress_bar(100, "Failed loading EPG data")

        #Set list view
        item = QTreeWidgetItem(["--/--/----", "--:--", "--:--", "Failed loading EPG data..."])
        self.live_info_box.live_EPG_info.addTopLevelItem(item)

    def ProcessEPGData(self, epg_data):
        try:
            #Clear EPG data
            self.live_info_box.live_EPG_info.clear()

            # is_fav = self.streaming_list_live.currentItem().data(Qt.UserRole).get('favorite', False)
            # self.live_info_box.setFavorite(is_fav)

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
            clicked_item_text = clicked_item.text()
            clicked_item_data = clicked_item.data(Qt.UserRole)

            #Check if item data is valid
            if not clicked_item_data:
                return

            #Get if clicked item is favorite
            is_fav = clicked_item_data.get('favorite', False)

            #Get stream type
            try:
                stream_type = clicked_item_data['stream_type']
            except:
                stream_type = ''

            #Skip when back button or already loaded series info
            if clicked_item.text() == self.go_back_text or ('series' in stream_type and self.series_navigation_level > 0):
                return

            #Show EPG data if live tv clicked
            if 'live' in stream_type:
                self.set_progress_bar(0, "Loading EPG data")

                #Set favorite button according to favorite value
                self.live_info_box.setFavorite(is_fav)

                #Set TV channel name in info window
                self.live_info_box.EPG_box_label.setText(f"{clicked_item_data['name']}")

                #Clear Stream Status indicator
                self.live_info_box.stream_status.setPixmap(QPixmap(self.path_to_unknown_status_icon).scaledToWidth(25))

                #Clear EPG data
                self.live_info_box.live_EPG_info.clear()
                item = QTreeWidgetItem(["...", "...", "...", "Loading EPG Data..."])
                self.live_info_box.live_EPG_info.addTopLevelItem(item)

                #Fetch cover image
                self.fetch_image(clicked_item_data['stream_icon'], 'Live')

                # Fetch stream status
                self.startOnlineWorker(clicked_item_data['stream_id'], clicked_item_data['url'])

                #Fetch EPG data
                self.startEPGWorker(clicked_item_data['stream_id'])

            #Show movie info if movie clicked
            elif 'movie' in stream_type:
                self.set_progress_bar(0, "Loading Movie info")

                #Set favorite button according to favorite value
                self.movies_info_box.setFavorite(is_fav)

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
                self.series_info_box.setFavorite(is_fav)

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
            self.animate_progress(0, 100, "Stream URL not found")

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
                print(f"Going to play: {url}")
                self.animate_progress(0, 100, "Loading player for streaming")

                # Embedded VLC marker — short-circuit before constructing any subprocess
                # command. The marker is set when the user picks "Embedded VLC" in
                # Settings (so we don't store a real path that could be invoked by accident).
                if self.external_player_command == "<embedded-vlc>":
                    self._play_embedded(url)
                    return

                self._launch_player_command(self.external_player_command, url)

            except Exception as e:
                import traceback
                self.animate_progress(0, 100, "Failed playing stream")
                print(f"Failed playing stream [{url}]: {e}")
                traceback.print_exc()
                try:
                    error_dialog = QMessageBox(self)
                    error_dialog.setIcon(QMessageBox.Warning)
                    error_dialog.setWindowTitle("Player failed to launch")
                    error_dialog.setText(
                        f"Could not launch the external player.\n\n"
                        f"Player: {self.external_player_command}\n"
                        f"Error: {e}\n\n"
                        f"See log.txt for the full traceback."
                    )
                    error_dialog.setStandardButtons(QMessageBox.Ok)
                    error_dialog.exec_()
                except Exception:
                    pass
        else:
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

                self.save_external_player_command()
                self._refresh_current_player_label()

                self.animate_progress(0, 100, "Selected external media player")

    def use_embedded_player(self):
        # User clicked "Use Internal Player (VLC)". Check libvlc is reachable BEFORE
        # we persist the choice — otherwise the user gets a silent failure later
        # when they try to play something.
        if not EmbeddedPlayerWindow.is_available():
            error_dialog = QMessageBox(self)
            error_dialog.setIcon(QMessageBox.Warning)
            error_dialog.setWindowTitle("Embedded player unavailable")
            error_dialog.setText(
                "The internal VLC player needs libvlc installed on this machine.\n\n"
                "Install VLC from https://www.videolan.org/vlc/ and then click this button again.\n"
                "(After installing, you may also need: pip install python-vlc)"
            )
            error_dialog.setStandardButtons(QMessageBox.Ok)
            error_dialog.exec_()
            return

        self.external_player_command = "<embedded-vlc>"
        self.save_external_player_command()
        self._refresh_current_player_label()
        self.animate_progress(0, 100, "Internal VLC player enabled")

    def _refresh_current_player_label(self):
        if not hasattr(self, "current_player_label"):
            return
        cmd = getattr(self, "external_player_command", "") or ""
        if cmd == "<embedded-vlc>":
            self.current_player_label.setText("Active player: Internal VLC (embedded)")
        elif cmd:
            self.current_player_label.setText(f"Active player: {cmd}")
        else:
            self.current_player_label.setText("No player selected — choose one above.")

    def _play_embedded(self, url):
        # Lazily create the embedded VLC window — keeping a single instance lets
        # the user switch channels without rebuilding the libvlc context each time.
        if not hasattr(self, "_embedded_player_window") or self._embedded_player_window is None:
            try:
                self._embedded_player_window = EmbeddedPlayerWindow(self, user_agent=self.current_user_agent)
                self._embedded_player_window.playback_failed.connect(self._on_embedded_playback_failed)
            except Exception as e:
                import traceback
                traceback.print_exc()
                error_dialog = QMessageBox(self)
                error_dialog.setIcon(QMessageBox.Critical)
                error_dialog.setWindowTitle("Embedded player error")
                error_dialog.setText(
                    f"Could not start the internal VLC player:\n{e}\n\n"
                    "Install VLC from https://www.videolan.org/vlc/ and try again."
                )
                error_dialog.exec_()
                return

        try:
            playlist, current_idx, title = self._collect_visible_playlist(url)
            self._embedded_player_window.play_url(
                url, title=title, playlist=playlist, index=current_idx,
            )
            self.animate_progress(0, 100, "Playing in internal player")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.animate_progress(0, 100, "Failed playing stream")
            print(f"Embedded play failed [{url}]: {e}")

    def _launch_player_command(self, player_command, url):
        ua = (self.current_user_agent or "").strip()
        exe_lower = player_command.lower()

        if is_linux:
            if not os.access(player_command, os.X_OK):
                raise RuntimeError(f"Selected player is not executable: {player_command}")

            player_cmd = [player_command]
            if exe_lower.endswith("vlc") and ua:
                player_cmd.append(f"--http-user-agent={ua}")
            elif exe_lower.endswith(("mpv", "mpv.com")) and ua:
                player_cmd.append(f"--user-agent={ua}")
            player_cmd.append(url)
            subprocess.Popen(player_cmd)
            return

        if is_windows:
            exe_q = f'"{player_command}"'
            url_q = f'"{url}"'

            if "potplayermini64.exe" in exe_lower or "potplayer" in exe_lower:
                ua_arg = f' /user_agent="{ua}"' if ua else ""
                player_cmd = f'{exe_q} {url_q}{ua_arg}'
            elif exe_lower.endswith(("mpv.exe", "mpv.com")) or "\\mpv\\" in exe_lower:
                ua_arg = f' --user-agent="{ua}"' if ua else ""
                player_cmd = f'{exe_q}{ua_arg} {url_q}'
            elif exe_lower.endswith("vlc.exe"):
                ua_arg = f' --http-user-agent="{ua}"' if ua else ""
                player_cmd = f'{exe_q}{ua_arg} {url_q}'
            else:
                player_cmd = f'{exe_q} {url_q}'

            subprocess.Popen(player_cmd)
            return

        subprocess.Popen([player_command, url])

    def _on_embedded_playback_failed(self, url, reason):
        print(f"Embedded player failed [{url}]: {reason}")

        try:
            self._embedded_player_window.hide()
        except Exception:
            pass

        self.animate_progress(0, 100, "Embedded playback failed, opening direct stream")

        try:
            vlc_executable = EmbeddedPlayerWindow.find_vlc_executable()
            if vlc_executable:
                self._launch_player_command(vlc_executable, url)
                return
        except Exception as e:
            print(f"Embedded fallback via VLC failed [{url}]: {e}")

        if QDesktopServices.openUrl(QUrl(url)):
            return

        error_dialog = QMessageBox(self)
        error_dialog.setIcon(QMessageBox.Warning)
        error_dialog.setWindowTitle("Playback failed")
        error_dialog.setText(
            "The internal VLC player could not start this stream, "
            "and the direct-stream fallback also failed."
        )
        error_dialog.setStandardButtons(QMessageBox.Ok)
        error_dialog.exec_()

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

    def SearchBarKeyPressed(self, e, search_bar, list_content_type, stream_type, list_widgets, history_list, history_list_idx):
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

            #If searching in category list
            if list_content_type == 'category':
                #Check if list is empty
                if not self.currently_loaded_categories[stream_type]:
                    return

                #Enable or disable sorting
                self.category_list_widgets[stream_type].setSortingEnabled(self.sorting_enabled)

                #When sorting is enabled, set sort order, 0: A-Z, 1: Z-A
                if self.sorting_enabled:
                    self.category_list_widgets[stream_type].sortItems(self.sorting_order)

                self.category_list_widgets[stream_type].clear()

                for entry in self.currently_loaded_categories[stream_type]:
                    if text.lower() in entry.get('category_name', '').lower():
                        item = QListWidgetItem(entry['category_name'])
                        item.setData(Qt.UserRole, entry)

                        self.category_list_widgets[stream_type].addItem(item)

                #Disable sorting
                self.category_list_widgets[stream_type].setSortingEnabled(False)

                #if search bar is empty
                if not text:
                    # Add 'All' and 'Favorites' categories to top
                    itemAll = QListWidgetItem(self.all_categories_text)
                    itemAll.setData(Qt.UserRole, {'category_name': self.all_categories_text})
                    self.category_list_widgets[stream_type].insertItem(0, itemAll)

                    itemFav = QListWidgetItem(self.fav_categories_text)
                    itemFav.setData(Qt.UserRole, {'category_name': self.fav_categories_text})
                    self.category_list_widgets[stream_type].insertItem(1, itemFav)

                #Check if no search results found
                num_of_items = self.category_list_widgets[stream_type].count()
                if not num_of_items:
                    self.category_list_widgets[stream_type].addItem("No search results found...")

            #If searching in streaming content list
            elif list_content_type == 'streaming':
                #Check if list is empty
                if not self.currently_loaded_streams[stream_type]:
                    return

                #Enable or disable sorting
                self.streaming_list_widgets[stream_type].setSortingEnabled(self.sorting_enabled)

                #When sorting is enabled, set sort order, 0: A-Z, 1: Z-A
                if self.sorting_enabled:
                    self.streaming_list_widgets[stream_type].sortItems(self.sorting_order)

                self.streaming_list_widgets[stream_type].clear()

                match self.series_navigation_level:
                    case 0: #LIVE/VOD/Series
                        for entry in self.currently_loaded_streams[stream_type]:
                            if text.lower() in entry['name'].lower():
                                item = QListWidgetItem(entry['name'])
                                item.setData(Qt.UserRole, entry)

                                self.streaming_list_widgets[stream_type].addItem(item)
                    case 1: #Seasons
                        self.streaming_list_widgets[stream_type].addItem(self.go_back_text)

                        # Sort numerically so "Season 10" follows "Season 9" (issue #18).
                        def _season_sort_key(k):
                            try:
                                return (0, int(k))
                            except (TypeError, ValueError):
                                return (1, str(k).lower())

                        for season in sorted(self.currently_loaded_streams['Seasons'].keys(), key=_season_sort_key):
                            if text.lower() in f"season {season}".lower():
                                item = QListWidgetItem(f"Season {season}")
                                item.setData(Qt.UserRole, self.currently_loaded_streams['Seasons'][season])

                                self.streaming_list_widgets[stream_type].addItem(item)
                    case 2: #Episodes
                        self.streaming_list_widgets[stream_type].addItem(self.go_back_text)

                        for episode in self.currently_loaded_streams['Episodes']:
                            if text.lower() in episode['title'].lower():
                                item = QListWidgetItem(episode['title'])
                                item.setData(Qt.UserRole, episode)

                                self.streaming_list_widgets[stream_type].addItem(item)

                #Check if no search results found
                num_of_items = self.streaming_list_widgets[stream_type].count()
                if not (num_of_items - (self.series_navigation_level > 0)):
                    self.streaming_list_widgets[stream_type].addItem("No search results found...")

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
            return config['ExternalPlayer'].get('Command', '')

        return ""

    def save_external_player_command(self):
        config = configparser.ConfigParser()
        try:
            config.read(self.user_data_file)
        except (configparser.Error, UnicodeDecodeError):
            config = configparser.ConfigParser()

        config['ExternalPlayer'] = {'Command': self.external_player_command}

        try:
            with open(self.user_data_file, 'w') as config_file:
                config.write(config_file)
        except OSError as e:
            print(f"Could not write user data file: {e}")

    def open_address_book(self):
        dialog = AccountManager(self)
        dialog.exec_()

def _install_logging():
    # Write every print() / unhandled exception to log.txt next to the script.
    # The app used to silently die when an external player launch failed; now the
    # traceback ends up on disk where the user can paste it into a bug report.
    import logging, atexit, traceback as _tb

    log_path = path.join(path.dirname(path.abspath(__file__)), "log.txt")

    class _StreamToLogger:
        def __init__(self, original, level):
            self.original = original
            self.level    = level
            self._buf     = ""
        def write(self, data):
            try:
                if self.original is not None:
                    self.original.write(data)
            except Exception:
                pass
            self._buf += data
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                if line:
                    logging.log(self.level, line)
        def flush(self):
            try:
                if self.original is not None:
                    self.original.flush()
            except Exception:
                pass
        def isatty(self):
            return False

    try:
        logging.basicConfig(
            filename=log_path,
            filemode='a',
            level=logging.INFO,
            format='%(asctime)s %(levelname)s %(message)s',
            encoding='utf-8',
        )
    except TypeError:
        # Python <3.9 has no encoding kwarg — fall back to a manual handler.
        handler = logging.FileHandler(log_path, mode='a', encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    sys.stdout = _StreamToLogger(sys.stdout, logging.INFO)
    sys.stderr = _StreamToLogger(sys.stderr, logging.ERROR)

    def _excepthook(exc_type, exc, tb):
        logging.error("Unhandled exception:\n%s", "".join(_tb.format_exception(exc_type, exc, tb)))
        sys.__excepthook__(exc_type, exc, tb)
    sys.excepthook = _excepthook

    logging.info("=== Session start (log lives at %s) ===", log_path)
    atexit.register(lambda: logging.info("=== Session end ==="))

def main():
    _install_logging()
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # Set an application-wide font that has Arabic/CJK glyphs out of the box —
    # otherwise non-Latin scripts (Arabic, in particular) render as a row of '?'
    # because Qt picks a font whose glyph table is missing those code points.
    if is_windows:
        app.setFont(QFont("Segoe UI", 10))
    elif is_mac:
        app.setFont(QFont("Helvetica Neue", 13))
    else:
        # Most Linux desktops have Noto Sans (which covers Arabic via Noto Naskh fallback).
        app.setFont(QFont("Noto Sans", 10))

    player = IPTVPlayerApp()
    player.show()
    QtWidgets.qApp.processEvents()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

