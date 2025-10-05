from PyQt5.QtGui import QIcon, QFont, QImage, QPixmap, QColor, QDesktopServices
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
    QTreeWidget, QTreeWidgetItem, QTreeView, QScrollArea
)

from os import path
import configparser
import json

class LiveInfoBox(QWidget):
    def __init__(self, parent=None):
        super().__init__()

        self.parent = parent

        #Create LIVE TV info box layout
        self.live_EPG_info_box_layout = QVBoxLayout(self)

        #Create Live TV Channel name label
        self.EPG_box_label = QLabel("Select channel to view Live TV info")
        self.EPG_box_label.setFont(QFont('Arial', 14, QFont.Bold))

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
        self.live_EPG_info.setColumnCount(2)
        self.live_EPG_info.setHeaderLabels(["Date", "From", "To", "Name"])

        #Set column widths of EPG info window
        self.live_EPG_info.setColumnWidth(0, 120)
        self.live_EPG_info.setColumnWidth(1, 50)
        self.live_EPG_info.setColumnWidth(2, 50)

        #Create stream status indicator
        self.stream_status = QLabel()
        self.stream_status_img = QPixmap(self.parent.path_to_unknown_status_icon)
        self.stream_status.setPixmap(self.stream_status_img.scaledToWidth(24))
        self.stream_status.setFixedWidth(25)

        #Create favorites button
        self.fav_button = QPushButton("")
        self.fav_button.setStyleSheet("text-align: left")
        self.fav_button.setFixedWidth(25)
        self.fav_button.setFlat(True)
        self.fav_button.setIcon(self.parent.favorites_icon)
        self.fav_button.clicked.connect(lambda: self.parent.favButtonPressed("LIVE", self))

        #Create catch-up icon label
        self.catchup_icon_label = QLabel()
        catchup_pixmap = self.parent.catchup_icon.pixmap(QSize(24, 24))
        self.catchup_icon_label.setPixmap(catchup_pixmap)
        self.catchup_icon_label.setFixedWidth(25)
        self.catchup_icon_label.setVisible(False)
        
        #Create title layout with favorites button
        self.title_layout = QHBoxLayout()
        self.title_layout.addWidget(self.fav_button)
        self.title_layout.addWidget(self.stream_status)
        self.title_layout.addWidget(self.EPG_box_label)
        self.title_layout.addWidget(self.catchup_icon_label)

        #Add TV channel label and EPG data to info box
        self.live_EPG_info_box_layout.addLayout(self.title_layout)
        self.live_EPG_info_box_layout.addWidget(self.cover)
        self.live_EPG_info_box_layout.addWidget(self.live_EPG_info)

    def setCatchupIconVisible(self, visible: bool) -> None:
        self.catchup_icon_label.setVisible(visible)

    def setFavorite(self, is_fav):
        if is_fav:
            #If favorite, set coloured icon
            self.fav_button.setIcon(self.parent.favorites_icon_colour)
        else:
            #If not favorite, set normal icon
            self.fav_button.setIcon(self.parent.favorites_icon)

class MovieInfoBox(QScrollArea):
    def __init__(self, parent=None):
        super().__init__()

        self.parent = parent

        self.yt_code    = None
        self.tmdb_code  = None

        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignTop)

        self.widget = QWidget()

        self.layout = QGridLayout(self.widget)
        self.layout.setAlignment(Qt.AlignTop)

        self.maxCoverWidth = 200

        #Create cover image
        self.cover          = QLabel()
        self.cover_img      = QPixmap(self.parent.path_to_no_img)
        self.cover.setAlignment(Qt.AlignTop)
        self.cover.setPixmap(self.cover_img.scaledToWidth(self.maxCoverWidth))
        self.cover.setFixedWidth(self.maxCoverWidth)

        #Create favorites button
        self.fav_button = QPushButton("")
        self.fav_button.setFixedWidth(25)
        self.fav_button.setFlat(True)
        self.fav_button.setIcon(self.parent.favorites_icon)
        self.fav_button.clicked.connect(lambda: self.parent.favButtonPressed("Movies", self))

        #Create information labels
        self.name           = QLabel("No movie selected...")
        self.release_date   = QLabel("Release date: ??-??-????")
        self.country        = QLabel("Country: ?")
        self.genre          = QLabel("Genre: ?")
        self.duration       = QLabel("Duration: ??:??:??")
        self.rating         = QLabel("Rating: ?")
        self.director       = QLabel("Director: ?")
        self.cast           = QLabel("Cast: ?")
        self.description    = QLabel("Description: ?")

        self.trailer = QLabel()
        self.trailer.setAlignment(Qt.AlignLeft)
        self.trailer.setFixedWidth(50)
        self.trailer.setEnabled(False)

        self.tmdb = QLabel()
        self.tmdb.setAlignment(Qt.AlignLeft)
        self.tmdb.setFixedWidth(50)
        self.tmdb.setEnabled(False)

        #Set YouTube icon
        self.yt_img = QPixmap(self.parent.path_to_yt_img)
        self.trailer.setPixmap(self.yt_img.scaledToHeight(30))

        #Set TMDB icon
        self.tmdb_img = QPixmap(self.parent.path_to_tmdb_img)
        self.tmdb.setPixmap(self.tmdb_img.scaledToHeight(30))

        self.trailer.mousePressEvent    = self.TrailerClicked
        self.tmdb.mousePressEvent       = self.TmdbClicked

        self.name.setFont(QFont('Arial', 14, QFont.Bold))

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
        self.layout.addWidget(self.cover,           1, 0, 10, 1)
        self.layout.addWidget(self.release_date,    1, 1)
        self.layout.addWidget(self.country,         2, 1)
        self.layout.addWidget(self.genre,           3, 1)
        self.layout.addWidget(self.duration,        4, 1)
        self.layout.addWidget(self.rating,          5, 1)
        self.layout.addWidget(self.director,        6, 1)
        self.layout.addWidget(self.cast,            7, 1)
        self.layout.addWidget(self.description,     8, 1)
        self.layout.addLayout(self.links_layout,    9, 1)

        self.setWidget(self.widget)

    def TrailerClicked(self, e):
        #Get youtube code from text and append to url
        yt_url = f"https://www.youtube.com/watch?v={self.yt_code}"

        #Open URL
        QDesktopServices.openUrl(QUrl(yt_url))

    def TmdbClicked(self, e):
        #Get TMDB code from text and append to url
        tmdb_url = f"https://www.themoviedb.org/movie/{self.tmdb_code}"

        #Open URL
        QDesktopServices.openUrl(QUrl(tmdb_url))

    def setFavorite(self, is_fav):
        if is_fav:
            #If favorite, set coloured icon
            self.fav_button.setIcon(self.parent.favorites_icon_colour)
        else:
            #If not favorite, set normal icon
            self.fav_button.setIcon(self.parent.favorites_icon)

class SeriesInfoBox(QScrollArea):
    def __init__(self, parent=None):
        super().__init__()

        self.parent = parent

        self.yt_code    = None
        self.tmdb_code  = None

        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignTop)

        self.widget = QWidget()

        self.layout = QGridLayout(self.widget)
        self.layout.setAlignment(Qt.AlignTop)

        self.maxCoverWidth = 200

        #Create cover image
        self.cover          = QLabel()
        self.cover_img      = QPixmap(self.parent.path_to_no_img)
        self.cover.setAlignment(Qt.AlignTop)
        self.cover.setPixmap(self.cover_img.scaledToWidth(self.maxCoverWidth))
        self.cover.setFixedWidth(self.maxCoverWidth)

        #Create favorites button
        self.fav_button = QPushButton("")
        self.fav_button.setFixedWidth(25)
        self.fav_button.setFlat(True)
        self.fav_button.setIcon(self.parent.favorites_icon)
        self.fav_button.clicked.connect(lambda: self.parent.favButtonPressed("Series", self))

        #Create information labels
        self.name           = QLabel("No series selected...")
        self.release_date   = QLabel("Release date: ??-??-????")
        self.genre          = QLabel("Genre: ?")
        self.num_seasons    = QLabel("Seasons: ?")
        self.duration       = QLabel("Episode duration: ? min")
        self.rating         = QLabel("Rating: ?")
        self.director       = QLabel("Director: ?")
        self.cast           = QLabel("Cast: ?")
        self.description    = QLabel("Description: ?")

        self.trailer = QLabel()
        self.trailer.setAlignment(Qt.AlignLeft)
        self.trailer.setFixedWidth(50)
        self.trailer.setEnabled(False)

        self.tmdb = QLabel()
        self.tmdb.setAlignment(Qt.AlignLeft)
        self.tmdb.setFixedWidth(50)
        self.tmdb.setEnabled(False)

        #Set YouTube icon
        self.yt_img = QPixmap(self.parent.path_to_yt_img)
        self.trailer.setPixmap(self.yt_img.scaledToHeight(30))

        #Set TMDB icon
        self.tmdb_img = QPixmap(self.parent.path_to_tmdb_img)
        self.tmdb.setPixmap(self.tmdb_img.scaledToHeight(30))

        self.trailer.mousePressEvent    = self.TrailerClicked
        self.tmdb.mousePressEvent       = self.TmdbClicked

        self.name.setFont(QFont('Arial', 14, QFont.Bold))

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
        self.layout.addWidget(self.cover,           1, 0, 10, 1)
        self.layout.addWidget(self.release_date,    1, 1)
        self.layout.addWidget(self.genre,           2, 1)
        self.layout.addWidget(self.num_seasons,     3, 1)
        self.layout.addWidget(self.duration,        4, 1)
        self.layout.addWidget(self.rating,          5, 1)
        self.layout.addWidget(self.director,        6, 1)
        self.layout.addWidget(self.cast,            7, 1)
        self.layout.addWidget(self.description,     8, 1)
        self.layout.addLayout(self.links_layout,    9, 1)

        #Add widget with all items to the scrollarea (self)
        self.setWidget(self.widget)

    def TrailerClicked(self, e):
        #Get youtube code from text and append to url
        yt_url = f"https://www.youtube.com/watch?v={self.yt_code}"

        #Open URL
        QDesktopServices.openUrl(QUrl(yt_url))

    def TmdbClicked(self, e):
        #Get TMDB code from text and append to url
        tmdb_url = f"https://www.themoviedb.org/tv/{self.tmdb_code}"

        #Open URL
        QDesktopServices.openUrl(QUrl(tmdb_url))

    def setFavorite(self, is_fav):
        if is_fav:
            #If favorite, set coloured icon
            self.fav_button.setIcon(self.parent.favorites_icon_colour)
        else:
            #If not favorite, set normal icon
            self.fav_button.setIcon(self.parent.favorites_icon)


