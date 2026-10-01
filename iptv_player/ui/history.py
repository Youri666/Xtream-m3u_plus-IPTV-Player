"""Present episode history as series groups without changing saved entries."""

from PyQt5.QtCore import Qt, QSignalBlocker, pyqtSignal
from PyQt5.QtWidgets import QTreeWidget, QTreeWidgetItem


GROUP_ROLE = Qt.UserRole + 1


class HistoryTreeWidget(QTreeWidget):
    """Open history on double-click or Enter regardless of desktop activation policy."""

    openRequested = pyqtSignal(QTreeWidgetItem, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setExpandsOnDoubleClick(False)
        self.itemDoubleClicked.connect(self.openRequested.emit)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.currentItem() is not None:
            self.openRequested.emit(self.currentItem(), self.currentColumn())
            event.accept()
            return
        super().keyPressEvent(event)


def _item_identity(item):
    group = item.data(0, GROUP_ROLE)
    if group is not None:
        return ('series', str(group))
    entry = item.data(0, Qt.UserRole)
    return ('entry', entry.get('key')) if isinstance(entry, dict) else None


def populate_history_tree(tree, entries, display_time, group_series=False, preserve_state=True):
    """Rebuild rows in recency order and retain surviving selection and expansion."""
    expanded = set()
    selected = set()
    current = _item_identity(tree.currentItem()) if tree.currentItem() else None
    scroll = tree.verticalScrollBar().value()
    if preserve_state:
        for row in range(tree.topLevelItemCount()):
            parent = tree.topLevelItem(row)
            if parent.isExpanded():
                expanded.add(_item_identity(parent))
        selected = {_item_identity(item) for item in tree.selectedItems()}
    else:
        current, scroll = None, 0

    blocker = QSignalBlocker(tree)
    tree.setUpdatesEnabled(False)
    try:
        tree.clear()
        groups = {}
        rows = []
        for entry in entries:
            timestamp = display_time(entry.get('last_viewed', ''))
            item = QTreeWidgetItem((timestamp, entry.get('title', '')))
            item.setData(0, Qt.UserRole, entry)
            series_id = entry.get('series_id') if group_series else None
            if series_id:
                series_id = str(series_id)
                parent = groups.get(series_id)
                if parent is None:
                    parent = QTreeWidgetItem((timestamp, entry.get('series_title') or entry.get('title', '')))
                    # The group activates the newest retained episode through the existing handler.
                    parent.setData(0, Qt.UserRole, entry)
                    parent.setData(0, GROUP_ROLE, series_id)
                    tree.addTopLevelItem(parent)
                    groups[series_id] = parent
                    rows.append(parent)
                parent.addChild(item)
            else:
                tree.addTopLevelItem(item)
            rows.append(item)

        current_item = None
        for item in rows:
            identity = _item_identity(item)
            if identity in expanded:
                item.setExpanded(True)
            if identity == current:
                current_item = item
        if current_item is not None:
            tree.setCurrentItem(current_item)
        for item in rows:
            item.setSelected(_item_identity(item) in selected)
        tree.doItemsLayout()
        tree.verticalScrollBar().setValue(scroll)
    finally:
        tree.setUpdatesEnabled(True)
        del blocker


def selected_history_entries(items):
    """Expand selected groups into their retained episodes, deduplicating overlaps."""
    entries = {}
    for item in items:
        targets = ([item.child(row) for row in range(item.childCount())]
                   if item.data(0, GROUP_ROLE) is not None else [item])
        for target in targets:
            entry = target.data(0, Qt.UserRole)
            if isinstance(entry, dict) and entry.get('key'):
                entries[entry['key']] = entry
    return list(entries.values())
