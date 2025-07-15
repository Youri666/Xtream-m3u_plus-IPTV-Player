#!/bin/bash

set -e

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
  echo "PyInstaller not found. Please install it with 'pip install pyinstaller'"
  exit 1
fi

# Set variables
PYINSTALLER=pyinstaller
MAIN_SCRIPT="IPTV M3U_Plus PLAYER by MY-1.py"
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

# Run PyInstaller build
$PYINSTALLER \
  --clean \
  --onefile \
  --noconsole \
  --noconfirm \
  --icon "Images/TV_icon.ico" \
  --name "IPTV_Player" \
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
echo -e "\u2714 Build completed. The executable is in the folder $DIST_PATH."
