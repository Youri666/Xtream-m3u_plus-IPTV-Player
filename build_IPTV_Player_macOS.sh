#!/bin/bash

set -e

# Use the same Python interpreter for dependency checks and the build.
if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1 && python -c 'import sys; raise SystemExit(sys.version_info.major != 3)' >/dev/null 2>&1; then
  PYTHON_BIN=python
else
  echo "Python was not found. Install Python 3 and try again."
  exit 1
fi

MAIN_SCRIPT="IPTVPlayer.py"
VERSION_FILE="iptv_player/constants.py"
BUILD_PATH="build"
DIST_PATH="dist"
APP_NAME="IPTV Player"
APP_PATH="$DIST_PATH/$APP_NAME.app"
VENV_PATH=".venv"
VENV_PYTHON="$VENV_PATH/bin/python"

# Remove generated specification files after both successful and failed builds.
cleanup_spec_files() {
  rm -f "IPTV Player.spec"
}
trap cleanup_spec_files EXIT

# Keep build tools and application dependencies isolated from the system Python.
if [ ! -x "$VENV_PYTHON" ]; then
  echo "Creating local Python environment in $VENV_PATH..."
  "$PYTHON_BIN" -m venv "$VENV_PATH"
fi

PYTHON_BIN="$VENV_PYTHON"
echo "Installing build dependencies in $VENV_PATH..."
"$PYTHON_BIN" -m pip install -r requirements-build.txt

if ! "$PYTHON_BIN" -c "import PyQt5, requests, lxml, dateutil, vlc" >/dev/null 2>&1; then
  echo "ERROR: Required Python modules are still unavailable. Build cancelled."
  exit 1
fi

echo "PyInstaller version:"
"$PYTHON_BIN" -m PyInstaller --version

# python-vlc is only a binding. The VLC application supplies libVLC at runtime.
if [ ! -d "/Applications/VLC.app" ]; then
  echo "WARNING: VLC was not found in /Applications."
  echo "Install the latest VLC from https://www.videolan.org/vlc/ before using the internal player."
fi

# Remove outputs from an earlier build only after dependency checks succeed.
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

# Generate all standard and Retina representations through Apple's native tool.
# Small Finder icons then use their own bitmap instead of shrinking one large icon.
ICON_ARGS=()
if [ -f "images/TV_icon.png" ]; then
  ICONSET_PATH="$BUILD_PATH/TV_icon.iconset"
  ICNS_PATH="$BUILD_PATH/TV_icon.icns"
  mkdir -p "$ICONSET_PATH"
  sips -z 16 16 "images/TV_icon.png" --out "$ICONSET_PATH/icon_16x16.png" >/dev/null
  sips -z 32 32 "images/TV_icon.png" --out "$ICONSET_PATH/icon_16x16@2x.png" >/dev/null
  sips -z 32 32 "images/TV_icon.png" --out "$ICONSET_PATH/icon_32x32.png" >/dev/null
  sips -z 64 64 "images/TV_icon.png" --out "$ICONSET_PATH/icon_32x32@2x.png" >/dev/null
  sips -z 128 128 "images/TV_icon.png" --out "$ICONSET_PATH/icon_128x128.png" >/dev/null
  sips -z 256 256 "images/TV_icon.png" --out "$ICONSET_PATH/icon_128x128@2x.png" >/dev/null
  sips -z 256 256 "images/TV_icon.png" --out "$ICONSET_PATH/icon_256x256.png" >/dev/null
  sips -z 512 512 "images/TV_icon.png" --out "$ICONSET_PATH/icon_256x256@2x.png" >/dev/null
  sips -z 512 512 "images/TV_icon.png" --out "$ICONSET_PATH/icon_512x512.png" >/dev/null
  sips -z 1024 1024 "images/TV_icon.png" --out "$ICONSET_PATH/icon_512x512@2x.png" >/dev/null
  iconutil -c icns "$ICONSET_PATH" -o "$ICNS_PATH"
  ICON_ARGS=(--icon "$ICNS_PATH")
fi

# Package one desktop application; detailed diagnostics are enabled in the app.
PYINSTALLER_ARGS=(
  --clean
  --onedir
  --noconfirm
  --hidden-import vlc
  "${ICON_ARGS[@]}"
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
  --windowed \
  --name "$APP_NAME" \
  "$MAIN_SCRIPT"

# The .app bundle contains its own complete copy. Keep only the artifact users
# install, after confirming that PyInstaller created it successfully.
if [ ! -d "$APP_PATH" ]; then
  echo "ERROR: The macOS application bundle was not created."
  exit 1
fi
if [ -d "$DIST_PATH/$APP_NAME" ]; then
  echo "Removing duplicate PyInstaller folder: $DIST_PATH/$APP_NAME"
  rm -rf "$DIST_PATH/$APP_NAME"
fi

# Create a compressed disk image suitable for a GitHub release. The Applications
# shortcut lets users install the app with the usual drag-and-drop gesture.
# Strip Windows carriage returns because the source file may use CRLF endings.
APP_VERSION=$(sed -n 's/^CURRENT_VERSION = "\([^"]*\)"/\1/p' "$VERSION_FILE" | head -n 1 | tr -d '\r')
if [ -z "$APP_VERSION" ]; then
  echo "ERROR: Could not read CURRENT_VERSION from $VERSION_FILE."
  exit 1
fi

DMG_STAGE="$BUILD_PATH/dmg"
DMG_PATH="$DIST_PATH/$APP_NAME $APP_VERSION.dmg"
rm -rf "$DMG_STAGE"
mkdir -p "$DMG_STAGE"
cp -R "$APP_PATH" "$DMG_STAGE/"
ln -s /Applications "$DMG_STAGE/Applications"
hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$DMG_STAGE" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

echo
echo "Build completed. Output is available in $DIST_PATH."
echo "Application: $APP_PATH"
echo "Release package: $DMG_PATH"
