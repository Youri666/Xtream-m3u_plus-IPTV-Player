"""Information panels for live channels, movies, and series."""

import unicodedata
import math

from PyQt5.QtGui import (
    QFont, QPixmap, QDesktopServices, QTextDocument, QPainter,
    QAbstractTextDocumentLayout, QTextCursor, QTextBlockFormat
)
from PyQt5.QtCore import (
    Qt, QSize, QUrl, QEvent
)
from PyQt5.QtWidgets import (
    QVBoxLayout, QLabel, QPushButton, QWidget, QHBoxLayout, QGridLayout,
    QTreeWidget, QTreeWidgetItem, QScrollArea, QTextBrowser, QFrame, QStyleOptionViewItem,
)


from iptv_player.ui.image_labels import ArtworkLabel
from iptv_player.ui.widgets import CompactListDelegate


def _text_bounds(widget):
    option = QStyleOptionViewItem()
    option.initFrom(widget)
    return CompactListDelegate.reference_bounds(option, widget.logicalDpiY())


def _compact_document_spacing(document, widget):
    """Use the shared font reference, without measuring individual text lines."""
    cursor = QTextCursor(document)
    cursor.select(QTextCursor.Document)
    block_format = QTextBlockFormat()
    block_format.setLineHeight(_text_bounds(widget).height() + 2,
                               QTextBlockFormat.FixedHeight)
    cursor.mergeBlockFormat(block_format)


def _document_text_offset(document, widget):
    """Centre visible glyphs when Qt compresses a font's oversized line box."""
    document.size()  # Complete layout before reading the first baseline.
    layout = document.begin().layout()
    if not layout.lineCount():
        return 0
    line = layout.lineAt(0)
    bounds = _text_bounds(widget)
    target_baseline = 1 - bounds.y()
    return target_baseline - line.position().y() - line.ascent()

def _set_link_available(widget, available):
    """Keep a link icon's enabled state and cursor consistent."""
    widget.setEnabled(available)
    widget.setCursor(Qt.PointingHandCursor if available else Qt.ArrowCursor)


def _trim_epg_description(description):
    """Remove outer whitespace and invisible formatting characters."""
    text = str(description or "")
    while text and (text[0].isspace() or unicodedata.category(text[0]) == "Cf"):
        text = text[1:]
    while text and (text[-1].isspace() or unicodedata.category(text[-1]) == "Cf"):
        text = text[:-1]
    return text


class _DescriptionView(QTextBrowser):
    """Show plain-text metadata in a resizable, independently scrolling area."""

    def __init__(self, text="—"):
        super().__init__()
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setFocusPolicy(Qt.NoFocus)
        self.document().setDocumentMargin(0)
        self.setText(text)

    def setText(self, text):
        """Preserve QLabel-like callers while treating provider text as plain text."""
        self.setPlainText(str(text or ""))

    def setPlainText(self, text):
        super().setPlainText(text)
        self._refresh_spacing()

    def _refresh_spacing(self):
        document = self.document()
        document.setDefaultFont(self.font())
        frame = document.rootFrame()
        frame_format = frame.frameFormat()
        frame_format.setTopMargin(0)
        frame.setFrameFormat(frame_format)
        _compact_document_spacing(document, self)
        # Text browsers need room above the first baseline; otherwise a font
        # with unusually large descent can clip its first line after compression.
        frame_format.setTopMargin(max(0, _document_text_offset(document, self)))
        frame.setFrameFormat(frame_format)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.ApplicationFontChange):
            self._refresh_spacing()

    def text(self):
        """Return plain text for compatibility with the former QLabel."""
        return self.toPlainText()

class _EpgDescriptionLabel(QLabel):
    """Use the same plain-text layout for measurement and painting."""

    def _text_document(self, width):
        document = QTextDocument()
        document.setDocumentMargin(0)
        document.setDefaultFont(self.font())
        document.setPlainText(self.text())
        margins = self.contentsMargins()
        document.setTextWidth(max(1, width - margins.left() - margins.right()))
        _compact_document_spacing(document, self)
        return document

    def heightForWidth(self, width):
        margins = self.contentsMargins()
        return (
            math.ceil(self._text_document(width).size().height())
            + margins.top() + margins.bottom()
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        margins = self.contentsMargins()
        painter.translate(margins.left(), margins.top())
        context = QAbstractTextDocumentLayout.PaintContext()
        context.palette = self.palette()
        document = self._text_document(self.width())
        painter.translate(0, _document_text_offset(document, self))
        document.documentLayout().draw(painter, context)
        painter.end()

    def sizeHint(self):
        # QTreeView also consults embedded widgets' size hints and takes the
        # maximum. QLabel's preferred-width hint can add unwanted wrapped lines.
        return QSize(0, 0)

    def minimumSizeHint(self):
        return QSize(0, 0)


class _CompactInfoLabel(_EpgDescriptionLabel):
    """Keep metadata wrapping compact without forcing a minimum text width."""

    def sizeHint(self):
        return QSize(0, self.heightForWidth(400))

    def minimumSizeHint(self):
        return QSize(0, _text_bounds(self).height() + 2)


class _EpgDescriptionDelegate(CompactListDelegate):
    """Share compact programme rows while sizing wrapped descriptions separately."""

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        tree = self.parent()
        item = tree.itemFromIndex(index)
        label = tree.itemWidget(item, 0) if item is not None else None
        if isinstance(label, QLabel) and item.isFirstColumnSpanned():
            depth = 0
            ancestor = item
            while ancestor is not None:
                depth += 1
                ancestor = ancestor.parent()
            if not tree.rootIsDecorated():
                depth -= 1
            # Spanned item widgets cover the full header, including columns
            # extending beyond the viewport when horizontal scrolling is needed.
            row_width = max(tree.viewport().width(), tree.header().length())
            width = max(1, row_width - depth * tree.indentation())
            size.setHeight(label.heightForWidth(width))
        return size


class _EpgTree(QTreeWidget):
    """Recalculate wrapped description rows when the viewport width changes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setExpandsOnDoubleClick(False)
        self.itemClicked.connect(self._toggle_program)

    @staticmethod
    def _toggle_program(item, column):
        """Toggle program rows while leaving native branch-arrow clicks alone."""
        if item.parent() is None and item.childCount():
            item.setExpanded(not item.isExpanded())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.doItemsLayout()


class LiveInfoBox(QWidget):
    def __init__(self, parent=None):
        super().__init__()

        self.parent = parent
        # Paint the panel with the application Window colour, matching the
        # Movie and Series information containers in every theme.
        self.setAutoFillBackground(True)

        #Create LIVE TV info box layout
        self.live_EPG_info_box_layout = QVBoxLayout(self)

        #Create Live TV Channel name label
        self.EPG_box_label = QLabel("Select channel to view Live TV info")
        self.EPG_box_label.setFont(QFont('Segoe UI', 14, QFont.Bold))

        #Enable wordwrap for TV channel name
        self.EPG_box_label.setWordWrap(True)

        self.maxCoverHeight = 200

        #Create cover image
        self.cover          = ArtworkLabel()
        self.cover_img      = QPixmap(self.parent.path_to_no_img)
        self.cover.setAlignment(Qt.AlignTop)
        self.cover.set_artwork(self.cover_img, width=self.maxCoverHeight)
        self.cover.setMaximumHeight(self.maxCoverHeight)

        #Create entry info window
        self.live_EPG_info = _EpgTree()
        self.live_EPG_info.setItemDelegate(
            _EpgDescriptionDelegate(self.live_EPG_info)
        )
        self.live_EPG_info.setColumnCount(4)
        self.live_EPG_info.setHeaderLabels(["Date", "From", "To", "Name"])

        #Set column widths of EPG info window
        self.live_EPG_info.setColumnWidth(0, 120)
        self.live_EPG_info.setColumnWidth(1, 50)
        self.live_EPG_info.setColumnWidth(2, 50)

        #Create stream status indicator
        self.stream_status = ArtworkLabel()
        self.stream_status_img = self.parent.status_pixmap(
            self.parent.path_to_unknown_status_icon, 24
        )
        self.stream_status.setPixmap(self.stream_status_img)
        self.stream_status.setFixedWidth(25)

        #Create favorites button — wider + larger icon so it sits clearly next
        #to the channel name/logo and isn't clipped (issue #17).
        self.fav_button = QPushButton("")
        self.fav_button.setStyleSheet("text-align: left; padding: 2px;")
        self.fav_button.setFixedSize(32, 32)
        self.fav_button.setIconSize(QSize(24, 24))
        self.fav_button.setFlat(True)
        self.fav_button.setToolTip("Toggle favorite")
        self.fav_button.setIcon(self.parent.favorites_icon)
        self.fav_button.setEnabled(False)
        self.fav_button.clicked.connect(lambda: self.parent.favorite_button_pressed("LIVE", self))

        #Create title layout with favorites button
        self.title_layout = QHBoxLayout()
        self.title_layout.addWidget(self.fav_button)
        self.title_layout.addWidget(self.stream_status)
        self.title_layout.addWidget(self.EPG_box_label)

        #Add TV channel label and EPG data to info box
        self.live_EPG_info_box_layout.addLayout(self.title_layout)
        self.live_EPG_info_box_layout.addWidget(self.cover)
        self.live_EPG_info_box_layout.addWidget(self.live_EPG_info)

    def set_favorite(self, is_fav):
        """Update the favorite button to reflect the selected entry."""
        if is_fav:
            #If favorite, set coloured icon
            self.fav_button.setIcon(self.parent.favorites_icon_colour)
        else:
            #If not favorite, set normal icon
            self.fav_button.setIcon(self.parent.favorites_icon)

    def add_epg_description(self, program_item, description):
        """Add an expanded EPG description spanning the complete table width."""
        cleaned_description = _trim_epg_description(description)
        if not cleaned_description:
            return None
        label = _EpgDescriptionLabel(cleaned_description)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        label.setContentsMargins(4, 0, 4, 4)
        description_item = QTreeWidgetItem()
        program_item.addChild(description_item)
        # Qt retains the spanning flag only after the child is attached.
        description_item.setFirstColumnSpanned(True)
        self.live_EPG_info.setItemWidget(description_item, 0, label)
        return description_item

    def reset(self):
        """Clear stale channel details until another channel is selected."""
        self.EPG_box_label.setText("Select channel to view Live TV info")
        self.cover.set_artwork(self.cover_img, width=self.maxCoverHeight)
        self.live_EPG_info.clear()
        self.stream_status.setPixmap(
            self.parent.status_pixmap(self.parent.path_to_unknown_status_icon, 24)
        )
        self.set_favorite(False)
        self.fav_button.setEnabled(False)

class MovieInfoBox(QScrollArea):
    def __init__(self, parent=None):
        super().__init__()

        self.parent = parent

        self.yt_code    = None
        self.tmdb_code  = None

        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignTop)

        self.widget = QWidget()

        self.layout = QGridLayout(self.widget)
        self.layout.setColumnStretch(1, 1)
        self.layout.setRowStretch(3, 1)

        self.maxCoverWidth = 200

        #Create cover image
        self.cover          = ArtworkLabel()
        self.cover_img      = QPixmap(self.parent.path_to_no_img)
        self.cover.setAlignment(Qt.AlignTop)
        self.cover.set_artwork(self.cover_img, width=self.maxCoverWidth)
        self.cover.setFixedWidth(self.maxCoverWidth)

        #Create favorites button — wider + larger icon (issue #17).
        self.fav_button = QPushButton("")
        self.fav_button.setStyleSheet("padding: 2px;")
        self.fav_button.setFixedSize(32, 32)
        self.fav_button.setIconSize(QSize(24, 24))
        self.fav_button.setFlat(True)
        self.fav_button.setToolTip("Toggle favorite")
        self.fav_button.setIcon(self.parent.favorites_icon)
        self.fav_button.setEnabled(False)
        self.fav_button.clicked.connect(lambda: self.parent.favorite_button_pressed("Movies", self))

        #Create information labels
        self.name           = QLabel("No movie selected...")
        self.release_date   = _CompactInfoLabel("Release date: —")
        self.country        = _CompactInfoLabel("Country: —")
        self.genre          = _CompactInfoLabel("Genre: —")
        self.duration       = _CompactInfoLabel("Duration: —")
        self.rating         = _CompactInfoLabel("Rating: —")
        self.director       = _CompactInfoLabel("Director: —")
        self.cast           = _CompactInfoLabel("Cast: —")
        self.description_title = _CompactInfoLabel("Description:")
        self.description    = _DescriptionView("—")

        self.trailer = ArtworkLabel()
        self.trailer.setAlignment(Qt.AlignLeft)
        self.trailer.setFixedWidth(50)
        _set_link_available(self.trailer, False)

        self.tmdb = ArtworkLabel()
        self.tmdb.setAlignment(Qt.AlignLeft)
        self.tmdb.setFixedWidth(50)
        _set_link_available(self.tmdb, False)

        #Set YouTube icon
        self.yt_img = QPixmap(self.parent.path_to_yt_img)
        self.trailer.set_artwork(self.yt_img, height=30)

        #Set TMDB icon
        self.tmdb_img = QPixmap(self.parent.path_to_tmdb_img)
        self.tmdb.set_artwork_file(self.parent.path_to_tmdb_img, height=30)

        self.trailer.mousePressEvent = self.open_trailer
        self.tmdb.mousePressEvent = self.open_tmdb_page

        self.name.setFont(QFont('Segoe UI', 14, QFont.Bold))

        self.name.setWordWrap(True)
        self.release_date.setWordWrap(True)
        self.country.setWordWrap(True)
        self.genre.setWordWrap(True)
        self.duration.setWordWrap(True)
        self.rating.setWordWrap(True)
        self.director.setWordWrap(True)
        self.cast.setWordWrap(True)

        #Create layout with title and favorite button
        self.title_layout = QHBoxLayout()
        self.title_layout.addWidget(self.fav_button)
        self.title_layout.addWidget(self.name)

        #Create layout with YouTube and TMDB icon next to each other
        self.links_layout = QHBoxLayout()
        self.links_layout.addWidget(self.trailer)
        self.links_layout.addWidget(self.tmdb)
        self.links_layout.addStretch(1)

        #Add widgets
        self.layout.addLayout(self.title_layout,    0, 0, 1, 2)
        self.layout.addWidget(self.cover,           1, 0)
        # Keep metadata together instead of distributing rows across the poster height.
        self.metadata_layout = QVBoxLayout()
        self.metadata_layout.addLayout(self.links_layout)
        self.metadata_layout.addWidget(self.release_date)
        self.metadata_layout.addWidget(self.country)
        self.metadata_layout.addWidget(self.genre)
        self.metadata_layout.addWidget(self.duration)
        self.metadata_layout.addWidget(self.rating)
        self.metadata_layout.addWidget(self.director)
        self.metadata_layout.addWidget(self.cast)
        self.metadata_layout.addStretch(1)
        self.layout.addLayout(self.metadata_layout, 1, 1)
        self.layout.addWidget(self.description_title, 2, 0, 1, 2)
        self.layout.addWidget(self.description,       3, 0, 1, 2)

        self.setWidget(self.widget)

    def open_trailer(self, event):
        """Open the selected movie trailer in the default browser."""
        #Get youtube code from text and append to url
        yt_url = f"https://www.youtube.com/watch?v={self.yt_code}"

        #Open URL
        QDesktopServices.openUrl(QUrl(yt_url))

    def open_tmdb_page(self, event):
        """Open the selected movie page on TMDB."""
        #Get TMDB code from text and append to url
        tmdb_url = f"https://www.themoviedb.org/movie/{self.tmdb_code}"

        #Open URL
        QDesktopServices.openUrl(QUrl(tmdb_url))

    def set_favorite(self, is_fav):
        """Update the favorite button to reflect the selected movie."""
        if is_fav:
            #If favorite, set coloured icon
            self.fav_button.setIcon(self.parent.favorites_icon_colour)
        else:
            #If not favorite, set normal icon
            self.fav_button.setIcon(self.parent.favorites_icon)

    def set_trailer_available(self, available):
        """Show whether the YouTube icon currently opens a valid link."""
        _set_link_available(self.trailer, available)

    def set_tmdb_available(self, available):
        """Show whether the TMDB icon currently opens a valid link."""
        _set_link_available(self.tmdb, available)

    def reset(self):
        """Clear stale movie details until another movie is selected."""
        self.name.setText("No movie selected...")
        self.release_date.setText("Release date: —")
        self.country.setText("Country: —")
        self.genre.setText("Genre: —")
        self.duration.setText("Duration: —")
        self.rating.setText("Rating: —")
        self.director.setText("Director: —")
        self.cast.setText("Cast: —")
        self.description.setText("—")
        self.cover.set_artwork(self.cover_img, width=self.maxCoverWidth)
        self.yt_code = None
        self.tmdb_code = None
        self.set_trailer_available(False)
        self.set_tmdb_available(False)
        self.set_favorite(False)
        self.fav_button.setEnabled(False)

class SeriesInfoBox(QScrollArea):
    def __init__(self, parent=None):
        super().__init__()

        self.parent = parent

        self.yt_code    = None
        self.tmdb_code  = None

        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignTop)

        self.widget = QWidget()

        self.layout = QGridLayout(self.widget)
        self.layout.setColumnStretch(1, 1)
        self.layout.setRowStretch(3, 1)

        self.maxCoverWidth = 200

        #Create cover image
        self.cover          = ArtworkLabel()
        self.cover_img      = QPixmap(self.parent.path_to_no_img)
        self.cover.setAlignment(Qt.AlignTop)
        self.cover.set_artwork(self.cover_img, width=self.maxCoverWidth)
        self.cover.setFixedWidth(self.maxCoverWidth)

        #Create favorites button — wider + larger icon (issue #17).
        self.fav_button = QPushButton("")
        self.fav_button.setStyleSheet("padding: 2px;")
        self.fav_button.setFixedSize(32, 32)
        self.fav_button.setIconSize(QSize(24, 24))
        self.fav_button.setFlat(True)
        self.fav_button.setToolTip("Toggle favorite")
        self.fav_button.setIcon(self.parent.favorites_icon)
        self.fav_button.setEnabled(False)
        self.fav_button.clicked.connect(lambda: self.parent.favorite_button_pressed("Series", self))

        #Create information labels
        self.name           = QLabel("No series selected...")
        self.release_date   = _CompactInfoLabel("Release date: —")
        self.genre          = _CompactInfoLabel("Genre: —")
        self.num_seasons    = _CompactInfoLabel("Seasons: —")
        self.duration       = _CompactInfoLabel("Episode duration: —")
        self.rating         = _CompactInfoLabel("Rating: —")
        self.director       = _CompactInfoLabel("Director: —")
        self.cast           = _CompactInfoLabel("Cast: —")
        self.description_title = _CompactInfoLabel("Description:")
        self.description    = _DescriptionView("—")

        self.trailer = ArtworkLabel()
        self.trailer.setAlignment(Qt.AlignLeft)
        self.trailer.setFixedWidth(50)
        _set_link_available(self.trailer, False)

        self.tmdb = ArtworkLabel()
        self.tmdb.setAlignment(Qt.AlignLeft)
        self.tmdb.setFixedWidth(50)
        _set_link_available(self.tmdb, False)

        #Set YouTube icon
        self.yt_img = QPixmap(self.parent.path_to_yt_img)
        self.trailer.set_artwork(self.yt_img, height=30)

        #Set TMDB icon
        self.tmdb_img = QPixmap(self.parent.path_to_tmdb_img)
        self.tmdb.set_artwork_file(self.parent.path_to_tmdb_img, height=30)

        self.trailer.mousePressEvent = self.open_trailer
        self.tmdb.mousePressEvent = self.open_tmdb_page

        self.name.setFont(QFont('Segoe UI', 14, QFont.Bold))

        #Enable wordwrap for all labels
        self.name.setWordWrap(True)
        self.release_date.setWordWrap(True)
        self.genre.setWordWrap(True)
        self.num_seasons.setWordWrap(True)
        self.duration.setWordWrap(True)
        self.rating.setWordWrap(True)
        self.director.setWordWrap(True)
        self.cast.setWordWrap(True)

        #Create layout with title and favorite button
        self.title_layout = QHBoxLayout()
        self.title_layout.addWidget(self.fav_button)
        self.title_layout.addWidget(self.name)

        #Create layout with YouTube and TMDB icon next to each other
        self.links_layout = QHBoxLayout()
        self.links_layout.addWidget(self.trailer)
        self.links_layout.addWidget(self.tmdb)
        self.links_layout.addStretch(1)

        #Add widgets
        self.layout.addLayout(self.title_layout,    0, 0, 1, 2)
        self.layout.addWidget(self.cover,           1, 0)
        # Keep metadata together instead of distributing rows across the poster height.
        self.metadata_layout = QVBoxLayout()
        self.metadata_layout.addLayout(self.links_layout)
        self.metadata_layout.addWidget(self.release_date)
        self.metadata_layout.addWidget(self.genre)
        self.metadata_layout.addWidget(self.num_seasons)
        self.metadata_layout.addWidget(self.duration)
        self.metadata_layout.addWidget(self.rating)
        self.metadata_layout.addWidget(self.director)
        self.metadata_layout.addWidget(self.cast)
        self.metadata_layout.addStretch(1)
        self.layout.addLayout(self.metadata_layout, 1, 1)
        self.layout.addWidget(self.description_title, 2, 0, 1, 2)
        self.layout.addWidget(self.description,       3, 0, 1, 2)

        #Add widget with all items to the scrollarea (self)
        self.setWidget(self.widget)

    def open_trailer(self, event):
        """Open the selected series trailer in the default browser."""
        #Get youtube code from text and append to url
        yt_url = f"https://www.youtube.com/watch?v={self.yt_code}"

        #Open URL
        QDesktopServices.openUrl(QUrl(yt_url))

    def open_tmdb_page(self, event):
        """Open the selected series page on TMDB."""
        #Get TMDB code from text and append to url
        tmdb_url = f"https://www.themoviedb.org/tv/{self.tmdb_code}"

        #Open URL
        QDesktopServices.openUrl(QUrl(tmdb_url))

    def set_favorite(self, is_fav):
        """Update the favorite button to reflect the selected series."""
        if is_fav:
            #If favorite, set coloured icon
            self.fav_button.setIcon(self.parent.favorites_icon_colour)
        else:
            #If not favorite, set normal icon
            self.fav_button.setIcon(self.parent.favorites_icon)

    def set_trailer_available(self, available):
        """Show whether the YouTube icon currently opens a valid link."""
        _set_link_available(self.trailer, available)

    def set_tmdb_available(self, available):
        """Show whether the TMDB icon currently opens a valid link."""
        _set_link_available(self.tmdb, available)

    def reset(self):
        """Clear stale series details until another series is selected."""
        self.name.setText("No series selected...")
        self.release_date.setText("Release date: —")
        self.genre.setText("Genre: —")
        self.num_seasons.setText("Seasons: —")
        self.duration.setText("Episode duration: —")
        self.rating.setText("Rating: —")
        self.director.setText("Director: —")
        self.cast.setText("Cast: —")
        self.description.setText("—")
        self.cover.set_artwork(self.cover_img, width=self.maxCoverWidth)
        self.yt_code = None
        self.tmdb_code = None
        self.set_trailer_available(False)
        self.set_tmdb_available(False)
        self.set_favorite(False)
        self.fav_button.setEnabled(False)
