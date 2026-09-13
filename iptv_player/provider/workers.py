from os import path
import time
import requests
from PyQt5.QtCore import QObject, pyqtSignal, QRunnable, pyqtSlot

from iptv_player.provider.cache import (
    account_cache_key,
    build_catalog_cache,
    catalog_cache_is_fresh,
    load_catalog_cache,
    write_catalog_cache,
)
from iptv_player.provider.client import (
    DEFAULT_USER_AGENT_HEADER,
    XtreamClient,
    provider_headers,
)
from iptv_player.provider.catalog import prepare_catalog_entries
from iptv_player.provider.epg import decode_epg_data, decode_epg_text
from iptv_player.provider.network import (
    LIVE_STATUS_CHUNK_SIZE,
    LIVE_STATUS_RETRY_DELAY,
    MAX_LIVE_STATUS_RETRIES,
    NETWORK_SETTINGS,
)
from iptv_player.provider.streams import generate_stream_url
from iptv_player.storage import read_json_mapping

class AccountInfoWorkerSignals(QObject):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)


class AccountInfoWorker(QRunnable):
    """Fetch only account/server metadata from the Xtream player API."""

    def __init__(self, server, username, password, user_agent):
        super().__init__()
        self.server = server
        self.username = username
        self.password = password
        self.user_agent = user_agent
        self.signals = AccountInfoWorkerSignals()

    @pyqtSlot()
    def run(self):
        # A fresh cache hit never creates a provider client. Initialize the handle
        # before branching so cleanup is safe for both cached and network loads.
        client = None
        try:
            with XtreamClient(
                self.server,
                self.username,
                self.password,
                self.user_agent,
                (NETWORK_SETTINGS.connection_timeout, NETWORK_SETTINGS.read_timeout),
            ) as client:
                data = client.get_json()
            if not isinstance(data, dict):
                raise ValueError("The provider returned invalid account information")
            self.signals.finished.emit(data)
        except Exception as error:
            self.signals.error.emit(str(error))

class FetchDataWorkerSignals(QObject):
    finished        = pyqtSignal(dict, dict, dict)
    error           = pyqtSignal(str)
    progress_bar    = pyqtSignal(int, int, str)
    show_error_msg  = pyqtSignal(str, str)
    show_info_msg   = pyqtSignal(str, str)

class FetchDataWorker(QRunnable):
    def __init__(self, server, username, password, live_url_format, movie_url_format,
                 series_url_format, parent=None, enabled_stream_types=None,
                 catalog_cache_enabled=True, catalog_cache_max_age_hours=24,
                 force_provider_refresh=False):
        super().__init__()
        self.server            = server
        self.username          = username
        self.password          = password
        self.live_url_format   = live_url_format
        self.movie_url_format  = movie_url_format
        self.series_url_format = series_url_format
        # Copy the selection because the Settings checkboxes may change while this
        # worker is running. A missing value keeps the historical all-content default.
        enabled_stream_types = enabled_stream_types or {
            'LIVE': True,
            'Movies': True,
            'Series': True
        }
        self.enabled_stream_types = {
            stream_type: bool(enabled_stream_types.get(stream_type, True))
            for stream_type in ('LIVE', 'Movies', 'Series')
        }
        self.parent            = parent
        self.catalog_cache_enabled = bool(catalog_cache_enabled)
        self.catalog_cache_max_age_hours = max(
            1, min(int(catalog_cache_max_age_hours), 720)
        )
        self.force_provider_refresh = bool(force_provider_refresh)
        self.signals           = FetchDataWorkerSignals()

    def _cache_account_key(self):
        """Identify a provider account without writing credentials to the cache."""
        return account_cache_key(self.server, self.username)

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
            # Fall back to the default UA when the user hasn't picked one — sending an
            # empty User-Agent makes some providers return 403 or empty category lists
            # (related to issues #69 and #10).
            ua = (self.parent.current_user_agent or "").strip() or DEFAULT_USER_AGENT_HEADER
            print("Going to fetch IPTV data")

            iptv_info_data = {}

            # Load only cache data belonging to this provider account. Older cache
            # files have no metadata and are refreshed once before becoming trusted.
            cached_data = {}
            if self.catalog_cache_enabled and path.isfile(self.parent.cache_file):
                print("Cache file is there")

                print("Loading cached data")
                cached_data = load_catalog_cache(self.parent.cache_file)
                if not cached_data:
                    cached_data = {}

                    # self.signals.show_error_msg.emit('Failed loading cache file', 
                    #         "Failed loading cache file.\n"
                    #         "Please check if it is empty or corrupted.")
                    print("Failed loading cache file. Please check if it is empty or corrupted.")

            metadata = cached_data.get('_metadata', {})
            cache_matches_account = (
                metadata.get('account_key') == self._cache_account_key()
            )
            cache_is_fresh = (
                self.catalog_cache_enabled
                and not self.force_provider_refresh
                and catalog_cache_is_fresh(
                    cached_data,
                    self._cache_account_key(),
                    self.enabled_stream_types,
                    self.catalog_cache_max_age_hours,
                )
            )

            if cache_is_fresh:
                self.signals.progress_bar.emit(0, 80, "Loading provider catalog from cache")
                for stream_type in ('LIVE', 'Movies', 'Series'):
                    if not self.enabled_stream_types[stream_type]:
                        continue
                    categories_per_stream_type[stream_type] = cached_data.get(
                        f'{stream_type} categories', []
                    )
                    entries_per_stream_type[stream_type] = cached_data.get(stream_type, [])
            else:
                client = XtreamClient(
                    self.server,
                    self.username,
                    self.password,
                    ua,
                    (NETWORK_SETTINGS.connection_timeout, NETWORK_SETTINGS.read_timeout),
                )
                # Account metadata stays out of the catalog cache because provider
                # responses can contain credentials. The Info tab can refresh it later.
                self.signals.progress_bar.emit(0, 5, "Fetching IPTV info")
                try:
                    iptv_info_data = client.get_json()
                except Exception as e:
                    print(f"failed fetching IPTV data: {e}")

                # Describe the six provider collections in one table so each content
                # toggle controls both its category and stream requests consistently.
                request_plan = (
                    ('LIVE', 'categories', 'get_live_categories', 'LIVE categories', 5, 10),
                    ('Movies', 'categories', 'get_vod_categories', 'Movies categories', 10, 20),
                    ('Series', 'categories', 'get_series_categories', 'Series categories', 20, 30),
                    ('LIVE', 'streams', 'get_live_streams', 'LIVE', 30, 40),
                    ('Movies', 'streams', 'get_vod_streams', 'Movies', 40, 60),
                    ('Series', 'streams', 'get_series', 'Series', 60, 80),
                )
                catalog_fetch_complete = True

                for stream_type, collection, action, cache_key, start, end in request_plan:
                    if not self.enabled_stream_types[stream_type]:
                        print(f"Skipping disabled {stream_type} {collection}")
                        continue

                    label = f"{stream_type} {collection}"
                    print(f"Fetching {label}")
                    self.signals.progress_bar.emit(start, end, f"Fetching {label}")
                    try:
                        result = client.get_json(action)
                    except Exception as e:
                        catalog_fetch_complete = False
                        print(f"Failed fetching {label}: {e}")
                        result = (
                            cached_data.get(cache_key, [])
                            if cache_matches_account else []
                        )
                        if result:
                            print(f"Loaded {label} from cache")

                    destination = (
                        categories_per_stream_type
                        if collection == 'categories'
                        else entries_per_stream_type
                    )
                    destination[stream_type] = result

                print("going to create cached data")

                # Preserve cached collections for disabled content. Disabling Movies,
                # for example, must not erase its useful fallback data from disk.
                if self.catalog_cache_enabled:
                    cache_to_write = build_catalog_cache(
                        cached_data,
                        self._cache_account_key(),
                        categories_per_stream_type,
                        entries_per_stream_type,
                        self.enabled_stream_types,
                        catalog_fetch_complete,
                    )
                    try:
                        write_catalog_cache(self.parent.cache_file, cache_to_write)
                    except OSError as error:
                        # Cache persistence must not discard data already fetched.
                        print(f"Failed writing provider cache: {error}")
            self.signals.progress_bar.emit(80, 100, "Provider catalog ready")

            print("Preparing streaming data")
            prepare_catalog_entries(
                entries_per_stream_type,
                read_json_mapping(self.parent.favorites_file),
                self.generate_url,
            )

            #Send received data to processing function
            self.signals.finished.emit(iptv_info_data, categories_per_stream_type, entries_per_stream_type)

            print("Finished downloading IPTV data")

        except Exception as e:
            print(f"Exception! {e}")
            self.signals.error.emit(str(e))
        finally:
            if client is not None:
                client.close()

    def generate_url(self, stream_type, stream_id, container_extension):
        """Keep the worker API while delegating URL formatting to the provider layer."""
        return generate_stream_url(
            self.server,
            self.username,
            self.password,
            stream_type,
            stream_id,
            container_extension,
            self.live_url_format,
            self.movie_url_format,
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
            # Fall back to the default UA when the user hasn't picked one — sending an
            # empty User-Agent makes some providers return 403 or empty category lists
            # (related to issues #69 and #10).
            ua = (self.parent.current_user_agent or "").strip() or DEFAULT_USER_AGENT_HEADER
            headers = provider_headers(ua)
            host_url = f"{self.server}/player_api.php"
            params = {
                'username': self.username,
                'password': self.password,
                'action': 'get_vod_info',
                'vod_id': self.vod_id
            }

            #Request vod info
            vod_info_resp = requests.get(
                host_url,
                params=params,
                headers=headers,
                timeout=(
                    NETWORK_SETTINGS.connection_timeout,
                    NETWORK_SETTINGS.read_timeout,
                ),
            )

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
            # Fall back to the default UA when the user hasn't picked one — sending an
            # empty User-Agent makes some providers return 403 or empty category lists
            # (related to issues #69 and #10).
            ua = (self.parent.current_user_agent or "").strip() or DEFAULT_USER_AGENT_HEADER
            headers = provider_headers(ua)
            host_url = f"{self.server}/player_api.php"
            params = {
                'username': self.username,
                'password': self.password,
                'action': 'get_series_info',
                'series_id': self.series_id
            }

            #Request series info
            series_info_resp = requests.get(
                host_url,
                params=params,
                headers=headers,
                timeout=(
                    NETWORK_SETTINGS.connection_timeout,
                    NETWORK_SETTINGS.read_timeout,
                ),
            )

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
    finished    = pyqtSignal(bytes, str)
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
        client = None
        try:
            # Skip the network call entirely if the entry didn't have a logo/cover URL —
            # otherwise requests raises "No scheme supplied" and floods the log.
            if not self.img_url or not str(self.img_url).strip():
                self.signals.finished.emit(
                    self._read_placeholder(self.parent.path_to_no_img),
                    self.stream_type,
                )
                return

            # Fall back to the default UA when the user hasn't picked one — sending an
            # empty User-Agent makes some providers return 403 or empty category lists
            # (related to issues #69 and #10).
            ua = (self.parent.current_user_agent or "").strip() or DEFAULT_USER_AGENT_HEADER
            headers = provider_headers(ua)

            #Request image
            image_resp = requests.get(
                self.img_url,
                headers=headers,
                timeout=(
                    NETWORK_SETTINGS.connection_timeout,
                    NETWORK_SETTINGS.read_timeout,
                ),
            )

            #Check if response code is valid, otherwise set replacement image
            resp_status = image_resp.status_code
            if resp_status == 404:
                image_data = self._read_placeholder(self.parent.path_to_404_img)

            elif not resp_status == 200:
                image_data = self._read_placeholder(self.parent.path_to_no_img)

            else:
                image_data = image_resp.content

            # QPixmap is a GUI resource and must be created by the main thread.
            self.signals.finished.emit(image_data, self.stream_type)
        except Exception as e:
            print(f"Failed fetching image: {e}")

            self.signals.finished.emit(
                self._read_placeholder(self.parent.path_to_no_img),
                self.stream_type,
            )
            self.signals.error.emit(str(e))

    @staticmethod
    def _read_placeholder(filename):
        """Read placeholder bytes without constructing GUI objects in this worker."""
        with open(filename, "rb") as image_file:
            return image_file.read()

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
            # Fall back to the default UA when the user hasn't picked one — sending an
            # empty User-Agent makes some providers return 403 or empty category lists
            # (related to issues #69 and #10).
            ua = (self.parent.current_user_agent or "").strip() or DEFAULT_USER_AGENT_HEADER
            headers = provider_headers(ua)

            #Requesting EPG data
            response = requests.get(
                epg_url,
                headers=headers,
                timeout=(
                    NETWORK_SETTINGS.connection_timeout,
                    NETWORK_SETTINGS.read_timeout,
                ),
            )
            epg_data = response.json()

            #Decrypt EPG data with base 64
            decrypted_epg_data = self.decrypt_epg_data(epg_data)

            self.signals.finished.emit(decrypted_epg_data)
        except Exception as e:
            self.signals.error.emit(str(e))

    def _decode_epg_text(self, raw_bytes):
        """Keep the historical worker method while delegating pure decoding."""
        return decode_epg_text(raw_bytes)

    def decrypt_epg_data(self, epg_data):
        try:
            return decode_epg_data(epg_data)
        except Exception as e:
            print(f"failed decrypting: {e}")

class OnlineWorkerSignals(QObject):
    finished = pyqtSignal(int, str)
    error = pyqtSignal(str)

class OnlineWorker(QRunnable):
    def __init__(self, stream_id, url, parent=None):
        super().__init__()
        self.stream_id  = int(stream_id)
        self.url        = url
        self.parent     = parent
        self.signals    = OnlineWorkerSignals()

    @pyqtSlot()
    def run(self):
        """Probe a LIVE stream and emit one final status after all retries."""

        # Fall back to the default UA when the user has not picked one. Sending an
        # empty User-Agent makes some providers return 403 or empty responses.
        ua = (self.parent.current_user_agent or "").strip() or DEFAULT_USER_AGENT_HEADER
        headers = provider_headers(ua)

        # Clamp the global value because userdata.ini can be edited manually and
        # therefore cannot be trusted to respect the GUI validator.
        retry_count = max(
            0,
            min(int(NETWORK_SETTINGS.live_status_retries), MAX_LIVE_STATUS_RETRIES),
        )
        best_status = False
        received_response = False
        last_error = None

        # Do not emit a red state between attempts. A transient provider failure
        # should not make the traffic light flicker before a later probe succeeds.
        for attempt in range(retry_count + 1):
            try:
                stream_status = self.request_status(headers)
                received_response = True

                # A confirmed successful probe is definitive and needs no retry.
                if stream_status is True:
                    self.signals.finished.emit(self.stream_id, str(stream_status))
                    return

                # Preserve "Maybe" over False when the provider reports a stream
                # that appears to be starting, even if a later retry fails.
                if stream_status == "Maybe":
                    best_status = "Maybe"
            except Exception as e:
                last_error = e

            if attempt < retry_count:
                time.sleep(LIVE_STATUS_RETRY_DELAY)

        # HTTP responses produce a final red/amber status. The unknown state is
        # reserved for the case where every attempt failed at the network layer.
        if received_response:
            self.signals.finished.emit(self.stream_id, str(best_status))
        else:
            self.signals.error.emit(str(last_error))

    def request_status(self, headers):
        """Read one small chunk instead of waiting for a continuous stream to end."""

        # Direct .ts streams may never finish. Streaming the response and closing it
        # after the first 4 KiB proves that bytes are arriving without downloading
        # the programme itself or holding an extra provider connection open.
        with requests.get(
            self.url,
            headers=headers,
            timeout=(
                NETWORK_SETTINGS.connection_timeout,
                NETWORK_SETTINGS.live_status_timeout,
            ),
            stream=True
        ) as response:
            response_code = response.status_code
            url_data = response.url
            received_data = False

            if response_code == 200:
                for chunk in response.iter_content(chunk_size=LIVE_STATUS_CHUNK_SIZE):
                    if chunk:
                        received_data = True
                        url_data += "\n" + chunk.decode("utf-8", errors="ignore")
                        break

                # A successful HTTP response without payload does not prove that the
                # channel is usable, so treat it as an offline probe.
                if not received_data:
                    return False

        return self.check_status(response_code, url_data)

    def check_status(self, response_code, url_data):
        if response_code != 200:  # need HTTP OK status
            return False

        # Provider-generated playlists are not consistent about letter case.
        normalized_url_data = url_data.lower()

        if "offline" in normalized_url_data: #some providers use offline.m3u8 as a dummy video file
            return False
        
        if "ext-x-endlist" in normalized_url_data: #m3u file is saying stream is over
            return False
        
        if "#ext-x-media-sequence:0" in normalized_url_data:                 #some providers respond with a fresh "Stream starting soon" stream
            if "_0.ts" in normalized_url_data and "_1.ts" not in normalized_url_data:   #this technically just means a stream is freshly started, hence the "Maybe" online
                return "Maybe"                                    #officially, see https://datatracker.ietf.org/doc/html/rfc8216#section-4.3.3.2

        return True
