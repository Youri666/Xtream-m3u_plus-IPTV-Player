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

# Remove generated specification files after both successful and failed builds.
cleanup_spec_files() {
  rm -f "IPTV Player.spec" "IPTV Player with debug console.spec"
}
trap cleanup_spec_files EXIT

# Accept an explicit mode for automation, or ask when launched interactively.
case "${1:-}" in
  --release) BUILD_CHOICE=1 ;;
  --debug) BUILD_CHOICE=2 ;;
  --both) BUILD_CHOICE=3 ;;
  "")
    echo "==============================="
    echo "What would you like to do?"
    echo
    echo "1. Create executable without console"
    echo "2. Create executable with console"
    echo "3. Create both executables"
    echo "==============================="
    read -r -p "Enter your choice (1, 2, or 3): " BUILD_CHOICE
    ;;
  *)
    echo "Usage: $0 [--release|--debug|--both]"
    exit 1
    ;;
esac

if [[ ! "$BUILD_CHOICE" =~ ^[123]$ ]]; then
  echo "ERROR: Invalid build selection."
  exit 1
fi

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
rm -f "IPTV Player.spec" "IPTV Player with debug console.spec"

# Keep shared packaging options in one list so release and debug builds cannot drift.
PYINSTALLER_ARGS=(
  --clean
  --onefile
  --noconfirm
  --hidden-import vlc
  --icon "Images/TV_icon.png"
  --distpath "$DIST_PATH"
  --workpath "$BUILD_PATH"
  --add-data "Images/TV_icon.ico:Images"
  --add-data "Images/404_not_found.png:Images"
  --add-data "Images/no_image.jpg:Images"
  --add-data "Images/loading-icon.png:Images"
  --add-data "Images/home_tab_icon.ico:Images"
  --add-data "Images/tv_tab_icon.ico:Images"
  --add-data "Images/movies_tab_icon.ico:Images"
  --add-data "Images/series_tab_icon.ico:Images"
  --add-data "Images/favorite_tab_icon.ico:Images"
  --add-data "Images/favorite_tab_icon_colour.ico:Images"
  --add-data "Images/info_tab_icon.ico:Images"
  --add-data "Images/settings_tab_icon.ico:Images"
  --add-data "Images/search_bar_icon.ico:Images"
  --add-data "Images/sorting_icon.ico:Images"
  --add-data "Images/clear_button_icon.ico:Images"
  --add-data "Images/go_back_icon.ico:Images"
  --add-data "Images/account_manager_icon.ico:Images"
  --add-data "Images/film_camera_icon.ico:Images"
  --add-data "Images/primary_full-TMDB.svg:Images"
  --add-data "Images/yt_icon_rgb.png:Images"
  --add-data "Images/unknown_status.png:Images"
  --add-data "Images/online_status.png:Images"
  --add-data "Images/maybe_status.png:Images"
  --add-data "Images/offline_status.png:Images"
  --add-data "Threadpools.py:."
  --add-data "CustomPyQtWidgets.py:."
  --add-data "AccountManager.py:."
)

build_executable() {
  local output_name=$1
  local console_option=$2
  "$PYTHON_BIN" -m PyInstaller \
    "${PYINSTALLER_ARGS[@]}" \
    "$console_option" \
    --name "$output_name" \
    "$MAIN_SCRIPT"
}

if [ "$BUILD_CHOICE" = "1" ] || [ "$BUILD_CHOICE" = "3" ]; then
  build_executable "IPTV Player" --noconsole
fi

if [ "$BUILD_CHOICE" = "2" ] || [ "$BUILD_CHOICE" = "3" ]; then
  build_executable "IPTV Player with debug console" --console
fi

echo
echo "Build completed. Output is available in $DIST_PATH."
