import sys
import os
import time
import requests
import subprocess
import configparser
import re
import json
import html
from lxml import etree
from datetime import datetime
from dateutil import parser, tz
import xml.etree.ElementTree as ET
from PyQt5.QtGui import QIcon, QFont, QImage, QPixmap
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize, QObject, pyqtSignal, QRunnable, pyqtSlot, QThreadPool
)
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QLineEdit, QLabel, QPushButton,
    QListWidget, QWidget, QFileDialog, QCheckBox, QSizePolicy, QHBoxLayout,
    QDialog, QFormLayout, QDialogButtonBox, QTabWidget, QListWidgetItem,
    QSpinBox, QMenu, QAction, QTextEdit, QGridLayout, QMessageBox
)

import threading

CUSTOM_USER_AGENT = (
    "Connection: Keep-Alive User-Agent: okhttp/5.0.0-alpha.2 "
    "Accept-Encoding: gzip, deflate"
)

def normalize_channel_name(name):
    name = name.lower().strip()
    name = re.sub(r'\s+', ' ', name)
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\b(hd|sd|channel|tv)\b', '', name)
    name = name.strip()
    return name

class FetchDataWorkerSignals(QObject):
    finished        = pyqtSignal(dict, dict, dict)
    error           = pyqtSignal(str)
    progress_bar    = pyqtSignal(int, int, str)

class FetchDataWorker(QRunnable):
    def __init__(self, server, username, password, http_method):
        super().__init__()
        self.server = server
        self.username = username
        self.password = password
        # self.http_method = http_method
        self.signals = FetchDataWorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            categories_per_stream_type = {
                'LIVE': [],
                'Movies': [],
                'Series': []
            }
            entries_per_stream_type = {
                'LIVE': [],
                'Movies': [],
                'Series': []
            }

            headers = {'User-Agent': CUSTOM_USER_AGENT}
            params = {
                'username': self.username,
                'password': self.password,
                'action': ''
            }

            host_url = f"{self.server}/player_api.php"

            print("Going to receive data")

            #Get IPTV info
            self.signals.progress_bar.emit(0, 5, "Fetching IPTV info")
            try:
                iptv_info_resp = requests.get(host_url, params=params, headers=headers, timeout=10)
                iptv_info_resp.raise_for_status()
                iptv_info_data = iptv_info_resp.json()
            except Exception as e:
                print(f"failed fetching IPTV data: {e}")

            #Get all category data
            print("Fetching categories")
            self.signals.progress_bar.emit(5, 10, "Fetching LIVE Categories")
            try:
                params['action'] = 'get_live_categories'
                live_category_resp = requests.get(host_url, params=params, headers=headers, timeout=10)
                print(live_category_resp.raise_for_status())

                categories_per_stream_type['LIVE'] = live_category_resp.json()
            except Exception as e:
                print(f"failed fetching LIVE categories: {e}")

            self.signals.progress_bar.emit(10, 20, "Fetching VOD Categories")
            try:
                params['action'] = 'get_vod_categories'
                movies_category_resp = requests.get(host_url, params=params, headers=headers, timeout=10)
                print(movies_category_resp.raise_for_status())

                categories_per_stream_type['Movies'] = movies_category_resp.json()
            except Exception as e:
                print(f"failed fetching VOD categories: {e}")

            self.signals.progress_bar.emit(20, 30, "Fetching Series Categories")
            try:
                params['action'] = 'get_series_categories'
                series_category_resp = requests.get(host_url, params=params, headers=headers, timeout=10)
                print(series_category_resp.raise_for_status())

                categories_per_stream_type['Series'] = series_category_resp.json()
            except Exception as e:
                print(f"failed fetching Series categories: {e}")

            print("Fetching streaming data")
            #Get all streaming data
            self.signals.progress_bar.emit(30, 40, "Fetching LIVE Streaming data")
            try:
                params['action'] = 'get_live_streams'
                live_streams_resp = requests.get(host_url, params=params, headers=headers, timeout=10)
                print(live_streams_resp.raise_for_status())

                entries_per_stream_type['LIVE'] = live_streams_resp.json()
            except Exception as e:
                print(f"failed fetching LIVE streams: {e}")

            self.signals.progress_bar.emit(40, 60, "Fetching VOD Streaming data")
            try:
                params['action'] = 'get_vod_streams'
                movies_streams_resp = requests.get(host_url, params=params, headers=headers, timeout=10)
                print(movies_streams_resp.raise_for_status())

                entries_per_stream_type['Movies'] = movies_streams_resp.json()
            except Exception as e:
                print(f"failed fetching VOD streams: {e}")

            self.signals.progress_bar.emit(60, 80, "Fetching Series Streaming data")
            try:
                params['action'] = 'get_series'
                series_streams_resp = requests.get(host_url, params=params, headers=headers, timeout=10)
                print(series_streams_resp.raise_for_status())

                entries_per_stream_type['Series'] = series_streams_resp.json()
            except Exception as e:
                print(f"failed fetching Series streams: {e}")


            # all_cached_data = json.dumps({
            #         'LIVE categories': categories_per_stream_type['LIVE'],
            #         'Movies categories': categories_per_stream_type['Movies'],
            #         'Series categories': categories_per_stream_type['Series'],
            #         'LIVE': entries_per_stream_type['LIVE'],
            #         'Movies': entries_per_stream_type['Movies'],
            #         'Series': entries_per_stream_type['Series']
            #     }, 
            #     indent=4)

            # with open("all_cached_data.json", 'w') as cache_file:
            #     cache_file.write(all_cached_data)

            #TODO Fetch EPG data

            # self.set_progress_bar(100, "Finished loading data")
            self.signals.progress_bar.emit(80, 100, "Finished Fetching data")

            print("setting url in streaming data")
            #Make streaming URL in each entry except for the series
            for tab_name in entries_per_stream_type.keys():
                for idx, entry in enumerate(entries_per_stream_type[tab_name]):
                    stream_type         = entry.get('stream_type', 'series')
                    stream_id           = entry.get("stream_id")
                    container_extension = entry.get("container_extension", "m3u8")
                    if stream_id:
                        entries_per_stream_type[tab_name][idx]["url"] = f"{self.server}/{stream_type}/{self.username}/{self.password}/{stream_id}.{container_extension}"
                    else:
                        entries_per_stream_type[tab_name][idx]["url"] = None

                    if stream_type == 'series':
                        entries_per_stream_type[tab_name][idx]["stream_type"] = stream_type

            self.signals.finished.emit(iptv_info_data, categories_per_stream_type, entries_per_stream_type)

            print("finished")

        except Exception as e:
            print(f"Exception! {e}")
            self.signals.error.emit(str(e))

class EPGWorkerSignals(QObject):
    finished = pyqtSignal(dict, dict)
    error = pyqtSignal(str)

class EPGWorker(QRunnable):
    def __init__(self, server, username, password, http_method):
        super().__init__()
        self.server = server
        self.username = username
        self.password = password
        self.http_method = http_method
        self.signals = EPGWorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            cache_file = 'epg_cache1.xml'
            cache_valid = False
            if os.path.exists(cache_file):
                cache_age = time.time() - os.path.getmtime(cache_file)
                if cache_age < 3600:  
                    cache_valid = True

            if cache_valid:
                with open(cache_file, 'rb') as f:
                    epg_xml_data = f.read()
            else:
                epg_url = f"{self.server}/xmltv.php?username={self.username}&password={self.password}"
                headers = {'User-Agent': CUSTOM_USER_AGENT}
                if self.http_method == 'POST':
                    response = requests.post(epg_url, headers=headers, timeout=10)
                else:
                    print("requesting EPG")
                    response = requests.get(epg_url, headers=headers, timeout=10)
                response.raise_for_status()
                epg_xml_data = response.content
                with open(cache_file, 'wb') as f:
                    f.write(epg_xml_data)

            print("going to parse epg_data")
            epg_data, channel_id_to_names = self.parse_epg_data(epg_xml_data)
            print("Finished parsing epg data")
            self.signals.finished.emit(epg_data, channel_id_to_names)
        except Exception as e:
            self.signals.error.emit(str(e))

    def parse_epg_data(self, epg_xml_data):
        epg_dict = {}
        channel_id_to_names = {}
        try:
            epg_tree = ET.fromstring(epg_xml_data)
            for channel in epg_tree.findall('channel'):
                channel_id = channel.get('id')
                if channel_id:
                    channel_id = channel_id.strip().lower()
                    display_names = []
                    for display_name_elem in channel.findall('display-name'):
                        if display_name_elem.text:
                            display_name = display_name_elem.text.strip()
                            normalized_name = normalize_channel_name(display_name)
                            display_names.append(normalized_name)
                    channel_id_to_names[channel_id] = display_names

            for programme in epg_tree.findall('programme'):
                channel_id = programme.get('channel')
                if channel_id:
                    channel_id = channel_id.strip().lower()
                start_time = programme.get('start')
                stop_time = programme.get('stop')
                title_elem = programme.find('title')
                description_elem = programme.find('desc')

                title = title_elem.text.strip() if title_elem is not None and title_elem.text else ''
                description = description_elem.text.strip() if description_elem is not None and description_elem.text else ''

                epg_entry = {
                    'start_time': start_time,
                    'stop_time': stop_time,
                    'title': title,
                    'description': description
                }

                if channel_id not in epg_dict:
                    epg_dict[channel_id] = []
                epg_dict[channel_id].append(epg_entry)

            return epg_dict, channel_id_to_names

        except Exception as e:
            print(f"Error parsing EPG data: {e}")
            return {}, {}

class AddressBookDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Address Book")
        self.setMinimumSize(400, 300)
        self.parent = parent

        layout = QtWidgets.QVBoxLayout(self)

        startup_credential_layout = QHBoxLayout()
        self.startup_credential_label = QLabel("Startup address:")
        self.startup_credential_options = QtWidgets.QComboBox()
        self.startup_credential_options.currentTextChanged.connect(self.set_startup_credentials)
        startup_credential_layout.addWidget(self.startup_credential_label)
        startup_credential_layout.addWidget(self.startup_credential_options)
        layout.addLayout(startup_credential_layout)

        self.credentials_list = QtWidgets.QListWidget()
        layout.addWidget(self.credentials_list)

        button_layout = QHBoxLayout()
        self.add_button = QPushButton("Add")
        self.add_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogNewFolder))
        self.select_button = QPushButton("Select")
        self.select_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogYesButton))
        self.delete_button = QPushButton("Delete")
        self.delete_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogCancelButton))
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.select_button)
        button_layout.addWidget(self.delete_button)
        layout.addLayout(button_layout)

        self.load_saved_credentials()

        self.add_button.clicked.connect(self.add_credentials)
        self.select_button.clicked.connect(self.select_credentials)
        self.delete_button.clicked.connect(self.delete_credentials)
        self.credentials_list.itemDoubleClicked.connect(self.double_click_credentials)

    def set_startup_credentials(self):
        selected_item = self.startup_credential_options.currentText()

        config = configparser.ConfigParser()
        config.read('credentials.ini')

        if 'Startup credentials' not in config:
            config['Startup credentials'] = {}

        config['Startup credentials']['startup_credentials'] = f"{selected_item}"

        with open('credentials.ini', 'w') as config_file:
            config.write(config_file)

    def load_saved_credentials(self):
        self.startup_credential_options.currentTextChanged.disconnect(self.set_startup_credentials)

        self.credentials_list.clear()
        self.startup_credential_options.clear()
        self.startup_credential_options.addItem("None")

        config = configparser.ConfigParser()
        config.read('credentials.ini')

        if 'Credentials' in config:
            for key in config['Credentials']:
                self.credentials_list.addItem(key)
                self.startup_credential_options.addItem(key)

        if 'Startup credentials' in config:
            selected_startup_credentials = config['Startup credentials']['startup_credentials']
            idx = self.startup_credential_options.findText(f"{selected_startup_credentials}")
            self.startup_credential_options.setCurrentIndex(idx)

        self.startup_credential_options.currentTextChanged.connect(self.set_startup_credentials)

    def add_credentials(self):
        dialog = AddCredentialsDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            method, name, *credentials = dialog.get_credentials()
            if name:
                config = configparser.ConfigParser()
                config.read('credentials.ini')
                if 'Credentials' not in config:
                    config['Credentials'] = {}
                if method == 'manual':
                    server, username, password = credentials
                    config['Credentials'][name] = f"manual|{server}|{username}|{password}"
                elif method == 'm3u_plus':
                    m3u_url, = credentials
                    config['Credentials'][name] = f"m3u_plus|{m3u_url}"
                with open('credentials.ini', 'w') as config_file:
                    config.write(config_file)
                self.load_saved_credentials()

    def select_credentials(self):
        selected_item = self.credentials_list.currentItem()
        if selected_item:
            name = selected_item.text()
            config = configparser.ConfigParser()
            config.read('credentials.ini')
            if 'Credentials' in config and name in config['Credentials']:
                data = config['Credentials'][name]
                if data.startswith('manual|'):
                    _, server, username, password = data.split('|')
                    self.parent.server_entry.setText(server)
                    self.parent.username_entry.setText(username)
                    self.parent.password_entry.setText(password)
                    self.parent.login()
                elif data.startswith('m3u_plus|'):
                    _, m3u_url = data.split('|', 1)
                    self.parent.extract_credentials_from_m3u_plus_url(m3u_url)
                    self.parent.login()
                self.accept()

    def double_click_credentials(self, item):
        self.select_credentials()
        self.accept()

    def delete_credentials(self):
        selected_item = self.credentials_list.currentItem()
        if selected_item:
            name = selected_item.text()
            config = configparser.ConfigParser()
            config.read('credentials.ini')
            if 'Credentials' in config and name in config['Credentials']:
                del config['Credentials'][name]
                with open('credentials.ini', 'w') as config_file:
                    config.write(config_file)
                self.load_saved_credentials()

class AddCredentialsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Credentials")
        layout = QtWidgets.QVBoxLayout(self)

        self.method_selector = QtWidgets.QComboBox()
        self.method_selector.addItems(["Manual Entry", "m3u_plus URL Entry"])
        layout.addWidget(QtWidgets.QLabel("Select Method:"))
        layout.addWidget(self.method_selector)

        self.stack = QtWidgets.QStackedWidget()
        layout.addWidget(self.stack)

        self.manual_form = QtWidgets.QWidget()
        manual_layout = QFormLayout(self.manual_form)
        self.name_entry_manual = QLineEdit()
        self.server_entry = QLineEdit()
        self.username_entry = QLineEdit()
        self.password_entry = QLineEdit()
        self.password_entry.setEchoMode(QLineEdit.Password)
        manual_layout.addRow("Name:", self.name_entry_manual)
        manual_layout.addRow("Server URL:", self.server_entry)
        manual_layout.addRow("Username:", self.username_entry)
        manual_layout.addRow("Password:", self.password_entry)

        self.m3u_form = QtWidgets.QWidget()
        m3u_layout = QFormLayout(self.m3u_form)
        self.name_entry_m3u = QLineEdit()
        self.m3u_url_entry = QLineEdit()
        m3u_layout.addRow("Name:", self.name_entry_m3u)
        m3u_layout.addRow("m3u_plus URL:", self.m3u_url_entry)

        self.stack.addWidget(self.manual_form)
        self.stack.addWidget(self.m3u_form)

        self.method_selector.currentIndexChanged.connect(self.stack.setCurrentIndex)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        layout.addWidget(buttons)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)

    def validate_and_accept(self):
        method = self.method_selector.currentText()
        if method == "Manual Entry":
            name = self.name_entry_manual.text().strip()
            server = self.server_entry.text().strip()
            username = self.username_entry.text().strip()
            password = self.password_entry.text().strip()
            if not name or not server or not username or not password:
                QtWidgets.QMessageBox.warning(self, "Input Error", "Please fill all fields for Manual Entry.")
                return
            self.accept()
        else:
            name = self.name_entry_m3u.text().strip()
            m3u_url = self.m3u_url_entry.text().strip()
            if not name or not m3u_url:
                QtWidgets.QMessageBox.warning(self, "Input Error", "Please fill all fields for m3u_plus URL Entry.")
                return
            self.accept()

    def get_credentials(self):
        method = self.method_selector.currentText()
        if method == "Manual Entry":
            name = self.name_entry_manual.text().strip()
            server = self.server_entry.text().strip()
            username = self.username_entry.text().strip()
            password = self.password_entry.text().strip()
            return ('manual', name, server, username, password)
        else:
            name = self.name_entry_m3u.text().strip()
            m3u_url = self.m3u_url_entry.text().strip()
            return ('m3u_plus', name, m3u_url)

class IPTVPlayerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Xtream IPTV Player by MY-1 V3.5")
        self.resize(1300, 900)

        self.default_font_size = 10
        self.go_back_text = " Go back"
        self.all_categories_text = " All"

        #navigation level indicates in what list level we are
        #LIVE and VOD have no navigation levels.
        #Series has 0: Series, 1: Seasons, 2: Episodes
        self.series_navigation_level = 0
        self.series_info_data = {}

        self.categories_per_stream_type = {}
        self.entries_per_stream_type = {
            'LIVE': [],
            'Movies': [],
            'Series': []
        }

        self.currently_loaded_entries = {
            'LIVE': [],
            'Movies': [],
            'Series': [],
            'Seasons': [],
            'Episodes': []
        }

        self.navigation_stacks = {
            'LIVE': [],
            'Movies': [],
            'Series': []
        }
        self.external_player_command = ""
        self.load_external_player_command()

        self.top_level_scroll_positions = {
            'LIVE': 0,
            'Movies': 0,
            'Series': 0
        }

        self.server = ""
        self.username = ""
        self.password = ""
        self.login_type = None  
        self.epg_data = {}  
        self.channel_id_to_names = {}  
        self.epg_last_updated = None  
        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(10)
        self.epg_id_mapping = {}
        self.epg_name_map = {}

        self.go_back_icon = self.style().standardIcon(QtWidgets.QStyle.SP_ArrowBack)
        self.live_channel_icon = self.style().standardIcon(QtWidgets.QStyle.SP_MediaVolume)
        self.movies_channel_icon = self.style().standardIcon(QtWidgets.QStyle.SP_MediaPlay)
        self.series_channel_icon = self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(10)

        #Create tab widget
        self.tab_widget = QTabWidget()
        content_layout.addWidget(self.tab_widget)

        self.tab_icon_size = QSize(24, 24)
        live_icon       = self.style().standardIcon(QtWidgets.QStyle.SP_MediaVolume)
        movies_icon     = self.style().standardIcon(QtWidgets.QStyle.SP_MediaPlay)
        series_icon     = self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon)
        info_icon       = self.style().standardIcon(QtWidgets.QStyle.SP_MessageBoxInformation)
        settings_icon   = self.style().standardIcon(QtWidgets.QStyle.SP_DriveCDIcon)

        self.live_tab       = QWidget()
        self.movies_tab     = QWidget()
        self.series_tab     = QWidget()
        self.info_tab       = QWidget()
        self.settings_tab   = QWidget()

        self.tab_widget.addTab(self.live_tab,       live_icon,      "LIVE")
        self.tab_widget.addTab(self.movies_tab,     movies_icon,    "Movies")
        self.tab_widget.addTab(self.series_tab,     series_icon,    "Series")
        self.tab_widget.addTab(self.info_tab,       info_icon,      "Info")
        self.tab_widget.addTab(self.settings_tab,   settings_icon,  "Settings")

        self.live_layout        = QGridLayout(self.live_tab)
        self.movies_layout      = QGridLayout(self.movies_tab)
        self.series_layout      = QGridLayout(self.series_tab)
        self.info_tab_layout    = QVBoxLayout(self.info_tab)
        self.settings_layout    = QVBoxLayout(self.settings_tab)

        self.search_bar_live = QLineEdit()
        self.search_bar_live.setPlaceholderText("Search Live Channels...")
        self.search_bar_live.setClearButtonEnabled(True)
        self.add_search_icon(self.search_bar_live)
        self.search_bar_live.textChanged.connect(lambda text: self.search_in_list('LIVE', text))

        self.search_bar_movies = QLineEdit()
        self.search_bar_movies.setPlaceholderText("Search Movies...")
        self.search_bar_movies.setClearButtonEnabled(True)
        self.add_search_icon(self.search_bar_movies)
        self.search_bar_movies.textChanged.connect(lambda text: self.search_in_list('Movies', text))

        self.search_bar_series = QLineEdit()
        self.search_bar_series.setPlaceholderText("Search Series...")
        self.search_bar_series.setClearButtonEnabled(True)
        self.add_search_icon(self.search_bar_series)
        self.search_bar_series.textChanged.connect(lambda text: self.search_in_list('Series', text))

        self.result_display = QTextEdit(self.info_tab)
        self.result_display.setReadOnly(True)
        default_font = QFont()
        default_font.setPointSize(self.default_font_size)
        self.result_display.setFont(default_font)

        self.info_tab_initialized = False

        #Create lists for channels
        self.channel_list_live      = QListWidget()
        self.channel_list_movies    = QListWidget()
        self.channel_list_series    = QListWidget()

        #Enable sorting
        self.channel_list_live.setSortingEnabled(True)
        self.channel_list_movies.setSortingEnabled(True)
        self.channel_list_series.setSortingEnabled(True)

        self.list_widgets = {
            'LIVE': self.channel_list_live,
            'Movies': self.channel_list_movies,
            'Series': self.channel_list_series,
        }

        #Create lists for categories
        self.category_list_live     = QListWidget()
        self.category_list_movies   = QListWidget()
        self.category_list_series   = QListWidget()

        self.category_list_live.setSortingEnabled(True)
        self.category_list_movies.setSortingEnabled(True)
        self.category_list_series.setSortingEnabled(True)

        self.category_list_widgets = {
            'LIVE': self.category_list_live,
            'Movies': self.category_list_movies,
            'Series': self.category_list_series,
        }

        standard_icon_size = QSize(24, 24)
        for list_widget in [self.channel_list_live, self.channel_list_movies, self.channel_list_series, self.category_list_live, self.category_list_movies, self.category_list_series]:
            list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            list_widget.setIconSize(standard_icon_size)
            list_widget.setStyleSheet("""
                QListWidget::item {
                    padding-top: 5px;
                    padding-bottom: 5px;
                }
            """)

        #Add widgets to tabs
        self.live_layout.addWidget(self.search_bar_live, 0, 0, 1, 2)
        self.live_layout.addWidget(self.category_list_live, 1, 0)
        self.live_layout.addWidget(self.channel_list_live, 1, 1)

        self.movies_layout.addWidget(self.search_bar_movies, 0, 0, 1, 2)
        self.movies_layout.addWidget(self.category_list_movies, 1, 0)
        self.movies_layout.addWidget(self.channel_list_movies, 1, 1)

        self.series_layout.addWidget(self.search_bar_series, 0, 0, 1, 2)
        self.series_layout.addWidget(self.category_list_series, 1, 0)
        self.series_layout.addWidget(self.channel_list_series, 1, 1)
        
        self.info_tab_layout.addWidget(self.result_display)

        #Create items in settings tab
        self.settings_layout.setSpacing(20)
        self.settings_layout.setAlignment(Qt.AlignTop)

        row1_layout = QHBoxLayout()
        # row1_layout.setSpacing(15)

        self.server_label = QLabel("Server URL:")
        self.server_label.setFixedWidth(100)
        self.server_entry = QLineEdit()
        self.server_entry.setPlaceholderText("Enter Server URL...")
        self.server_entry.setClearButtonEnabled(True)

        self.username_label = QLabel("Username:")
        self.username_label.setFixedWidth(100)
        self.username_entry = QLineEdit()
        self.username_entry.setPlaceholderText("Enter Username...")
        self.username_entry.setClearButtonEnabled(True)

        self.password_label = QLabel("Password:")
        self.password_label.setFixedWidth(100)
        self.password_entry = QLineEdit()
        self.password_entry.setPlaceholderText("Enter Password...")
        self.password_entry.setEchoMode(QLineEdit.Password)
        self.password_entry.setClearButtonEnabled(True)

        row1_layout.addWidget(self.server_label)
        row1_layout.addWidget(self.server_entry)
        row1_layout.addWidget(self.username_label)
        row1_layout.addWidget(self.username_entry)
        row1_layout.addWidget(self.password_label)
        row1_layout.addWidget(self.password_entry)

        buttons_layout = QHBoxLayout()
        # buttons_layout.setSpacing(15)

        self.login_button = QPushButton("Login")
        self.login_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogApplyButton))
        self.login_button.clicked.connect(self.login)

        self.m3u_plus_button = QPushButton("M3u_plus")
        search_icon = QIcon.fromTheme("edit-find")
        if search_icon.isNull():
            search_icon = self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogContentsView)
        self.m3u_plus_button.setIcon(search_icon)
        self.m3u_plus_button.clicked.connect(self.open_m3u_plus_dialog)

        self.address_book_button = QPushButton("Address Book")
        self.address_book_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon))
        self.address_book_button.setToolTip("Manage Saved Credentials")
        self.address_book_button.clicked.connect(self.open_address_book)

        self.choose_player_button = QPushButton("Choose Media Player")
        self.choose_player_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaPlay))
        self.choose_player_button.clicked.connect(self.choose_external_player)

        buttons_layout.addWidget(self.login_button)
        buttons_layout.addWidget(self.m3u_plus_button)
        buttons_layout.addWidget(self.address_book_button)
        buttons_layout.addWidget(self.choose_player_button)

        checkbox_layout = QVBoxLayout()
        # checkbox_layout.setAlignment(Qt.AlignRight)
        # checkbox_layout.setSpacing(15)

        self.http_method_checkbox = QCheckBox("Use POST Method")
        self.http_method_checkbox.setToolTip("Check to use POST instead of GET for server requests")

        self.keep_on_top_checkbox = QCheckBox("Keep on top")
        self.keep_on_top_checkbox.setToolTip("Keep the application on top of all windows")
        self.keep_on_top_checkbox.stateChanged.connect(self.toggle_keep_on_top)

        self.epg_checkbox = QCheckBox("Download EPG")
        self.epg_checkbox.setToolTip("Check to download EPG data for channels")
        self.epg_checkbox.stateChanged.connect(self.on_epg_checkbox_toggled)

        self.font_size_label = QLabel("Font Size:")
        self.font_size_spinbox = QSpinBox()
        self.font_size_spinbox.setRange(8, 24)
        self.font_size_spinbox.setValue(10)
        self.font_size_spinbox.setToolTip("Set the font size for playlist items")
        self.font_size_spinbox.valueChanged.connect(self.update_font_size)
        self.font_size_spinbox.setFixedWidth(60)

        checkbox_layout.addWidget(self.http_method_checkbox)
        checkbox_layout.addWidget(self.keep_on_top_checkbox)
        checkbox_layout.addWidget(self.epg_checkbox)

        fontbox_layout = QHBoxLayout()
        fontbox_layout.setAlignment(Qt.AlignLeft)
        fontbox_layout.addWidget(self.font_size_label)
        fontbox_layout.addWidget(self.font_size_spinbox)
        checkbox_layout.addLayout(fontbox_layout)

        self.settings_layout.addLayout(row1_layout)
        self.settings_layout.addLayout(buttons_layout)
        self.settings_layout.addLayout(checkbox_layout)

        #Set widget events
        # self.tab_widget.currentChanged.connect(self.on_tab_change)

        # self.channel_list_live.itemDoubleClicked.connect(self.channel_item_double_clicked)
        # self.channel_list_movies.itemDoubleClicked.connect(self.channel_item_double_clicked)
        # self.channel_list_series.itemDoubleClicked.connect(self.channel_item_double_clicked)
        self.channel_list_live.itemDoubleClicked.connect(self.streaming_item_double_clicked)
        self.channel_list_movies.itemDoubleClicked.connect(self.streaming_item_double_clicked)
        self.channel_list_series.itemDoubleClicked.connect(self.streaming_item_double_clicked)

        # self.category_list_live.itemClicked.connect(self.channel_item_clicked)
        # self.category_list_movies.itemClicked.connect(self.channel_item_clicked)
        # self.category_list_series.itemClicked.connect(self.channel_item_clicked)
        self.category_list_live.itemClicked.connect(self.category_item_clicked)
        self.category_list_movies.itemClicked.connect(self.category_item_clicked)
        self.category_list_series.itemClicked.connect(self.category_item_clicked)

        #Create progress bar
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setFixedHeight(25)
        self.progress_bar.setTextVisible(True)

        #Add everything to the main_layout
        main_layout.addWidget(content_widget)
        main_layout.addWidget(self.progress_bar)

        #Animate progress bar
        self.playlist_progress_animation = QPropertyAnimation(self.progress_bar, b"value")
        self.playlist_progress_animation.setDuration(1000)  # longer duration for smoother animation
        self.playlist_progress_animation.setEasingCurve(QEasingCurve.InOutQuad)

    def load_data_startup(self):
        # Load playlist on startup if enabled
        config = configparser.ConfigParser()
        config.read('credentials.ini')

        if 'Startup credentials' in config:
            selected_startup_credentials = config['Startup credentials']['startup_credentials']

            if 'Credentials' in config and selected_startup_credentials in config['Credentials']:
                data = config['Credentials'][selected_startup_credentials]

                if data.startswith('manual|'):
                    _, server, username, password = data.split('|')
                    self.server_entry.setText(server)
                    self.username_entry.setText(username)
                    self.password_entry.setText(password)
                    self.login()

                elif data.startswith('m3u_plus|'):
                    _, m3u_url = data.split('|', 1)
                    self.extract_credentials_from_m3u_plus_url(m3u_url)
                    self.login()

    def add_search_icon(self, search_bar):
        search_icon = QIcon.fromTheme("edit-find")
        if search_icon.isNull():
            search_icon = self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogContentsView)
        search_bar.addAction(search_icon, QLineEdit.LeadingPosition)

    def toggle_keep_on_top(self, state):
        if state == Qt.Checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()

    def get_http_method(self):
        return 'POST' if self.http_method_checkbox.isChecked() else 'GET'

    def make_request(self, method, url, params=None, timeout=10):
        headers = {'User-Agent': CUSTOM_USER_AGENT}
        if method == 'POST':
            return requests.post(url, data=params, headers=headers, timeout=timeout)
        else:
            return requests.get(url, params=params, headers=headers, timeout=timeout)

    def open_m3u_plus_dialog(self):
        text, ok = QtWidgets.QInputDialog.getText(self, 'M3u_plus Login', 'Enter m3u_plus URL:')
        if ok and text:
            m3u_plus_url = text.strip()
            self.extract_credentials_from_m3u_plus_url(m3u_plus_url)
            self.login()

    def update_font_size(self, value):
        self.default_font_size = value
        for tab_name, list_widget in self.list_widgets.items():
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                font = item.font()
                font.setPointSize(value)
                item.setFont(font)

        font = QFont()
        font.setPointSize(value)
        self.result_display.setFont(font)

    def extract_credentials_from_m3u_plus_url(self, url):
        try:
            pattern = r'(http[s]?://[^/]+)/get\.php\?username=([^&]*)&password=([^&]*)&type=(m3u_plus|m3u|&output=m3u8)'
            match = re.match(pattern, url)
            if match:
                self.server = match.group(1)
                self.username = match.group(2)
                self.password = match.group(3)
                self.server_entry.setText(self.server)
                self.username_entry.setText(self.username)
                self.password_entry.setText(self.password)
            else:
                self.animate_progress(0, 100, "Invalid m3u_plus or m3u URL")
        except Exception as e:
            print(f"Error extracting credentials: {e}")
            self.animate_progress(0, 100, "Error extracting credentials")

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

    def reset_progress_bar(self):
        self.playlist_progress_animation.stop()
        self.progress_bar.setValue(0)
        self.set_progress_text("")

    def login(self):
        # When logging into another server, reset the progress bar
        self.reset_progress_bar()
        self.epg_data = {}
        self.channel_id_to_names = {}
        self.epg_last_updated = None
        for tab_name, list_widget in self.list_widgets.items():
            list_widget.clear()

        for tab_name, list_widget in self.category_list_widgets.items():
            list_widget.clear()

        cache_file = 'epg_cache1.xml'
        if os.path.exists(cache_file):
            try:
                os.remove(cache_file)
            except Exception as e:
                print(f"Error deleting EPG cache: {e}")
                # self.animate_progress(0, 100, "Error deleting EPG cache")
                self.set_progress_bar(100, "Error deleting EPG cache")
                return

        self.server = self.server_entry.text().strip()
        self.username = self.username_entry.text().strip()
        self.password = self.password_entry.text().strip()

        if not self.server or not self.username or not self.password:
            dlg = QMessageBox(self)
            dlg.setWindowTitle("Error!")
            dlg.setText("Please fill in all fields to login!")
            btn = dlg.exec()

            if btn == QMessageBox.Ok:
                print("OK!")

            return

        # if not server or not username or not password:
        #     # self.animate_progress(0, 100, "Please fill all fields")
        #     self.set_progress_bar(100, "Please fill all fields")
        #     return

        # # Start loading playlist from 0 to 100
        # # self.reset_progress_bar()
        # # self.animate_progress(0, 30, "Loading playlist...")
        # self.set_progress_bar(50, "Loading playlist...")
        # self.fetch_categories_only(server, username, password)

        # #Remove this
        # self.fetch_all_data(self.server, self.username, self.password)
        self.fetch_data_thread(self.server, self.username, self.password)

    def fetch_data_thread(self, server, username, password):
        http_method = self.get_http_method()
        dataWorker = FetchDataWorker(self.server, self.username, self.password, http_method)
        dataWorker.signals.finished.connect(self.process_data)
        dataWorker.signals.error.connect(self.on_fetch_data_error)
        dataWorker.signals.progress_bar.connect(self.animate_progress)
        self.threadpool.start(dataWorker)

    def process_data(self, iptv_info, categories, entries_per_stream_type):
        self.categories_per_stream_type = categories
        self.entries_per_stream_type = entries_per_stream_type
        # print(self.entries_per_stream_type['LIVE'])

        #Process IPTV info
        user_info   = iptv_info.get("user_info", {})
        server_info = iptv_info.get("server_info", {})

        hostname    = server_info.get("url", "Unknown")
        port        = server_info.get("port", "Unknown")
        if hostname == "Unknown" or port == "Unknown":
            host = "Unknown"
        else:
            host = f"http://{hostname}:{port}"

        username            = user_info.get("username", "Unknown")
        password            = user_info.get("password", "Unknown")
        max_connections     = user_info.get("max_connections", "Unknown")
        active_connections  = user_info.get("active_cons", "Unknown")
        status              = user_info.get("status", "Unknown")
        expire_timestamp    = user_info.get("exp_date", "Unknown")
        expiry = (
            datetime.fromtimestamp(int(expire_timestamp)).strftime("%B %d, %Y")
            if expire_timestamp else "Unknown"
        )

        if user_info.get("is_trial") == "1":
            trial = "Yes"
        else:
            trial = "No"

        created_at_timestamp = user_info.get("created_at", "Unknown")
        created_at = (
            datetime.fromtimestamp(int(created_at_timestamp)).strftime("%B %d, %Y")
            if created_at_timestamp and created_at_timestamp.isdigit() else "Unknown"
        )

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

        self.result_display.setText(formatted_data)
        QtWidgets.qApp.processEvents()

        #Process categories and entries
        for stream_type in self.entries_per_stream_type.keys():
            self.list_widgets[stream_type].clear()
            self.category_list_widgets[stream_type].clear()
            self.category_list_widgets[stream_type].addItem(self.all_categories_text)

            # self.currently_loaded_entries[stream_type] = self.entries_per_stream_type[stream_type]
            for entry in self.entries_per_stream_type[stream_type]:
                self.currently_loaded_entries[stream_type].append(entry)

            #Add categories in category list
            num_of_categories = len(self.categories_per_stream_type[stream_type])
            prev_perc = 0
            for idx, category_item in enumerate(self.categories_per_stream_type[stream_type]):
                item = QListWidgetItem(category_item['category_name'])
                item.setData(Qt.UserRole, category_item)
                # item.setIcon(channel_icon)

                self.category_list_widgets[stream_type].addItem(item)

                perc = (idx * 100) / num_of_categories
                if (perc - prev_perc) > 10:
                    prev_perc = perc
                    self.set_progress_bar(int(perc), f"Loading {stream_type} categories: {idx} of {num_of_categories}")
                    QtWidgets.qApp.processEvents()

            #Add streams in streaming list
            num_of_entries = len(self.entries_per_stream_type[stream_type])
            prev_perc = 0
            for idx, entry in enumerate(self.entries_per_stream_type[stream_type]):
                item = QListWidgetItem(entry['name'])
                item.setData(Qt.UserRole, entry)
                # item.setIcon(channel_icon)

                self.list_widgets[stream_type].addItem(item)

                perc = (idx * 100) / num_of_entries
                if (perc - prev_perc) > 10:
                    prev_perc = perc
                    self.set_progress_bar(int(perc), f"Loading {stream_type} streams: {idx} of {num_of_entries}")
                    QtWidgets.qApp.processEvents()


        self.set_progress_bar(100, f"Finished loading")
        QtWidgets.qApp.processEvents()

    def on_fetch_data_error(self, error_msg):
        print(f"Error occurred while fetching data: {error_msg}")

    # def fetch_all_data(self, server, username, password):
        # try:
        #     self.login_type = 'xtream'
        #     self.navigation_stacks = {'LIVE': [], 'Movies': [], 'Series': []}
        #     self.top_level_scroll_positions = {'LIVE': 0, 'Movies': 0, 'Series': 0}


        #     http_method = self.get_http_method()

        #     params = {
        #         'username': username,
        #         'password': password,
        #         'action': ''
        #     }

        #     host_url = f"{server}/player_api.php"

        #     print("Going to receive data")

        #     #Get IPTV info
        #     self.set_progress_bar(5, "Loading IPTV info")
        #     iptv_info = self.make_request(http_method, host_url, params, timeout=10)
        #     iptv_info.raise_for_status()

        #     #Get all category data
        #     self.set_progress_bar(10, "Loading LIVE Categories")
        #     params['action'] = 'get_live_categories'
        #     live_category_resp = self.make_request(http_method, host_url, params, timeout=10)
        #     live_category_resp.raise_for_status()

        #     self.set_progress_bar(20, "Loading VOD Categories")
        #     params['action'] = 'get_vod_categories'
        #     movies_category_resp = self.make_request(http_method, host_url, params, timeout=10)
        #     movies_category_resp.raise_for_status()

        #     self.set_progress_bar(30, "Loading Series Categories")
        #     params['action'] = 'get_series_categories'
        #     series_category_resp = self.make_request(http_method, host_url, params, timeout=10)
        #     series_category_resp.raise_for_status()

        #     self.categories_per_stream_type = {
        #         "LIVE": live_category_resp.json(),
        #         "Movies": movies_category_resp.json(),
        #         "Series": series_category_resp.json(),
        #     }

        #     #Get all streaming data
        #     self.set_progress_bar(40, "Loading LIVE TV Streaming data")
        #     params['action'] = 'get_live_streams'
        #     live_streams_resp = self.make_request(http_method, host_url, params, timeout=10)
        #     live_streams_resp.raise_for_status()

        #     self.set_progress_bar(60, "Loading VOD Streaming data")
        #     params['action'] = 'get_vod_streams'
        #     movies_streams_resp = self.make_request(http_method, host_url, params, timeout=10)
        #     movies_streams_resp.raise_for_status()

        #     self.set_progress_bar(80, "Loading Series Streaming data")
        #     params['action'] = 'get_series'
        #     series_streams_resp = self.make_request(http_method, host_url, params, timeout=10)
        #     series_streams_resp.raise_for_status()

        #     self.entries_per_stream_type['LIVE']    = live_streams_resp.json()
        #     self.entries_per_stream_type['Movies']  = movies_streams_resp.json()
        #     self.entries_per_stream_type['Series']  = series_streams_resp.json()

        #     #TODO Fetch EPG data

        #     self.set_progress_bar(100, "Finished loading data")

        #     #Make streaming URL in each entry except for the series
        #     for tab_name in self.entries_per_stream_type.keys():
        #         for idx, entry in enumerate(self.entries_per_stream_type[tab_name]):
        #             stream_type         = entry.get('stream_type')
        #             stream_id           = entry.get("stream_id")
        #             container_extension = entry.get("container_extension", "m3u8")
        #             if stream_id:
        #                 self.entries_per_stream_type[tab_name][idx]["url"] = f"{self.server}/{stream_type}/{self.username}/{self.password}/{stream_id}.{container_extension}"

        #     list_widget = self.get_list_widget('LIVE')
        #     list_widget.clear()

        #     for entry in self.entries_per_stream_type['LIVE']:
        #         if entry['category_id'] == '1525':
        #             item = QListWidgetItem(entry['name'])
        #             item.setData(Qt.UserRole, entry)
        #             # item.setIcon(channel_icon)

        #             list_widget.addItem(item)

        #     print("Finished processing data")

        # except Exception as e:
        #     print(f"Failed: {e}")

    def fetch_vod_info(self, vod_id):
        return

    def fetch_series_info(self, series_id):
        return

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

            selected_item_text = selected_item.text()
            selected_item_data = selected_item.data(Qt.UserRole)

            if selected_item_text != self.all_categories_text:
                category_id = selected_item_data['category_id']

            self.set_progress_bar(0, "Loading items")

            self.series_navigation_level = 0
            self.list_widgets[stream_type].clear()
            self.currently_loaded_entries[stream_type].clear()

            for entry in self.entries_per_stream_type[stream_type]:
                # print(entry)
                if selected_item_text == self.all_categories_text:
                    item = QListWidgetItem(entry['name'])
                    item.setData(Qt.UserRole, entry)

                    self.currently_loaded_entries[stream_type].append(entry)
                    self.list_widgets[stream_type].addItem(item)

                elif entry['category_id'] == category_id:
                    item = QListWidgetItem(entry['name'])
                    item.setData(Qt.UserRole, entry)

                    self.currently_loaded_entries[stream_type].append(entry)
                    self.list_widgets[stream_type].addItem(item)

            self.animate_progress(0, 100, "Loading finished")

        except Exception as e:
            print(f"Failed: {e}")

    def streaming_item_double_clicked(self, double_clicked_item):
        try:
            sender = self.sender()

            print(double_clicked_item.text())

            selected_item = sender.currentItem()
            if not selected_item:
                return

            selected_item_text = selected_item.text()
            selected_item_data = selected_item.data(Qt.UserRole)
            print(f"name = {selected_item_text}")

            match self.series_navigation_level:
                case 0: #Highest level, either LIVE, VOD or series
                    if double_clicked_item.text() == self.go_back_text:
                        return

                    stream_type = selected_item_data['stream_type']
                    print(f"level 0: {stream_type}")

                    if stream_type == 'live' or stream_type == 'movie':
                        self.play_item(selected_item_data['url'])

                    elif stream_type == 'series':
                        self.series_navigation_level = 1
                        self.show_seasons(selected_item_data)

                case 1: #Series seasons
                    print("level 1")
                    if selected_item_text == self.go_back_text:
                        self.series_navigation_level = 0
                        self.go_back_to_level(self.series_navigation_level)
                        
                    else:
                        self.series_navigation_level = 2
                        self.show_episodes(selected_item_data)

                case 2: #Series episodes
                    print("level 2")
                    if selected_item_text == self.go_back_text:
                        self.series_navigation_level = 1
                        self.go_back_to_level(self.series_navigation_level)
                        
                    else:
                        #Play episode
                        self.play_item(selected_item_data['url'])

        except Exception as e:
            print(f"failed: {e}")

    def go_back_to_level(self, series_navigation_level):
        self.set_progress_bar(0, "Loading items")

        if series_navigation_level == 0:    #From seasons back to series list
            self.list_widgets['Series'].clear()
            # QtWidgets.qApp.processEvents()

            for entry in self.currently_loaded_entries['Series']:
                item = QListWidgetItem(entry['name'])
                item.setData(Qt.UserRole, entry)

                self.list_widgets['Series'].addItem(item)

        elif series_navigation_level == 1:  #From episodes back to seasons list
            self.list_widgets['Series'].clear()
            # QtWidgets.qApp.processEvents()

            self.list_widgets['Series'].addItem(self.go_back_text)

            for season in self.currently_loaded_entries['Seasons'].keys():
                item = QListWidgetItem(f"Season {season}")
                item.setData(Qt.UserRole, self.currently_loaded_entries['Seasons'][season])

                self.list_widgets['Series'].addItem(item)

        self.animate_progress(0, 100, "Loading finished")

    def show_seasons(self, seasons_data):
        self.set_progress_bar(0, "Loading items")

        #Fetch series info
        headers = {'User-Agent': CUSTOM_USER_AGENT}
        host_url = f"{self.server}/player_api.php"
        params = {
            'username': self.username,
            'password': self.password,
            'action': 'get_series_info',
            'series_id': seasons_data['series_id']
        }

        series_info_resp = requests.get(host_url, params=params, headers=headers, timeout=10)
        series_info_resp.raise_for_status()

        self.series_info_data = series_info_resp.json()

        #Show seasons in list
        self.list_widgets['Series'].clear()
        # QtWidgets.qApp.processEvents()

        self.list_widgets['Series'].addItem(self.go_back_text)

        self.currently_loaded_entries['Seasons'] = self.series_info_data['episodes']

        for season in self.series_info_data['episodes'].keys():
            item = QListWidgetItem(f"Season {season}")
            item.setData(Qt.UserRole, self.series_info_data['episodes'][season])
            # item.setIcon(channel_icon)

            # self.currently_loaded_entries['Seasons'].append(self.series_info_data['episodes'][season])
            self.list_widgets['Series'].addItem(item)

        self.animate_progress(0, 100, "Loading finished")

    def show_episodes(self, episodes_data):
        self.set_progress_bar(0, "Loading items")

        #Clear lists
        self.list_widgets['Series'].clear()
        # QtWidgets.qApp.processEvents()

        self.list_widgets['Series'].addItem(self.go_back_text)

        self.currently_loaded_entries['Episodes'].clear()

        #Show episodes in list
        for episode in episodes_data:
            item = QListWidgetItem(f"{episode['title']}")

            container_extension = episode['container_extension']
            episode_id          = episode['id']
            playable_url = f"{self.server}/series/{self.username}/{self.password}/{episode_id}.{container_extension}"

            episode['url'] = playable_url

            item.setData(Qt.UserRole, episode)

            self.currently_loaded_entries['Episodes'].append(episode)
            self.list_widgets['Series'].addItem(item)

        self.animate_progress(0, 100, "Loading finished")

    def play_item(self, url):
        if self.external_player_command:
            try:
                print(f"Going to play: {url}")
                self.animate_progress(0, 100, "Loading player for streaming")
                subprocess.Popen([self.external_player_command, url])
            except:
                self.animate_progress(0, 100, "Failed playing stream")
        else:
            self.animate_progress(0, 100, "No external player configured")


    def fetch_categories_only(self, server, username, password):
        try:
            http_method = self.get_http_method()

            params = {
                'username': username,
                'password': password,
                'action': 'get_live_categories'
            }

            categories_url = f"{server}/player_api.php"
            live_response = self.make_request(http_method, categories_url, params, timeout=10)
            live_response.raise_for_status()

            params['action'] = 'get_vod_categories'
            movies_response = self.make_request(http_method, categories_url, params, timeout=10)
            movies_response.raise_for_status()

            params['action'] = 'get_series_categories'
            series_response = self.make_request(http_method, categories_url, params, timeout=10)
            series_response.raise_for_status()

            # print(live_response.json())

            self.categories_per_stream_type = {
                "LIVE": live_response.json(),
                "Movies": movies_response.json(),
                "Series": series_response.json(),
            }
                
            self.server = server
            self.username = username
            self.password = password
            self.login_type = 'xtream'
            self.navigation_stacks = {'LIVE': [], 'Movies': [], 'Series': []}
            self.top_level_scroll_positions = {'LIVE': 0, 'Movies': 0, 'Series': 0}
            self.update_category_lists('LIVE')
            self.update_category_lists('Movies')
            self.update_category_lists('Series')
            self.fetch_additional_data(server, username, password)

            # Playlist loading complete
            # self.animate_progress(self.progress_bar.value(), 100, "Playlist loaded")
            self.set_progress_bar(100, "Playlist Loaded")

            # After playlist is fully loaded, if EPG is checked and not loaded, load EPG now
            if self.epg_checkbox.isChecked() and not self.epg_data:
                # Reset to 0 before loading EPG
                self.reset_progress_bar()
                # self.animate_progress(0, 50, "Loading EPG data...")
                self.set_progress_bar(50, "Loading EPG data...")
                self.load_epg_data_async()

        except requests.exceptions.Timeout:
            print("Request timed out")
            self.animate_progress(self.progress_bar.value(), 100, "Login timed out")
        except requests.RequestException as e:
            print(f"Network error: {e}")
            self.animate_progress(self.progress_bar.value(), 100, "Network Error")
        except ValueError as e:
            print(f"JSON decode error: {e}")
            self.animate_progress(self.progress_bar.value(), 100, "Invalid server response")
        except Exception as e:
            print(f"Error fetching categories: {e}")
            # self.animate_progress(self.progress_bar.value(), 100, "Error fetching categories")

    def fetch_additional_data(self, server, username, password):
        try:
            if not server.startswith("http://") and not server.startswith("https://"):
                server = f"http://{server}"

            headers = {'User-Agent': CUSTOM_USER_AGENT}
            payload = {'username': username, 'password': password}
            url = f"{server}/player_api.php"

            response = requests.post(url, headers=headers, data=payload, timeout=10)
            response.raise_for_status()

            additional_data = response.json()
            user_info = additional_data.get("user_info", {})
            server_info = additional_data.get("server_info", {})

            hostname = server_info.get("url", server.replace("http://", "").replace("https://", ""))
            port = server_info.get("port", 25461)
            host = f"http://{hostname}:{port}"

            username = user_info.get("username", "Unknown")
            password = user_info.get("password", "Unknown")
            max_connections = user_info.get("max_connections", "Unlimited")
            active_connections = user_info.get("active_cons", "0")
            trial = "Yes" if user_info.get("is_trial") == "1" else "No"
            expire_timestamp = user_info.get("exp_date")
            expiry = (
                datetime.fromtimestamp(int(expire_timestamp)).strftime("%B %d, %Y")
                if expire_timestamp else "Unlimited"
            )
            status = user_info.get("status", "Unknown")

            created_at_timestamp = user_info.get("created_at", "Unknown")
            created_at = (
                datetime.fromtimestamp(int(created_at_timestamp)).strftime("%B %d, %Y")
                if created_at_timestamp and created_at_timestamp.isdigit() else "Unknown"
            )
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

            self.result_display.setText(formatted_data)
            self.info_tab_initialized = True

        except Exception as e:
            print(f"Error fetching additional data: {e}")

    def load_epg_data_async(self):
        if not self.server or not self.username or not self.password:
            # Can't load EPG if not logged in
            return
        http_method = self.get_http_method()
        epg_worker = EPGWorker(self.server, self.username, self.password, http_method)
        epg_worker.signals.finished.connect(self.on_epg_loaded)
        epg_worker.signals.error.connect(self.on_epg_error)
        self.threadpool.start(epg_worker)

    def on_epg_loaded(self, epg_data, channel_id_to_names):
        print("EPG data loaded, processing now...")
        self.epg_data = epg_data
        self.channel_id_to_names = channel_id_to_names

        name_to_id = {}
        for cid, names in channel_id_to_names.items():
            for n in names:
                if n not in name_to_id:
                    name_to_id[n] = cid
        self.epg_name_map = name_to_id

        # EPG done
        # self.animate_progress(self.progress_bar.value(), 100, "EPG data loaded")
        self.set_progress_bar(100, "EPG Data Loaded")

    def on_epg_error(self, error_message):
        print(f"Error fetching EPG data: {error_message}")
        self.animate_progress(self.progress_bar.value(), 100, "Error fetching EPG data")

    # def channel_item_clicked(self, item):
    #     try:
    #         sender = self.sender()
    #         category = {
    #             self.category_list_live: 'LIVE',
    #             self.category_list_movies: 'Movies',
    #             self.category_list_series: 'Series'
    #         }.get(sender)

    #         if not category:
    #             return

    #         selected_item = sender.currentItem()
    #         if not selected_item:
    #             return

    #         selected_text = selected_item.text()

    #         self.handle_xtream_click(selected_item, selected_text, category, sender)

    #     except Exception as e:
    #         print(f"Error occurred while handling click: {e}")

    # def channel_item_double_clicked(self, item):
    #     try:
    #         sender = self.sender()
    #         category = {
    #             self.channel_list_live: 'LIVE',
    #             self.channel_list_movies: 'Movies',
    #             self.channel_list_series: 'Series'
    #         }.get(sender)

    #         if not category:
    #             return

    #         selected_item = sender.currentItem()
    #         if not selected_item:
    #             return

    #         selected_text = selected_item.text()
    #         list_widget = self.get_list_widget(category)
    #         current_scroll_position = list_widget.verticalScrollBar().value()
    #         stack = self.navigation_stacks[category]

    #         if stack:
    #             stack[-1]['scroll_position'] = current_scroll_position
    #         else:
    #             self.top_level_scroll_positions[category] = current_scroll_position

    #         self.handle_xtream_double_click(selected_item, selected_text, category, sender)

    #     except Exception as e:
    #         print(f"Error occurred while handling double click: {e}")

    # def handle_xtream_click(self, selected_item, selected_text, tab_name, sender):
    #     try:
    #         list_widget = self.get_category_list_widget(tab_name)
            
    #         if tab_name != "Series":
    #             if selected_text == "All":
    #                 self.fetch_all_channels(tab_name)
    #             elif selected_text in [group["category_name"] for group in self.categories_per_stream_type[tab_name]]:
    #                 self.fetch_channels(selected_text, tab_name)
    #             else:
    #                 selected_entry = selected_item.data(Qt.UserRole)
    #                 if selected_entry and "url" in selected_entry:
    #                     self.play_channel(selected_entry)
    #             return
    #         elif tab_name == "Series":
    #             if selected_text in [group["category_name"] for group in self.categories_per_stream_type["Series"]]:
    #                 self.fetch_series_in_category(selected_text)
    #                 return

    #     except Exception as e:
    #         print(f"Error loading channels: {e}")

    # def handle_xtream_double_click(self, selected_item, selected_text, tab_name, sender):
    #     try:
    #         list_widget = self.get_list_widget(tab_name)
    #         stack = self.navigation_stacks[tab_name]

    #         if selected_text == self.go_back_text:
    #             if stack:
    #                 stack.pop()
    #                 if stack:
    #                     last_level = stack[-1]
    #                     level = last_level['level']
    #                     data = last_level['data']
    #                     scroll_position = last_level.get('scroll_position', 0)
    #                     if level == 'channels':
    #                         self.entries_per_stream_type[tab_name] = data['entries']
    #                         self.show_channels(list_widget, tab_name)
    #                         list_widget.verticalScrollBar().setValue(scroll_position)
    #                     elif level == 'series_categories':
    #                         self.show_series_in_category(data['series_list'], restore_scroll_position=True, scroll_position=scroll_position)
    #                     elif level == 'series':
    #                         self.show_seasons(data['seasons'], restore_scroll_position=True, scroll_position=scroll_position)
    #                     elif level == 'season':
    #                         self.show_episodes(data['episodes'], restore_scroll_position=True, scroll_position=scroll_position)
    #                 else:
    #                     self.update_category_lists(tab_name)
    #                     list_widget.verticalScrollBar().setValue(self.top_level_scroll_positions.get(tab_name, 0))
    #             else:
    #                 self.update_category_lists(tab_name)
    #                 list_widget.verticalScrollBar().setValue(self.top_level_scroll_positions.get(tab_name, 0))
    #             return

    #         if tab_name != "Series":
    #             if selected_text in [group["category_name"] for group in self.categories_per_stream_type[tab_name]]:
    #                 self.fetch_channels(selected_text, tab_name)
    #             else:
    #                 selected_entry = selected_item.data(Qt.UserRole)
    #                 print(selected_entry)
    #                 if selected_entry and "url" in selected_entry:
    #                     self.play_channel(selected_entry)
    #             return

    #         # Series logic
    #         if tab_name == "Series":
    #             if not stack:
    #                 print("not stack")
    #                 if selected_text in [group["category_name"] for group in self.categories_per_stream_type["Series"]]:
    #                     self.fetch_series_in_category(selected_text)
    #                     return
    #             elif stack[-1]['level'] == 'series_categories':
    #                 print("series category")
    #                 series_entry = selected_item.data(Qt.UserRole)
    #                 if series_entry and "series_id" in series_entry:
    #                     self.fetch_seasons(series_entry)
    #                     return
    #             elif stack[-1]['level'] == 'series':
    #                 print("series")
    #                 season_number = selected_item.data(Qt.UserRole)
    #                 series_entry = stack[-1]['data']['series_entry']
    #                 self.fetch_episodes(series_entry, season_number)
    #                 return
    #             elif stack[-1]['level'] == 'season':
    #                 print("seasons\n\n\n")
    #                 selected_entry = selected_item.data(Qt.UserRole)
    #                 if selected_entry and "url" in selected_entry:
    #                     self.play_channel(selected_entry)
    #                 return

    #     except Exception as e:
    #         print(f"Error loading channels: {e}")

    # def update_category_lists(self, tab_name):
    #     if tab_name == 'LIVE':
    #         self.search_bar_live.clear()
    #     elif tab_name == 'Movies':
    #         self.search_bar_movies.clear()
    #     elif tab_name == 'Series':
    #         self.search_bar_series.clear()

    #     try:
    #         # list_widget = self.get_list_widget(tab_name)
    #         list_widget = self.get_category_list_widget(tab_name)
    #         list_widget.clear()

    #         if self.navigation_stacks[tab_name]:
    #             go_back_item = QListWidgetItem(self.go_back_text)
    #             go_back_item.setIcon(self.go_back_icon)
    #             list_widget.addItem(go_back_item)

    #         if tab_name == 'LIVE':
    #             channel_icon = self.live_channel_icon
    #         elif tab_name == 'Movies':
    #             channel_icon = self.movies_channel_icon
    #         elif tab_name == 'Series':
    #             channel_icon = self.series_channel_icon
    #         else:
    #             channel_icon = self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)

    #         group_list = self.categories_per_stream_type[tab_name]
    #         category_names = sorted(group["category_name"] for group in group_list)
    #         items = []
    #         for category_name in category_names:
    #             item = QListWidgetItem(category_name)
    #             item.setIcon(channel_icon)
    #             items.append(item)

    #         items.sort(key=lambda x: x.text())
    #         for item in items:
    #             list_widget.addItem(item)

    #         item = QListWidgetItem("All")
    #         item.setIcon(channel_icon)
    #         list_widget.insertItem(0, QListWidgetItem(item))

    #         scroll_position = self.top_level_scroll_positions.get(tab_name, 0)
    #         list_widget.verticalScrollBar().setValue(scroll_position)
    #     except Exception as e:
    #         print(f"Error updating category lists: {e}")
    #         self.animate_progress(self.progress_bar.value(), 100, "Error updating lists")

    # def fetch_channels(self, category_name, tab_name):
    #     try:
    #         category_id = next(g["category_id"] for g in self.categories_per_stream_type[tab_name] if g["category_name"] == category_name)

    #         list_widget = self.get_list_widget(tab_name)
    #         current_scroll_position = list_widget.verticalScrollBar().value()
    #         stack = self.navigation_stacks[tab_name]
    #         if stack:
    #             stack[-1]['scroll_position'] = current_scroll_position
    #         else:
    #             self.top_level_scroll_positions[tab_name] = current_scroll_position

    #         http_method = self.get_http_method()
    #         params = {
    #             'username': self.username,
    #             'password': self.password,
    #             'action': '',
    #             'category_id': category_id
    #         }

    #         if tab_name == "LIVE":
    #             params['action'] = 'get_live_streams'
    #             stream_type = "live"
    #         elif tab_name == "Movies":
    #             params['action'] = 'get_vod_streams'
    #             stream_type = "movie"

    #         streams_url = f"{self.server}/player_api.php"
    #         response = self.make_request(http_method, streams_url, params)
    #         response.raise_for_status()

    #         data = response.json()
    #         if not isinstance(data, list):
    #             raise ValueError("Expected a list of channels")

    #         self.entries_per_stream_type[tab_name] = data
    #         entries = self.entries_per_stream_type[tab_name]
    #         # print(entries)

    #         for entry in entries:
    #             stream_id = entry.get("stream_id")
    #             epg_channel_id = entry.get("epg_channel_id")
    #             if epg_channel_id:
    #                 epg_channel_id = epg_channel_id.strip().lower()
    #             else:
    #                 epg_channel_id = None

    #             container_extension = entry.get("container_extension", "m3u8")
    #             if stream_id:
    #                 entry["url"] = f"{self.server}/{stream_type}/{self.username}/{self.password}/{stream_id}.{container_extension}"
    #             else:
    #                 entry["url"] = None
    #             entry["epg_channel_id"] = epg_channel_id

    #         self.navigation_stacks[tab_name].append({'level': 'channels', 'data': {'tab_name': tab_name, 'entries': entries}, 'scroll_position': 0})
    #         self.show_channels(list_widget, tab_name)

    #     except requests.RequestException as e:
    #         print(f"Network error: {e}")
    #         self.animate_progress(self.progress_bar.value(), 100, "Network Error")
    #     except ValueError as e:
    #         print(f"Data validation error: {e}")
    #         self.animate_progress(self.progress_bar.value(), 100, "Invalid channel data received")
    #     except Exception as e:
    #         print(f"Error fetching channels: {e}")
    #         self.animate_progress(self.progress_bar.value(), 100, "Error fetching channels")

    # def show_channels(self, list_widget, tab_name):
    #     try:
    #         list_widget.clear()

    #         # if self.navigation_stacks[tab_name]:
    #         #     go_back_item = QListWidgetItem(self.go_back_text)
    #         #     go_back_item.setIcon(self.go_back_icon)
    #         #     list_widget.addItem(go_back_item)

    #         if tab_name == 'LIVE':
    #             channel_icon = self.live_channel_icon
    #         elif tab_name == 'Movies':
    #             channel_icon = self.movies_channel_icon
    #         elif tab_name == 'Series':
    #             channel_icon = self.series_channel_icon
    #         else:
    #             channel_icon = self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)

    #         items = []
    #         now = datetime.now(tz=tz.tzlocal()) if self.epg_data else None

    #         for idx, entry in enumerate(self.entries_per_stream_type[tab_name]):
    #             display_text = entry.get("name", "Unnamed Channel")
    #             tooltip_text = ""

    #             # try:
    #             #     icon_url = entry.get('stream_icon')

    #             #     headers = {'User-Agent': CUSTOM_USER_AGENT}

    #             #     image = QImage()
    #             #     image.loadFromData(requests.get(icon_url, headers=headers).content)

    #             #     channel_icon = QIcon(QPixmap(image))

    #             # except Exception as e:
    #             #     print(f"failed to do icon: {e}")


    #             if tab_name == "LIVE" and self.epg_data:
    #                 epg_channel_id = entry.get('epg_channel_id')
    #                 if epg_channel_id and epg_channel_id in self.epg_data:
    #                     epg_info_list = self.epg_data[epg_channel_id]
    #                 else:
    #                     channel_name = normalize_channel_name(entry.get('name', ''))
    #                     epg_channel_id = self.epg_name_map.get(channel_name, None)
    #                     epg_info_list = self.epg_data.get(epg_channel_id, [])

    #                 if epg_info_list:
    #                     current_epg = None
    #                     for epg in epg_info_list:
    #                         start_time = parser.parse(epg['start_time'])
    #                         stop_time = parser.parse(epg['stop_time'])
    #                         if start_time <= now <= stop_time:
    #                             current_epg = epg
    #                             break
    #                         elif start_time > now:
    #                             current_epg = epg
    #                             break

    #                     if current_epg:
    #                         start_time = parser.parse(current_epg['start_time']).astimezone(tz.tzlocal())
    #                         stop_time = parser.parse(current_epg['stop_time']).astimezone(tz.tzlocal())
    #                         start_time_formatted = start_time.strftime("%I:%M %p")
    #                         stop_time_formatted = stop_time.strftime("%I:%M %p")
    #                         title = current_epg['title']
    #                         display_text += f" - {title} ({start_time_formatted} - {stop_time_formatted})"
    #                         tooltip_text = current_epg['description']
    #                     else:
    #                         display_text += " - No Current EPG Data Available"
    #                         tooltip_text = "No current EPG information found."
    #                 else:
    #                     display_text += " - No EPG Data"
    #                     tooltip_text = "No EPG information found."

    #             item = QListWidgetItem(display_text)
    #             item.setData(Qt.UserRole, entry)
    #             item.setIcon(channel_icon)

    #             if tooltip_text:
    #                 description_html = html.escape(tooltip_text)
    #                 tooltip_text_formatted = f"""
    #                 <div style="max-width: 300px; white-space: normal;">
    #                     {description_html}
    #                 </div>
    #                 """
    #                 item.setToolTip(tooltip_text_formatted)

    #             items.append(item)

    #         items.sort(key=lambda x: x.text())
    #         for item in items:
    #             list_widget.addItem(item)

    #         list_widget.verticalScrollBar().setValue(0)
    #     except Exception as e:
    #         print(f"Error displaying channels: {e}")

    # def fetch_series_in_category(self, category_name):
    #     try:
    #         list_widget = self.get_list_widget('Series')
    #         current_scroll_position = list_widget.verticalScrollBar().value()
    #         stack = self.navigation_stacks['Series']
    #         if stack:
    #             stack[-1]['scroll_position'] = current_scroll_position
    #         else:
    #             self.top_level_scroll_positions['Series'] = current_scroll_position

    #         category_id = next(g["category_id"] for g in self.categories_per_stream_type["Series"] if g["category_name"] == category_name)

    #         http_method = self.get_http_method()
    #         params = {
    #             'username': self.username,
    #             'password': self.password,
    #             'action': 'get_series',
    #             'category_id': category_id
    #         }

    #         streams_url = f"{self.server}/player_api.php"
    #         response = self.make_request(http_method, streams_url, params)
    #         response.raise_for_status()

    #         series_list = response.json()

    #         self.navigation_stacks['Series'].append({'level': 'series_categories', 'data': {'series_list': series_list}, 'scroll_position': 0})
    #         self.show_series_in_category(series_list)

    #     except Exception as e:
    #         print(f"Error fetching series: {e}")

    # def show_series_in_category(self, series_list, restore_scroll_position=False, scroll_position=0):
    #     try:
    #         list_widget = self.channel_list_series

    #         list_widget.clear()

    #         items = []
    #         for entry in series_list:
    #             item = QListWidgetItem(entry["name"])
    #             item.setData(Qt.UserRole, entry)
    #             item.setIcon(self.series_channel_icon)
    #             items.append(item)

    #         items.sort(key=lambda x: x.text())
    #         for item in items:
    #             list_widget.addItem(item)

    #         if restore_scroll_position:
    #             QTimer.singleShot(0, lambda: list_widget.verticalScrollBar().setValue(scroll_position))
    #         else:
    #             list_widget.verticalScrollBar().setValue(0)

    #         self.current_series_list = series_list
    #     except Exception as e:
    #         print(f"Error displaying series: {e}")

    # def fetch_seasons(self, series_entry):
    #     try:
    #         list_widget = self.get_list_widget('Series')
    #         current_scroll_position = list_widget.verticalScrollBar().value()
    #         stack = self.navigation_stacks['Series']
    #         if stack:
    #             stack[-1]['scroll_position'] = current_scroll_position

    #         http_method = self.get_http_method()
    #         params = {
    #             'username': self.username,
    #             'password': self.password,
    #             'action': 'get_series_info',
    #             'series_id': series_entry["series_id"]
    #         }

    #         episodes_url = f"{self.server}/player_api.php"
    #         response = self.make_request(http_method, episodes_url, params)
    #         response.raise_for_status()

    #         series_info = response.json()
    #         self.series_info = series_info

    #         seasons = list(series_info.get("episodes", {}).keys())
    #         self.navigation_stacks['Series'].append({'level': 'series', 'data': {'series_entry': series_entry, 'seasons': seasons}, 'scroll_position': 0})
    #         self.show_seasons(seasons)

    #     except Exception as e:
    #         print(f"Error fetching seasons: {e}")

    # def show_seasons(self, seasons, restore_scroll_position=False, scroll_position=0):
    #     try:
    #         list_widget = self.channel_list_series
    #         list_widget.clear()
    #         if self.navigation_stacks['Series']:
    #             go_back_item = QListWidgetItem(self.go_back_text)
    #             go_back_item.setIcon(self.go_back_icon)
    #             list_widget.addItem(go_back_item)

    #         seasons_int = sorted([int(season) for season in seasons])
    #         items = []
    #         for season in seasons_int:
    #             item = QListWidgetItem(f"Season {season}")
    #             item.setData(Qt.UserRole, str(season))
    #             item.setIcon(self.series_channel_icon)
    #             items.append(item)

    #         for item in items:
    #             list_widget.addItem(item)

    #         if restore_scroll_position:
    #             QTimer.singleShot(0, lambda: list_widget.verticalScrollBar().setValue(scroll_position))
    #         else:
    #             list_widget.verticalScrollBar().setValue(0)

    #         self.current_seasons = [str(season) for season in seasons_int]
    #     except Exception as e:
    #         print(f"Error displaying seasons: {e}")

    # def fetch_episodes(self, series_entry, season_number):
    #     try:
    #         list_widget = self.get_list_widget('Series')
    #         current_scroll_position = list_widget.verticalScrollBar().value()
    #         stack = self.navigation_stacks['Series']
    #         if stack:
    #             stack[-1]['scroll_position'] = current_scroll_position

    #         episodes = self.series_info.get("episodes", {}).get(str(season_number), [])
    #         self.navigation_stacks['Series'].append({'level': 'season', 'data': {'season_number': season_number, 'episodes': episodes}, 'scroll_position': 0})
    #         self.show_episodes(episodes)

    #     except Exception as e:
    #         print(f"Error fetching episodes: {e}")

    # def show_episodes(self, episodes, restore_scroll_position=False, scroll_position=0):
    #     try:
    #         list_widget = self.channel_list_series
    #         list_widget.clear()
    #         if self.navigation_stacks['Series']:
    #             go_back_item = QListWidgetItem(self.go_back_text)
    #             go_back_item.setIcon(self.go_back_icon)
    #             list_widget.addItem(go_back_item)

    #         episodes_sorted = sorted(episodes, key=lambda x: int(x.get('episode_num', 0)))
    #         stack = self.navigation_stacks['Series']
    #         if stack and len(stack) >= 2 and 'series_entry' in stack[-2]['data']:
    #             series_title = stack[-2]['data']['series_entry'].get('name', '').strip()
    #         else:
    #             series_title = "Unknown Series"

    #         items = []
    #         for episode in episodes_sorted:
    #             raw_episode_title = str(episode.get('title', 'Untitled Episode')).strip()
    #             season = str(episode.get('season', '1'))
    #             episode_num = str(episode.get('episode_num', '1'))

    #             try:
    #                 season_int = int(season)
    #                 episode_num_int = int(episode_num)
    #                 episode_code = f"S{season_int:02d}E{episode_num_int:02d}"
    #             except ValueError:
    #                 episode_code = f"S{season}E{episode_num}"

    #             if series_title.lower() in raw_episode_title.lower():
    #                 episode_title = re.sub(re.escape(series_title), '', raw_episode_title, flags=re.IGNORECASE).strip(" -")
    #             else:
    #                 episode_title = raw_episode_title

    #             if episode_code.lower() in episode_title.lower():
    #                 episode_title = re.sub(re.escape(episode_code), '', episode_title, flags=re.IGNORECASE).strip(" -")

    #             display_text = f"{series_title} - {episode_code} - {episode_title}"

    #             episode_entry = {
    #                 "season": season,
    #                 "episode_num": episode_num,
    #                 "name": display_text,
    #                 "url": f"{self.server}/series/{self.username}/{self.password}/{episode['id']}.{episode.get('container_extension', 'm3u8')}",
    #                 "title": episode_title
    #             }

    #             item = QListWidgetItem(display_text)
    #             item.setData(Qt.UserRole, episode_entry)
    #             item.setIcon(self.series_channel_icon)
    #             items.append(item)

    #         for item in items:
    #             list_widget.addItem(item)

    #         if restore_scroll_position:
    #             QTimer.singleShot(0, lambda: list_widget.verticalScrollBar().setValue(scroll_position))
    #         else:
    #             list_widget.verticalScrollBar().setValue(0)

    #         self.current_episodes = episodes_sorted
    #     except Exception as e:
    #         print(f"Error displaying episodes: {e}")

    # def play_channel(self, entry):
    #     try:
    #         stream_url = entry.get("url")
    #         print(f"stream_url: {stream_url}")
    #         if not stream_url:
    #             self.animate_progress(0, 100, "Stream URL not found")
    #             return
    #         if self.external_player_command:
    #             subprocess.Popen([self.external_player_command, stream_url])
    #         else:
    #             self.animate_progress(0, 100, "No external player configured")
    #     except Exception as e:
    #         print(f"Error playing channel: {e}")
    #         self.animate_progress(0, 100, "Error playing channel")

    # def on_tab_change(self, index):
    #     try:
    #         tab_name = self.tab_widget.tabText(index)

    #         if tab_name == "Info":
    #             if not self.info_tab_initialized:
    #                 self.result_display.clear()
    #                 self.result_display.setText("Ready to fetch and display data.")
    #                 self.info_tab_initialized = True
    #             return
    #         elif tab_name == "Settings":
    #             pass
    #         elif self.login_type == 'xtream':
    #             stack = self.navigation_stacks.get(tab_name, [])
    #             list_widget = self.get_list_widget(tab_name)

    #             if not stack:
    #                 self.update_category_lists(tab_name)
    #                 list_widget.verticalScrollBar().setValue(
    #                     self.top_level_scroll_positions.get(tab_name, 0)
    #                 )
    #             else:
    #                 last_level = stack[-1]
    #                 level = last_level['level']
    #                 data = last_level['data']
    #                 scroll_position = last_level.get('scroll_position', 0)

    #                 if level == 'channels':
    #                     self.entries_per_stream_type[tab_name] = data['entries']
    #                     self.show_channels(list_widget, tab_name)
    #                     list_widget.verticalScrollBar().setValue(scroll_position)
    #                 elif level == 'series_categories':
    #                     self.show_series_in_category(
    #                         data['series_list'],
    #                         restore_scroll_position=True,
    #                         scroll_position=scroll_position
    #                     )
    #                 elif level == 'series':
    #                     self.show_seasons(
    #                         data['seasons'],
    #                         restore_scroll_position=True,
    #                         scroll_position=scroll_position
    #                     )
    #                 elif level == 'season':
    #                     self.show_episodes(
    #                         data['episodes'],
    #                         restore_scroll_position=True,
    #                         scroll_position=scroll_position
    #                     )

    #     except Exception as e:
    #         print(f"Error while switching tabs: {e}")

    def choose_external_player(self):
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.ExistingFile)
        if sys.platform.startswith('win'):
            file_dialog.setNameFilter("Executable files (*.exe *.bat)")
        else:
            file_dialog.setNameFilter("Executable files (*)")
        file_dialog.setWindowTitle("Select External Media Player")
        if file_dialog.exec_():
            file_paths = file_dialog.selectedFiles()
            if len(file_paths) > 0:
                self.external_player_command = file_paths[0]
                self.save_external_player_command()
                print("External Player selected:", self.external_player_command)

    def show_context_menu(self, position):
        sender = self.sender()
        menu = QMenu()
        sort_action = QAction("Sort Alphabetically", self)
        sort_action.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_ArrowUp))
        sort_action.triggered.connect(lambda: self.sort_channel_list(sender))
        menu.addAction(sort_action)
        menu.exec_(sender.viewport().mapToGlobal(position))

    def sort_channel_list(self, list_widget):
        try:
            items = []
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                if item.text() != self.go_back_text:
                    items.append(item)

            items.sort(key=lambda x: x.text())
            list_widget.clear()

            current_tab = self.tab_widget.tabText(self.tab_widget.currentIndex())
            if self.navigation_stacks[current_tab]:
                go_back_item = QListWidgetItem(self.go_back_text)
                go_back_item.setIcon(self.go_back_icon)
                list_widget.addItem(go_back_item)

            for item in items:
                list_widget.addItem(item)
        except Exception as e:
            print(f"Error sorting channel list: {e}")

    def search_in_list(self, tab_name, text):
        list_widget = self.get_list_widget(tab_name)
        if list_widget.count() == 0:
            self.show_channels(list_widget, tab_name)
            print("list is empty")

        if not list_widget:
            print("not list widget")
            # for i in range(len(self.entries_per_stream_type[tab_name])):
            #     print(self.entries_per_stream_type[tab_name][i])
            #     print("\n\n")
            return

        list_widget.clear()

        # for i in range(len(self.navigation_stacks[tab_name])):
        #     print(self.navigation_stacks[tab_name][i])
        #     print("\n\n")
        # for i in range(len(self.entries_per_stream_type[tab_name])):
        #     print(self.entries_per_stream_type[tab_name][i])
        #     print("\n\n")
        # if self.navigation_stacks[tab_name]:
        #     go_back_item = QListWidgetItem(self.go_back_text)
        #     go_back_item.setIcon(self.go_back_icon)
        #     list_widget.addItem(go_back_item)

        filtered_items = []
        if self.login_type == 'xtream':
            if tab_name != "Series":
                print("not series")
                print(tab_name)
                # print(list(self.entries_per_stream_type['LIVE']))
                # print(list(self.navigation_stacks['LIVE']))

                for entry in self.entries_per_stream_type[tab_name]:
                    if text.lower() in entry['name'].lower():
                        item = QListWidgetItem(entry['name'])
                        item.setData(Qt.UserRole, entry)
                        if tab_name == 'LIVE':
                            channel_icon = self.live_channel_icon
                        elif tab_name == 'Movies':
                            channel_icon = self.movies_channel_icon
                        elif tab_name == 'Series':
                            channel_icon = self.series_channel_icon
                        else:
                            channel_icon = self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)
                        item.setIcon(channel_icon)
                        filtered_items.append(item)
            else:
                print("is series")
                # print(self.navigation_stacks['Series'])
                # print(self.navigation_stacks['Series'][-1]['data'])
                stack = self.navigation_stacks['Series']

                # try:
                #     for i in range(len(self.navigation_stacks['Series'][-1]['data']['series_list'])):
                #         print(self.navigation_stacks['Series'][-1]['data']['series_list'][i])
                #         print("\n")
                # except Exception as e:
                #     print(f"failed: {e}")

                if not stack or stack[-1]['level'] == 'series_categories':
                    print("in series category")
                    # for group in self.categories_per_stream_type["Series"]:
                    #     if text.lower() in group["category_name"].lower():
                    #         item = QListWidgetItem(group["category_name"])
                    #         item.setIcon(self.series_channel_icon)
                    #         filtered_items.append(item)
                    for entry in self.current_series_list:
                        if text.lower() in entry['name'].lower():
                            item = QListWidgetItem(entry['name'])
                            item.setData(Qt.UserRole, entry)
                            item.setIcon(self.series_channel_icon)
                            filtered_items.append(item)
                elif stack[-1]['level'] == 'series':
                    print("in series list")
                    # for entry in self.current_series_list:
                    #     if text.lower() in entry['name'].lower():
                    #         item = QListWidgetItem(entry['name'])
                    #         item.setData(Qt.UserRole, entry)
                    #         item.setIcon(self.series_channel_icon)
                    #         filtered_items.append(item)
                    for season in self.current_seasons:
                        if text.lower() in f"Season {season}".lower():
                            item = QListWidgetItem(f"Season {season}")
                            item.setData(Qt.UserRole, season)
                            item.setIcon(self.series_channel_icon)
                            filtered_items.append(item)

                    go_back_item = QListWidgetItem(self.go_back_text)
                    go_back_item.setIcon(self.go_back_icon)
                    list_widget.addItem(go_back_item)
                elif stack[-1]['level'] == 'season':
                    print("in seasons")
                    # for season in self.current_seasons:
                    #     if text.lower() in f"Season {season}".lower():
                    #         item = QListWidgetItem(f"Season {season}")
                    #         item.setData(Qt.UserRole, season)
                    #         item.setIcon(self.series_channel_icon)
                    #         filtered_items.append(item)
                # elif stack[-1]['level'] == 'episode':
                #     print("in episodes")
                    for episode in self.current_episodes:
                        if text.lower() in episode['title'].lower():
                            episode_entry = {
                                "season": episode.get('season'),
                                "episode_num": episode['episode_num'],
                                "name": f"{episode['title']}",
                                "url": f"{self.server}/series/{self.username}/{self.password}/{episode['id']}.{episode.get('container_extension', 'm3u8')}",
                                "title": episode['title']
                            }
                            # item = QListWidgetItem(f"Episode {episode['episode_num']}: {episode['title']}")
                            item = QListWidgetItem(f"{episode['title']}")
                            item.setData(Qt.UserRole, episode_entry)
                            item.setIcon(self.series_channel_icon)
                            filtered_items.append(item)
                    go_back_item = QListWidgetItem(self.go_back_text)
                    go_back_item.setIcon(self.go_back_icon)
                    list_widget.addItem(go_back_item)
                else:
                    print("was nothing")

        if not filtered_items:
            print("filtered items is empty")
            list_widget.addItem(QListWidgetItem("No search results..."))
            return

        filtered_items.sort(key=lambda x: x.text())
        for item in filtered_items:
            list_widget.addItem(item)

    def get_list_widget(self, tab_name):
        return self.list_widgets.get(tab_name)

    def get_category_list_widget(self, tab_name):
        return self.category_list_widgets.get(tab_name)

    def load_external_player_command(self):
        config = configparser.ConfigParser()
        config.read('config.ini')
        if 'ExternalPlayer' in config:
            self.external_player_command = config['ExternalPlayer'].get('Command', '')

    def save_external_player_command(self):
        config = configparser.ConfigParser()
        config['ExternalPlayer'] = {'Command': self.external_player_command}
        with open('config.ini', 'w') as config_file:
            config.write(config_file)

    def on_epg_checkbox_toggled(self, state):
        # If EPG is checked after we already logged in and no EPG data loaded, start it now.
        if state == Qt.Checked:
            if self.login_type == 'xtream' and self.server and self.username and self.password and not self.epg_data:
                # Reset progress and load EPG
                self.reset_progress_bar()
                self.animate_progress(0, 50, "Loading EPG data...")
                self.load_epg_data_async()

    def open_address_book(self):
        dialog = AddressBookDialog(self)
        dialog.exec_()

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    player = IPTVPlayerApp()
    player.show()
    QtWidgets.qApp.processEvents()
    player.load_data_startup()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
