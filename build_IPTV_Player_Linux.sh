#!/bin/bash

set -e

# Use the same Python interpreter for dependency checks and the build.
if command -v python3 &> /dev/null; then
  PYTHON_BIN=python3
elif command -v python &> /dev/null && python -c 'import sys; raise SystemExit(sys.version_info.major != 3)' &> /dev/null; then
  PYTHON_BIN=python
else
  echo "Python was not found. Install Python 3 and try again."
  exit 1
fi

# Check if PyInstaller is installed for the selected Python interpreter.
if ! "$PYTHON_BIN" -m PyInstaller --version &> /dev/null; then
  echo "PyInstaller not found. Please install it with '$PYTHON_BIN -m pip install pyinstaller'"
  exit 1
fi

# Every dependency must belong to the interpreter used for packaging.
if ! "$PYTHON_BIN" -c "import PyQt5, requests, lxml, dateutil, vlc" &> /dev/null; then
  echo "Installing missing application dependencies..."
  if ! "$PYTHON_BIN" -m pip install -r requirements.txt; then
    echo "ERROR: Application dependencies could not be installed."
    exit 1
  fi
fi

# Confirm all modules can be collected before deleting previous builds.
if ! "$PYTHON_BIN" -c "import PyQt5, requests, lxml, dateutil, vlc" &> /dev/null; then
  echo "ERROR: Required Python modules are still unavailable. Build cancelled."
  exit 1
fi

echo "Application dependencies are available."

# Set variables
MAIN_SCRIPT="IPTVPlayer.py"
BUILD_PATH="build"
DIST_PATH="dist"

# Remove previous build and dist folders
if [ -d "$BUILD_PATH" ]; then
  echo "Removing old build folder: $BUILD_PATH"
  rm -rf "$BUILD_PATH"
fi

if [ -d "$DIST_PATH" ]; then
  echo "Removing old dist folder: $DIST_PATH"
  rm -rf "$DIST_PATH"
fi

# Run PyInstaller and explicitly collect the lazily imported VLC binding.
"$PYTHON_BIN" -m PyInstaller \
  --clean \
  --onefile \
  --noconsole \
  --noconfirm \
  --hidden-import vlc \
  --icon "Images/TV_icon.png" \
  --name "IPTV Player" \
  --distpath "$DIST_PATH" \
  --workpath "$BUILD_PATH" \
  --add-data "Images/TV_icon.ico:Images" \
  --add-data "Images/404_not_found.png:Images" \
  --add-data "Images/no_image.jpg:Images" \
  --add-data "Images/loading-icon.png:Images" \
  --add-data "Images/home_tab_icon.ico:Images" \
  --add-data "Images/tv_tab_icon.ico:Images" \
  --add-data "Images/movies_tab_icon.ico:Images" \
  --add-data "Images/series_tab_icon.ico:Images" \
  --add-data "Images/favorite_tab_icon.ico:Images" \
  --add-data "Images/favorite_tab_icon_colour.ico:Images" \
  --add-data "Images/info_tab_icon.ico:Images" \
  --add-data "Images/settings_tab_icon.ico:Images" \
  --add-data "Images/search_bar_icon.ico:Images" \
  --add-data "Images/sorting_icon.ico:Images" \
  --add-data "Images/clear_button_icon.ico:Images" \
  --add-data "Images/go_back_icon.ico:Images" \
  --add-data "Images/account_manager_icon.ico:Images" \
  --add-data "Images/film_camera_icon.ico:Images" \
  --add-data "Images/primary_full-TMDB.svg:Images" \
  --add-data "Images/yt_icon_rgb.png:Images" \
  --add-data "Images/unknown_status.png:Images" \
  --add-data "Images/online_status.png:Images" \
  --add-data "Images/maybe_status.png:Images" \
  --add-data "Images/offline_status.png:Images" \
  --add-data "Threadpools.py:." \
  --add-data "CustomPyQtWidgets.py:." \
  --add-data "AccountManager.py:." \
  "$MAIN_SCRIPT"

echo
echo "Build completed: $DIST_PATH/IPTV Player"
