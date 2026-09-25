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

VENV_PATH=".venv"
VENV_PYTHON="$VENV_PATH/bin/python"

# Keep build tools and application dependencies isolated from the system Python.
if [ ! -x "$VENV_PYTHON" ]; then
  echo "Creating local Python environment in $VENV_PATH..."
  "$PYTHON_BIN" -m venv "$VENV_PATH"
fi

PYTHON_BIN="$VENV_PYTHON"
echo "Installing build dependencies in $VENV_PATH..."
"$PYTHON_BIN" -m pip install -r requirements-build.txt

# Confirm all modules can be collected before deleting previous builds.
if ! "$PYTHON_BIN" -c "import PyQt5, requests, lxml, dateutil, vlc" &> /dev/null; then
  echo "ERROR: Required Python modules are still unavailable. Build cancelled."
  exit 1
fi

echo "Application dependencies are available."
echo "PyInstaller version:"
"$PYTHON_BIN" -m PyInstaller --version

# Set variables
MAIN_SCRIPT="IPTVPlayer.py"
BUILD_PATH="build"
DIST_PATH="dist"

# Remove generated specification files after both successful and failed builds.
cleanup_spec_files() {
  rm -f "IPTV Player.spec"
}
trap cleanup_spec_files EXIT

# Remove previous build and dist folders
if [ -d "$BUILD_PATH" ]; then
  echo "Removing old build folder: $BUILD_PATH"
  rm -rf "$BUILD_PATH"
fi

if [ -d "$DIST_PATH" ]; then
  echo "Removing old dist folder: $DIST_PATH"
  rm -rf "$DIST_PATH"
fi

# PyInstaller writes specification files beside the script; remove stale variants.
rm -f "IPTV Player.spec"

# Package one desktop application; detailed diagnostics are enabled in the app.
PYINSTALLER_ARGS=(
  --clean
  --onefile
  --noconfirm
  --hidden-import vlc
  --icon "images/TV_icon.png"
  --distpath "$DIST_PATH"
  --workpath "$BUILD_PATH"
  --add-data "images/TV_icon.ico:images"
  --add-data "images/404_not_found.png:images"
  --add-data "images/no_image.jpg:images"
  --add-data "images/loading-icon.png:images"
  --add-data "images/tv_tab_icon.ico:images"
  --add-data "images/movies_tab_icon.ico:images"
  --add-data "images/series_tab_icon.ico:images"
  --add-data "images/home_tab_icon.ico:images"
  --add-data "images/favorite_tab_icon.ico:images"
  --add-data "images/favorite_tab_icon_colour.ico:images"
  --add-data "images/info_tab_icon.ico:images"
  --add-data "images/settings_tab_icon.ico:images"
  --add-data "images/search_bar_icon.ico:images"
  --add-data "images/sorting_icon.ico:images"
  --add-data "images/clear_button_icon.ico:images"
  --add-data "images/go_back_icon.ico:images"
  --add-data "images/account_manager_icon.ico:images"
  --add-data "images/film_camera_icon.ico:images"
  --add-data "images/primary_full-TMDB.svg:images"
  --add-data "images/yt_icon_rgb.png:images"
  --add-data "images/unknown_status.png:images"
  --add-data "images/online_status.png:images"
  --add-data "images/maybe_status.png:images"
  --add-data "images/offline_status.png:images"
)

"$PYTHON_BIN" -m PyInstaller \
  "${PYINSTALLER_ARGS[@]}" \
  --noconsole \
  --name "IPTV Player" \
  "$MAIN_SCRIPT"

echo
echo "Build completed. Output is available in $DIST_PATH."
