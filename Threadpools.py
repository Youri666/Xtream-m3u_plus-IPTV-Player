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
from PyQt5.QtGui import QIcon, QFont, QImage, QPixmap, QColor
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize, QObject, pyqtSignal, 
    QRunnable, pyqtSlot, QThreadPool, QModelIndex, QAbstractItemModel, QVariant
)
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QLineEdit, QLabel, QPushButton,
    QListWidget, QWidget, QFileDialog, QCheckBox, QSizePolicy, QHBoxLayout,
    QDialog, QFormLayout, QDialogButtonBox, QTabWidget, QListWidgetItem,
    QSpinBox, QMenu, QAction, QTextEdit, QGridLayout, QMessageBox, QListView,
    QTreeWidget, QTreeWidgetItem, QTreeView
)

import base64

# CUSTOM_USER_AGENT = (
#     "Connection: Keep-Alive User-Agent: okhttp/5.0.0-alpha.2 "
#     "Accept-Encoding: gzip, deflate"
# )

CONNECTION_HEADER           = "Keep-Alive"
CONTENT_HEADER              = "gzip, deflate"
DEFAULT_USER_AGENT_HEADER   = "Chrome/123.0.0.0"

# CUSTOM_USER_AGENT = "Connection: Keep-Alive Accept-Encoding: gzip, deflate "

CONNECTION_TIMEOUT  = 3
READ_TIMEOUT        = 10

class FetchDataWorkerSignals(QObject):
    finished        = pyqtSignal(dict, dict, dict)
    error           = pyqtSignal(str)
    progress_bar    = pyqtSignal(int, int, str)
    show_error_msg  = pyqtSignal(str, str)
    show_info_msg   = pyqtSignal(str, str)

class FetchDataWorker(QRunnable):
    def __init__(self, server, username, password, live_url_format, movie_url_format, series_url_format, parent=None):
        super().__init__()
        self.server            = server
        self.username          = username
        self.password          = password
        self.live_url_format   = live_url_format
        self.movie_url_format  = movie_url_format
        self.series_url_format = series_url_format
        self.parent            = parent
        self.signals           = FetchDataWorkerSignals()

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

            #Create header
            headers = {
                "Connection": CONNECTION_HEADER,
                "Accept-Encoding": CONTENT_HEADER,
                "User-Agent": self.parent.current_user_agent
            }

            params = {
                'username': self.username,
                'password': self.password,
                'action': ''
            }

            host_url = f"{self.server}/player_api.php"

            print("Going to fetch IPTV data")

            #Get IPTV info
            self.signals.progress_bar.emit(0, 5, "Fetching IPTV info")
            try:
                iptv_info_resp = requests.get(host_url, params=params, headers=headers, timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT))
                iptv_info_resp.raise_for_status()

                iptv_info_data = iptv_info_resp.json()
            except Exception as e:
                iptv_info_data = {}

                print(f"failed fetching IPTV data: {e}")

            #Load cached data
            cached_data = {}

            #Check if cache file exists
            if path.isfile(self.parent.cache_file):
                print("Cache file is there")

                try:
                    print("Loading cached data")
                    with open(self.parent.cache_file, 'r') as cache_file:
                        cached_data = json.load(cache_file)
                except Exception as e:
                    cached_data = {}

                    # self.signals.show_error_msg.emit('Failed loading cache file', 
                    #         "Failed loading cache file.\n"
                    #         "Please check if it is empty or corrupted.")
                    print("Failed loading cache file. Please check if it is empty or corrupted.")

            config = configparser.ConfigParser()
            config.read(self.parent.user_data_file)

            if 'Debug' in config and config['Debug']['load_with_cache'] == 'True':   #For testing purposes only
                categories_per_stream_type['LIVE'] = cached_data['LIVE categories']
                categories_per_stream_type['Movies'] = cached_data['Movies categories']
                categories_per_stream_type['Series'] = cached_data['Series categories']
                entries_per_stream_type['LIVE'] = cached_data['LIVE']
                entries_per_stream_type['Movies'] = cached_data['Movies']
                entries_per_stream_type['Series'] = cached_data['Series']
            else:
                #Get all category data
                print("Fetching Live TV categories")
                self.signals.progress_bar.emit(5, 10, "Fetching LIVE Categories")
                try:
                    params['action'] = 'get_live_categories'
                    live_category_resp = requests.get(host_url, params=params, headers=headers, timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT))
                    live_category_resp.raise_for_status()  #Raises HTTP error is status is 4xx or 5xx

                    categories_per_stream_type['LIVE'] = live_category_resp.json()
                except Exception as e:
                    print(f"failed fetching LIVE categories: {e}")

                    if cached_data.get('LIVE categories', 0):
                        print("Getting LIVE categories from cache")
                        categories_per_stream_type['LIVE'] = cached_data['LIVE categories']

                        #Notify user that data is fetched from cache file
                        # self.signals.show_info_msg.emit('Getting IPTV data from cache', 
                        #     "Couldn't get Live TV categories from IPTV provider.\n"
                        #     "Please check your internet connection or if IPTV server is still online.\n"
                        #     "Fortunately, Live TV categories could be loaded from cache.")
                        print("Failed fetching Live TV categories. Got them from cache.")
                    else:
                        #Display error msg that data fetching failed
                        # self.signals.show_error_msg.emit('Failed fetching data from IPTV provider', 
                        #     "Couldn't get Live TV categories from IPTV provider.\n"
                        #     "Please check your internet connection or if IPTV server is still online.")
                        print("Failed fetching Live TV categories")

                print("Fetching Movies categories")
                self.signals.progress_bar.emit(10, 20, "Fetching VOD Categories")
                try:
                    params['action'] = 'get_vod_categories'
                    movies_category_resp = requests.get(host_url, params=params, headers=headers, timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT))
                    movies_category_resp.raise_for_status()  #Raises HTTP error is status is 4xx or 5xx

                    categories_per_stream_type['Movies'] = movies_category_resp.json()
                except Exception as e:
                    print(f"failed fetching VOD categories: {e}")

                    if cached_data.get('Movies categories', 0):
                        print("Getting Movies categories from cache")
                        categories_per_stream_type['Movies'] = cached_data['Movies categories']

                        #Notify user that data is fetched from cache file
                        # self.signals.show_info_msg.emit('Getting IPTV data from cache', 
                        #     "Couldn't get Movies categories from IPTV provider.\n"
                        #     "Please check your internet connection or if IPTV server is still online.\n"
                        #     "Fortunately, Movies categories could be loaded from cache.")
                        print("Failed fetching Movies categories. Got them from cache.")
                    else:
                        #Display error msg that data fetching failed
                        # self.signals.show_error_msg.emit('Failed fetching data from IPTV provider', 
                        #     "Couldn't get Movies categories from IPTV provider.\n"
                        #     "Please check your internet connection or if IPTV server is still online.")
                        print("Failed fetching Movies categories")

                print("Fetching Series categories")
                self.signals.progress_bar.emit(20, 30, "Fetching Series Categories")
                try:
                    params['action'] = 'get_series_categories'
                    series_category_resp = requests.get(host_url, params=params, headers=headers, timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT))
                    series_category_resp.raise_for_status()  #Raises HTTP error is status is 4xx or 5xx

                    categories_per_stream_type['Series'] = series_category_resp.json()
                except Exception as e:
                    print(f"failed fetching Series categories: {e}")

                    if cached_data.get('Series categories', 0):
                        print("Getting Series categories from cache")
                        categories_per_stream_type['Series'] = cached_data['Series categories']

                        #Notify user that data is fetched from cache file
                        # self.signals.show_info_msg.emit('Getting IPTV data from cache', 
                        #     "Couldn't get Series categories from IPTV provider.\n"
                        #     "Please check your internet connection or if IPTV server is still online.\n"
                        #     "Fortunately, Series categories could be loaded from cache.")
                        print("Failed fetching Series categories. Got them from cache.")
                    else:
                        #Display error msg that data fetching failed
                        # self.signals.show_error_msg.emit('Failed fetching data from IPTV provider', 
                        #     "Couldn't get Series categories from IPTV provider.\n"
                        #     "Please check your internet connection or if IPTV server is still online.")
                        print("Failed fetching Series categories")

                print("Fetching Live TV streaming data")
                #Get all streaming data
                self.signals.progress_bar.emit(30, 40, "Fetching LIVE Streaming data")
                try:
                    params['action'] = 'get_live_streams'
                    live_streams_resp = requests.get(host_url, params=params, headers=headers, timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT))
                    live_streams_resp.raise_for_status()  #Raises HTTP error is status is 4xx or 5xx

                    entries_per_stream_type['LIVE'] = live_streams_resp.json()
                except Exception as e:
                    print(f"failed fetching LIVE streams: {e}")

                    if cached_data.get('LIVE', 0):
                        print("Getting LIVE streams from cache")
                        entries_per_stream_type['LIVE'] = cached_data['LIVE']

                        #Notify user that data is fetched from cache file
                        # self.signals.show_info_msg.emit('Getting IPTV data from cache', 
                        #     "Couldn't get Live TV streams from IPTV provider.\n"
                        #     "Please check your internet connection or if IPTV server is still online.\n"
                        #     "Fortunately, Live TV streams could be loaded from cache.")
                        print("Failed fetching Live TV streams. Got them from cache.")
                    else:
                        #Display error msg that data fetching failed
                        # self.signals.show_error_msg.emit('Failed fetching data from IPTV provider', 
                        #     "Couldn't get Live TV streams from IPTV provider.\n"
                        #     "Please check your internet connection or if IPTV server is still online.")
                        print("Failed fetching Live TV streams")

                print("Fetching Movies streaming data")
                self.signals.progress_bar.emit(40, 60, "Fetching VOD Streaming data")
                try:
                    params['action'] = 'get_vod_streams'
                    movies_streams_resp = requests.get(host_url, params=params, headers=headers, timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT))
                    movies_streams_resp.raise_for_status()  #Raises HTTP error is status is 4xx or 5xx

                    entries_per_stream_type['Movies'] = movies_streams_resp.json()
                except Exception as e:
                    print(f"failed fetching VOD streams: {e}")

                    if cached_data.get('Movies', 0):
                        print("Getting Movies streams from cache")
                        entries_per_stream_type['Movies'] = cached_data['Movies']

                        #Notify user that data is fetched from cache file
                        # self.signals.show_info_msg.emit('Getting IPTV data from cache', 
                        #     "Couldn't get Movies streams from IPTV provider.\n"
                        #     "Please check your internet connection or if IPTV server is still online.\n"
                        #     "Fortunately, Movies streams could be loaded from cache.")
                        print("Failed fetching Movies streams. Got them from cache.")
                    else:
                        #Display error msg that data fetching failed
                        # self.signals.show_error_msg.emit('Failed fetching data from IPTV provider', 
                        #     "Couldn't get Movies streams from IPTV provider.\n"
                        #     "Please check your internet connection or if IPTV server is still online.")
                        print("Failed fetching Live TV streams")

                print("Fetching Series streaming data")
                self.signals.progress_bar.emit(60, 80, "Fetching Series Streaming data")
                try:
                    params['action'] = 'get_series'
                    series_streams_resp = requests.get(host_url, params=params, headers=headers, timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT))
                    series_streams_resp.raise_for_status()  #Raises HTTP error is status is 4xx or 5xx

                    entries_per_stream_type['Series'] = series_streams_resp.json()
                except Exception as e:
                    print(f"failed fetching Series streams: {e}")

                    if cached_data.get('Series', 0):
                        print("Getting Series streams from cache")
                        entries_per_stream_type['Series'] = cached_data['Series']

                        #Notify user that data is fetched from cache file
                        # self.signals.show_info_msg.emit('Getting IPTV data from cache', 
                        #     "Couldn't get Series streams from IPTV provider.\n"
                        #     "Please check your internet connection or if IPTV server is still online.\n"
                        #     "Fortunately, Series streams could be loaded from cache.")
                        print("Failed fetching Series streams. Got them from cache.")
                    else:
                        #Display error msg that data fetching failed
                        # self.signals.show_error_msg.emit('Failed fetching data from IPTV provider', 
                        #     "Couldn't get Series streams from IPTV provider.\n"
                        #     "Please check your internet connection or if IPTV server is still online.")
                        print("Failed fetching Series streams")

                print("going to create cached data")

                all_cached_data = json.dumps({
                        'LIVE categories': categories_per_stream_type['LIVE'],
                        'Movies categories': categories_per_stream_type['Movies'],
                        'Series categories': categories_per_stream_type['Series'],
                        'LIVE': entries_per_stream_type['LIVE'],
                        'Movies': entries_per_stream_type['Movies'],
                        'Series': entries_per_stream_type['Series']
                    }, 
                    indent=4)

                with open(self.parent.cache_file, 'w') as cache_file:
                    cache_file.write(all_cached_data)

            # self.set_progress_bar(100, "Finished loading data")
            self.signals.progress_bar.emit(80, 100, "Finished Fetching data")

            fav_data = {}

            #Check if cache file exists
            if path.isfile(self.parent.favorites_file):
                print("Favorites file is there")

                with open(self.parent.favorites_file, 'r') as fav_file:
                    fav_data = json.load(fav_file)

            print("Preparing streaming data")
            #Make streaming URL in each entry except for the series
            for tab_name in entries_per_stream_type.keys():
                for idx, entry in enumerate(entries_per_stream_type[tab_name]):
                    #Get stream type. If no stream_type is found it is series
                    stream_type         = entry.get('stream_type', 'series')
                    stream_id           = entry.get("stream_id", -1)
                    series_id           = entry.get("series_id", -1)
                    container_extension = entry.get("container_extension", "m3u8")

                    #Correct for any vague other stream types. Series stream type is already fixed by code above.
                    if "live" in stream_type:
                        stream_type = "live"

                    if "movie" in stream_type:
                        stream_type = "movie"

                    #Check if stream_id is valid
                    if stream_id:
                        entries_per_stream_type[tab_name][idx]["url"] = self.generate_url(stream_type, stream_id, container_extension)

                        #Check if stream id is in favorites list in userdata.ini
                        if stream_id in fav_data.get('stream_ids', []):
                            #Add "favorite" parameter to entries_per_stream_type and set to True or False depending if inside userdata.ini
                            entries_per_stream_type[tab_name][idx]['favorite'] = True
                        else:
                            entries_per_stream_type[tab_name][idx]['favorite'] = False
                    else:
                        entries_per_stream_type[tab_name][idx]["url"] = None

                    #Check if stream type is series
                    if stream_type == 'series':
                        #Create stream type key for series data
                        entries_per_stream_type[tab_name][idx]["stream_type"] = stream_type

                        #Check if series_id is valid
                        if series_id:
                            #Check if series id is in favorites list in userdata.ini
                            if series_id in fav_data.get('series_ids', []):
                                #Add "favorite" parameter to entries_per_stream_type and set to True or False depending if inside userdata.ini
                                entries_per_stream_type[tab_name][idx]['favorite'] = True
                            else:
                                entries_per_stream_type[tab_name][idx]['favorite'] = False

            #Send received data to processing function
            self.signals.finished.emit(iptv_info_data, categories_per_stream_type, entries_per_stream_type)

            print("Finished downloading IPTV data")

        except Exception as e:
            print(f"Exception! {e}")
            self.signals.error.emit(str(e))

    def generate_url(self, stream_type, stream_id, container_extension):
        # Select the appropriate format string
        if stream_type == 'live':
            fmt = self.live_url_format
        elif stream_type == 'movie':
            fmt = self.movie_url_format
        else:
            # Fallback format if unknown type
            fmt = "{server}/{stream_type}/{username}/{password}/{stream_id}.{container_extension}"
    
        # Remove extension if not included in the format string
        if ".{container_extension}" not in fmt:
            container_extension = ""
    
        # Format and return the URL
        return fmt.format(
            server=self.server,
            username=self.username,
            password=self.password,
            stream_type=stream_type,
            stream_id=stream_id,
            container_extension=container_extension
        )

class MovieInfoFetcherSignals(QObject):
    finished    = pyqtSignal(dict, dict)
    error       = pyqtSignal(str)

class MovieInfoFetcher(QRunnable):
    def __init__(self, server, username, password, vod_id, parent=None):
        super().__init__()
        self.server     = server
        self.username   = username
        self.password   = password
        self.vod_id     = vod_id
        self.parent     = parent
        self.signals    = MovieInfoFetcherSignals()

    @pyqtSlot()
    def run(self):
        try:
            #Set request parameters
            # headers = {'User-Agent': CUSTOM_USER_AGENT}
            #Create header
            headers = {
                "Connection": CONNECTION_HEADER,
                "Accept-Encoding": CONTENT_HEADER,
                "User-Agent": self.parent.current_user_agent
            }
            host_url = f"{self.server}/player_api.php"
            params = {
                'username': self.username,
                'password': self.password,
                'action': 'get_vod_info',
                'vod_id': self.vod_id
            }

            #Request vod info
            vod_info_resp = requests.get(host_url, params=params, headers=headers, timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT))

            #Get vod info data
            vod_info_data = vod_info_resp.json()

            #Get info and movie data
            vod_info = vod_info_data.get('info', {})
            vod_data = vod_info_data.get('movie_data', {})

            #Check if the variable types are valid
            if not isinstance(vod_info, dict):
                vod_info = {}

            if not isinstance(vod_data, dict):
                vod_data = {}

            #Return movie info data
            self.signals.finished.emit(vod_info, vod_data)
        except Exception as e:
            print(f"Failed fetching movie info: {e}")
            self.signals.error.emit(str(e))

class SeriesInfoFetcherSignals(QObject):
    finished    = pyqtSignal(dict, bool)
    error       = pyqtSignal(str)

class SeriesInfoFetcher(QRunnable):
    def __init__(self, server, username, password, series_id, is_show_request, parent=None):
        super().__init__()
        self.server             = server
        self.username           = username
        self.password           = password
        self.series_id          = series_id
        self.is_show_request    = is_show_request
        self.parent             = parent
        self.signals            = SeriesInfoFetcherSignals()

    @pyqtSlot()
    def run(self):
        try:
            #Set request parameters
            # headers = {'User-Agent': CUSTOM_USER_AGENT}
            #Create header
            headers = {
                "Connection": CONNECTION_HEADER,
                "Accept-Encoding": CONTENT_HEADER,
                "User-Agent": self.parent.current_user_agent
            }
            host_url = f"{self.server}/player_api.php"
            params = {
                'username': self.username,
                'password': self.password,
                'action': 'get_series_info',
                'series_id': self.series_id
            }

            #Request series info
            series_info_resp = requests.get(host_url, params=params, headers=headers, timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT))

            #Get series info data
            series_info_data = series_info_resp.json()

            #Check if the variable type is valid
            if not isinstance(series_info_data, dict):
                series_info_data = {}

            #Return series info data
            self.signals.finished.emit(series_info_data, self.is_show_request)
        except Exception as e:
            print(f"Failed fetching series info: {e}")
            self.signals.error.emit(str(e))
        
class ImageFetcherSignals(QObject):
    finished    = pyqtSignal(QPixmap, str)
    error       = pyqtSignal(str)

class ImageFetcher(QRunnable):
    def __init__(self, img_url, stream_type, parent=None):
        super().__init__()
        self.img_url        = img_url
        self.stream_type    = stream_type
        self.parent         = parent
        self.signals        = ImageFetcherSignals()

    @pyqtSlot()
    def run(self):
        try:
            #Set header for request
            # headers = {'User-Agent': CUSTOM_USER_AGENT}
            #Create header
            headers = {
                "Connection": CONNECTION_HEADER,
                "Accept-Encoding": CONTENT_HEADER,
                "User-Agent": self.parent.current_user_agent
            }

            #Request image
            image_resp = requests.get(self.img_url, headers=headers, timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT))

            #Check if response code is valid, otherwise set replacement image
            resp_status = image_resp.status_code
            if resp_status == 404:
                #Set 404 error as image
                image = QPixmap(self.parent.path_to_404_img)

            elif not resp_status == 200:
                #Set no image
                image = QPixmap(self.parent.path_to_no_img)

            else:
                #Create QPixmap from image data
                image = QPixmap()
                image.loadFromData(image_resp.content)  #Don't combine this with the previous line, then it doesn't work

            #Check if Pixmap is valid
            if image.isNull():
                image = QPixmap(self.parent.path_to_no_img)

            #Emit image
            self.signals.finished.emit(image, self.stream_type)
        except Exception as e:
            print(f"Failed fetching image: {e}")

            #Emit no image placeholder
            image = QPixmap(self.parent.path_to_no_img)
            self.signals.finished.emit(image, self.stream_type)
            self.signals.error.emit(str(e))

class SearchWorkerSignals(QObject):
    list_widget = pyqtSignal(list, str)
    error = pyqtSignal(str)

class SearchWorker(QRunnable):
    def __init__(self, stream_type, currently_loaded_entries, list_widgets, text):
        super().__init__()
        self.stream_type = stream_type
        self.currently_loaded_entries = currently_loaded_entries[0]
        self.list_widgets = list_widgets[0]
        self.text = text

        self.signals = SearchWorkerSignals()

        # self.setAutoDelete(True)

    @pyqtSlot()
    def run(self):
        try:
            self.list_widgets[self.stream_type].clear()
            print("starting searching through entries")

            for entry in self.currently_loaded_entries[self.stream_type]:
                if self.text.lower() in entry['name'].lower():
                    item = QListWidgetItem(entry['name'])
                    item.setData(Qt.UserRole, entry)

                    self.list_widgets[self.stream_type].addItem(item)

                    print(entry['name'])

            self.signals.list_widget.emit([self.list_widgets[self.stream_type]], self.stream_type)
        except Exception as e:
            print(f"failed search worker: {e}")

class EPGWorkerSignals(QObject):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

class EPGWorker(QRunnable):
    def __init__(self, server, username, password, stream_id, parent=None):
        super().__init__()
        self.server     = server
        self.username   = username
        self.password   = password
        self.stream_id  = stream_id
        self.parent     = parent
        self.signals    = EPGWorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            #Creating url for requesting EPG data for specific stream
            epg_url = f"{self.server}/player_api.php?username={self.username}&password={self.password}&action=get_simple_data_table&stream_id={self.stream_id}"
            # headers = {'User-Agent': CUSTOM_USER_AGENT}
            #Create header
            headers = {
                "Connection": CONNECTION_HEADER,
                "Accept-Encoding": CONTENT_HEADER,
                "User-Agent": self.parent.current_user_agent
            }

            #Requesting EPG data
            response = requests.get(epg_url, headers=headers, timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT))
            epg_data = response.json()

            #Decrypt EPG data with base 64
            decrypted_epg_data = self.decryptEPGData(epg_data)

            self.signals.finished.emit(decrypted_epg_data)
        except Exception as e:
            self.signals.error.emit(str(e))

    def decryptEPGData(self, epg_data):
        try:
            decrypted_epg_data = []

            for epg_entry in epg_data['epg_listings']:
                #Get start, stop time and date
                start_timestamp = datetime.fromtimestamp(int(epg_entry['start_timestamp']))
                stop_timestamp  = datetime.fromtimestamp(int(epg_entry['stop_timestamp']))
                date            = f"{start_timestamp.day:02}-{start_timestamp.month:02}-{start_timestamp.year}"

                #Decode program name and descryption
                program_name        = base64.b64decode(epg_entry['title']).decode("utf-8")
                program_description = base64.b64decode(epg_entry['description']).decode("utf-8")

                #Put only necessary EPG data in list
                decrypted_epg_data.append({
                    'start_time': start_timestamp,
                    'stop_time': stop_timestamp,
                    'program_name': program_name,
                    'description': program_description,
                    'date': date
                    })

            #return decrypted EPG data
            return decrypted_epg_data
        except Exception as e:
            print(f"failed decrypting: {e}")

