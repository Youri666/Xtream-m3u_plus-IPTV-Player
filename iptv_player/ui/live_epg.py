"""Keep the main LIVE schedule current without rebuilding unchanged rows."""
from datetime import datetime
import time

from PyQt5.QtCore import QObject, QTimer
from PyQt5.QtWidgets import QTreeWidgetItem

from iptv_player.programme_info import EpgRefreshState


class LiveEpgController(QObject):
    """Share cached provider requests with the player's Programme panel."""
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.key = None
        self.payload = None
        self.signature = None
        self.refresh = EpgRefreshState()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def current(self, key):
        window = self.window
        return (key == self.key and key[0] == window.active_account_id
                and window._is_current_info_request('LIVE', key[2]))

    def select(self, stream_id, generation=None):
        window = self.window
        generation = window._info_request_generation['LIVE'] if generation is None else generation
        self.key = (window.active_account_id, str(stream_id), generation)
        self.payload = None
        self.signature = None
        self.refresh = EpgRefreshState()
        service = window._get_programme_service()
        service.register(window.active_account_id, window.server, window.username,
                         window.password, window.current_user_agent, window.epg_offset_minutes)
        self._request()

    def _request(self):
        if self.refresh.pending:
            return
        key = self.key
        self.refresh.begin()
        self.window._get_programme_service().request({
            'generation': key[2], 'history': {'account_id': key[0], 'type': 'LIVE',
                                            'stream_id': key[1]}},
            callback=lambda payload: self._received(key, payload))

    def _received(self, key, payload):
        if not self.current(key):
            return
        self.refresh.received(payload)
        if payload.get('message'):
            # Preserve an existing schedule on a background provider failure.
            if self.payload is None:
                self.window.live_info_box.live_EPG_info.clear()
                self.window.on_epg_fetch_error('Provider EPG request failed', key[2])
            return
        initial = self.payload is None
        self.payload = payload
        self._render()
        if initial:
            self.window.set_progress_bar(100, 'Loaded EPG data' if payload.get('entries') else 'No EPG data')

    def tick(self):
        window = self.window
        if (self.key is None or not self.current(self.key)
                or not window.live_info_box.isVisible() or window.isMinimized()
                or getattr(window, '_catalog_installing', False)):
            return
        self._render()
        if self.refresh.due(self.payload):
            self._request()

    def _render(self):
        if self.payload is None:
            return
        now = time.time()
        entries = [entry for entry in self.payload.get('entries', []) if entry['end'] > now]
        signature = tuple((entry['start'], entry['end'], entry['title'], entry['summary']) for entry in entries)
        if signature == self.signature:
            return
        self.signature = signature
        tree = self.window.live_info_box.live_EPG_info
        def row_key(item):
            return tuple(item.text(column) for column in range(4))
        expanded = {row_key(tree.topLevelItem(index)) for index in range(tree.topLevelItemCount())
                    if tree.topLevelItem(index).isExpanded()}
        scroll = tree.verticalScrollBar().value()
        tree.setUpdatesEnabled(False)
        try:
            tree.clear()
            if not entries:
                tree.addTopLevelItem(QTreeWidgetItem([
                    '--/--/----', '--:--', '--:--', 'No EPG Data Available...']))
            for entry in entries:
                start, end = datetime.fromtimestamp(entry['start']), datetime.fromtimestamp(entry['end'])
                item = QTreeWidgetItem([start.strftime('%d-%m-%Y'), start.strftime('%H:%M'),
                                        end.strftime('%H:%M'), str(entry['title'])])
                tree.addTopLevelItem(item)
                self.window.live_info_box.add_epg_description(item, entry['summary'])
                item.setExpanded(row_key(item) in expanded)
            tree.verticalScrollBar().setValue(scroll)
        finally:
            tree.setUpdatesEnabled(True)
