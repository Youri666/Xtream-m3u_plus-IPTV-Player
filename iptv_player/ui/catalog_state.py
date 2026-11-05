"""Preserve current browsing context while replacing a provider catalogue."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QListWidgetItem


def _identity(item):
    if item is None:
        return None
    data = item.data(Qt.UserRole)
    if isinstance(data, dict):
        for field in ("stream_id", "id", "series_id", "category_id"):
            if data.get(field) is not None:
                return field, str(data[field])
    return "text", item.text()


def capture_catalog_view(window):
    """Capture identities, filters and scroll positions without retaining Qt items."""
    state = {"lists": {}, "series_level": window.series_navigation_level}
    for kind in window.category_list_widgets:
        categories = window.category_list_widgets[kind]
        streams = window.streaming_list_widgets[kind]
        state["lists"][kind] = dict(category=_identity(categories.currentItem()),
            stream=_identity(streams.currentItem()),
            category_search=window.category_search_bars[kind].text(),
            stream_search=window.streaming_search_bars[kind].text(),
            category_scroll=categories.verticalScrollBar().value(),
            stream_scroll=streams.verticalScrollBar().value())
    if state["series_level"]:
        series_list = window.streaming_list_widgets['Series']
        state['series_entry'] = window.current_series_entry
        state['series_season'] = getattr(window, 'current_series_season', '')
        state['series_sources'] = {key: window.currently_loaded_streams.get(key) for key in ('Seasons', 'Episodes')}
        state['series_id'] = str((window.current_series_entry or {}).get('series_id', ''))
        state['series_rows'] = [(series_list.item(row).text(), series_list.item(row).data(Qt.UserRole))
                                for row in range(series_list.count())]
    return state


def restore_catalog_view(window, state):
    """Restore available selections without activating playback or changing tabs."""
    for kind, saved in state['lists'].items():
        if not window.content_enabled[kind]:
            continue
        categories = window.category_list_widgets[kind]
        streams = window.streaming_list_widgets[kind]
        bar = window.category_search_bars[kind]
        bar.setText(saved['category_search'])
        bar.textChanged.emit(bar.text())
        for row in range(categories.count()):
            item = categories.item(row)
            if _identity(item) == saved['category']:
                categories.setCurrentItem(item)
                categories.itemClicked.emit(item)
                break
        if kind == 'Series' and state['series_level']:
            if any(str(entry.get('series_id', '')) == state['series_id']
                   for entry in window.entries_per_stream_type.get('Series', [])):
                # Retain the already opened season/episode view; it is independent
                # of root catalogue rows and will be fetched normally on reopening.
                window.series_navigation_level = state['series_level']
                window.current_series_entry = state['series_entry']
                window.current_series_season = state['series_season']
                window.currently_loaded_streams.update(state['series_sources'])
                streams.clear()
                for text, data in state['series_rows']:
                    item = QListWidgetItem(text)
                    item.setData(Qt.UserRole, data)
                    streams.addItem(item)
        bar = window.streaming_search_bars[kind]
        bar.setText(saved['stream_search'])
        bar.textChanged.emit(bar.text())
        for row in range(streams.count()):
            item = streams.item(row)
            if _identity(item) == saved['stream']:
                streams.setCurrentItem(item)
                break
        categories.verticalScrollBar().setValue(saved['category_scroll'])
        streams.verticalScrollBar().setValue(saved['stream_scroll'])
