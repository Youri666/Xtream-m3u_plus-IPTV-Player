"""Information panels for live channels, movies, and series."""

import unicodedata

from PyQt5.QtGui import (
    QFont, QPixmap, QDesktopServices
)
from PyQt5.QtCore import (
    Qt, QSize, QUrl
)
from PyQt5.QtWidgets import (
    QVBoxLayout, QLabel, QPushButton, QWidget, QHBoxLayout, QGridLayout,
    QTreeWidget, QTreeWidgetItem, QScrollArea
)


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

class LiveInfoBox(QWidget):
    def __init__(self, parent=None):
        super().__init__()

        self.parent = parent

        #Create LIVE TV info box layout
        self.live_EPG_info_box_layout = QVBoxLayout(self)

        #Create Live TV Channel name label
        self.EPG_box_label = QLabel("Select channel to view Live TV info")
        self.EPG_box_label.setFont(QFont('Segoe UI', 14, QFont.Bold))

        #Enable wordwrap for TV channel name
        self.EPG_box_label.setWordWrap(True)

        self.maxCoverHeight = 200

        #Create cover image
        self.cover          = QLabel()
        self.cover_img      = QPixmap(self.parent.path_to_no_img)
        self.cover.setAlignment(Qt.AlignTop)
        self.cover.setPixmap(self.cover_img.scaledToHeight(self.maxCoverHeight))
        self.cover.setMaximumHeight(self.maxCoverHeight)

        #Create entry info window
        self.live_EPG_info = QTreeWidget()
        self.live_EPG_info.setColumnCount(4)
        self.live_EPG_info.setHeaderLabels(["Date", "From", "To", "Name"])

        #Set column widths of EPG info window
        self.live_EPG_info.setColumnWidth(0, 120)
        self.live_EPG_info.setColumnWidth(1, 50)
        self.live_EPG_info.setColumnWidth(2, 50)

        #Create stream status indicator
        self.stream_status = QLabel()
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
        label = QLabel(cleaned_description)
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
        self.cover.setPixmap(self.cover_img.scaledToHeight(self.maxCoverHeight))
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

        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignTop)

        self.widget = QWidget()

        self.layout = QGridLayout(self.widget)
        self.layout.setAlignment(Qt.AlignTop)
        self.layout.setColumnStretch(1, 1)

        self.maxCoverWidth = 200

        #Create cover image
        self.cover          = QLabel()
        self.cover_img      = QPixmap(self.parent.path_to_no_img)
        self.cover.setAlignment(Qt.AlignTop)
        self.cover.setPixmap(self.cover_img.scaledToWidth(self.maxCoverWidth))
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
        self.release_date   = QLabel("Release date: —")
        self.country        = QLabel("Country: —")
        self.genre          = QLabel("Genre: —")
        self.duration       = QLabel("Duration: —")
        self.rating         = QLabel("Rating: —")
        self.director       = QLabel("Director: —")
        self.cast           = QLabel("Cast: —")
        self.description_title = QLabel("Description:")
        self.description    = QLabel("—")

        self.trailer = QLabel()
        self.trailer.setAlignment(Qt.AlignLeft)
        self.trailer.setFixedWidth(50)
        _set_link_available(self.trailer, False)

        self.tmdb = QLabel()
        self.tmdb.setAlignment(Qt.AlignLeft)
        self.tmdb.setFixedWidth(50)
        _set_link_available(self.tmdb, False)

        #Set YouTube icon
        self.yt_img = QPixmap(self.parent.path_to_yt_img)
        self.trailer.setPixmap(self.yt_img.scaledToHeight(30))

        #Set TMDB icon
        self.tmdb_img = QPixmap(self.parent.path_to_tmdb_img)
        self.tmdb.setPixmap(self.tmdb_img.scaledToHeight(30))

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
        self.description.setWordWrap(True)

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
        self.layout.addWidget(self.cover,           1, 0, 8, 1)
        self.layout.addLayout(self.links_layout,    1, 1)
        self.layout.addWidget(self.release_date,    2, 1)
        self.layout.addWidget(self.country,         3, 1)
        self.layout.addWidget(self.genre,           4, 1)
        self.layout.addWidget(self.duration,        5, 1)
        self.layout.addWidget(self.rating,          6, 1)
        self.layout.addWidget(self.director,        7, 1)
        self.layout.addWidget(self.cast,            8, 1)
        self.layout.addWidget(self.description_title, 9, 0, 1, 2)
        self.layout.addWidget(self.description,    10, 0, 1, 2)

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
        self.cover.setPixmap(self.cover_img.scaledToWidth(self.maxCoverWidth))
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

        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignTop)

        self.widget = QWidget()

        self.layout = QGridLayout(self.widget)
        self.layout.setAlignment(Qt.AlignTop)
        self.layout.setColumnStretch(1, 1)

        self.maxCoverWidth = 200

        #Create cover image
        self.cover          = QLabel()
        self.cover_img      = QPixmap(self.parent.path_to_no_img)
        self.cover.setAlignment(Qt.AlignTop)
        self.cover.setPixmap(self.cover_img.scaledToWidth(self.maxCoverWidth))
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
        self.release_date   = QLabel("Release date: —")
        self.genre          = QLabel("Genre: —")
        self.num_seasons    = QLabel("Seasons: —")
        self.duration       = QLabel("Episode duration: —")
        self.rating         = QLabel("Rating: —")
        self.director       = QLabel("Director: —")
        self.cast           = QLabel("Cast: —")
        self.description_title = QLabel("Description:")
        self.description    = QLabel("—")

        self.trailer = QLabel()
        self.trailer.setAlignment(Qt.AlignLeft)
        self.trailer.setFixedWidth(50)
        _set_link_available(self.trailer, False)

        self.tmdb = QLabel()
        self.tmdb.setAlignment(Qt.AlignLeft)
        self.tmdb.setFixedWidth(50)
        _set_link_available(self.tmdb, False)

        #Set YouTube icon
        self.yt_img = QPixmap(self.parent.path_to_yt_img)
        self.trailer.setPixmap(self.yt_img.scaledToHeight(30))

        #Set TMDB icon
        self.tmdb_img = QPixmap(self.parent.path_to_tmdb_img)
        self.tmdb.setPixmap(self.tmdb_img.scaledToHeight(30))

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
        self.description.setWordWrap(True)

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
        self.layout.addWidget(self.cover,           1, 0, 8, 1)
        self.layout.addLayout(self.links_layout,    1, 1)
        self.layout.addWidget(self.release_date,    2, 1)
        self.layout.addWidget(self.genre,           3, 1)
        self.layout.addWidget(self.num_seasons,     4, 1)
        self.layout.addWidget(self.duration,        5, 1)
        self.layout.addWidget(self.rating,          6, 1)
        self.layout.addWidget(self.director,        7, 1)
        self.layout.addWidget(self.cast,            8, 1)
        self.layout.addWidget(self.description_title, 9, 0, 1, 2)
        self.layout.addWidget(self.description,    10, 0, 1, 2)

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
        self.cover.setPixmap(self.cover_img.scaledToWidth(self.maxCoverWidth))
        self.yt_code = None
        self.tmdb_code = None
        self.set_trailer_available(False)
        self.set_tmdb_available(False)
        self.set_favorite(False)
        self.fav_button.setEnabled(False)
