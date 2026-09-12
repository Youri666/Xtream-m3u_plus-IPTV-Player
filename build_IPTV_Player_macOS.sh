#!/bin/bash

set -e

# Use Python 3 consistently for dependency checks and the PyInstaller build.
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found. Install it and try again."
  exit 1
fi

PYTHON_BIN=python3
MAIN_SCRIPT="IPTVPlayer.py"
BUILD_PATH="build"
DIST_PATH="dist"
APP_NAME="IPTV Player"
APP_PATH="$DIST_PATH/$APP_NAME.app"

# PyInstaller and every application dependency must belong to the interpreter
# used for packaging. PyInstaller can otherwise finish with a broken bundle.
if ! "$PYTHON_BIN" -m PyInstaller --version >/dev/null 2>&1; then
  echo "PyInstaller not found. Please install it with '$PYTHON_BIN -m pip install pyinstaller'"
  exit 1
fi

if ! "$PYTHON_BIN" -c "import PyQt5, requests, lxml, dateutil, vlc" >/dev/null 2>&1; then
  echo "Installing missing application dependencies..."
  if ! "$PYTHON_BIN" -m pip install -r requirements.txt; then
    echo "ERROR: Application dependencies could not be installed."
    exit 1
  fi
fi

if ! "$PYTHON_BIN" -c "import PyQt5, requests, lxml, dateutil, vlc" >/dev/null 2>&1; then
  echo "ERROR: Required Python modules are still unavailable. Build cancelled."
  exit 1
fi

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

# Generate all standard and Retina representations through Apple's native tool.
# Small Finder icons then use their own bitmap instead of shrinking one large icon.
ICON_ARGS=()
if [ -f "Images/TV_icon.png" ]; then
  ICONSET_PATH="$BUILD_PATH/TV_icon.iconset"
  ICNS_PATH="$BUILD_PATH/TV_icon.icns"
  mkdir -p "$ICONSET_PATH"
  sips -z 16 16 "Images/TV_icon.png" --out "$ICONSET_PATH/icon_16x16.png" >/dev/null
  sips -z 32 32 "Images/TV_icon.png" --out "$ICONSET_PATH/icon_16x16@2x.png" >/dev/null
  sips -z 32 32 "Images/TV_icon.png" --out "$ICONSET_PATH/icon_32x32.png" >/dev/null
  sips -z 64 64 "Images/TV_icon.png" --out "$ICONSET_PATH/icon_32x32@2x.png" >/dev/null
  sips -z 128 128 "Images/TV_icon.png" --out "$ICONSET_PATH/icon_128x128.png" >/dev/null
  sips -z 256 256 "Images/TV_icon.png" --out "$ICONSET_PATH/icon_128x128@2x.png" >/dev/null
  sips -z 256 256 "Images/TV_icon.png" --out "$ICONSET_PATH/icon_256x256.png" >/dev/null
  sips -z 512 512 "Images/TV_icon.png" --out "$ICONSET_PATH/icon_256x256@2x.png" >/dev/null
  sips -z 512 512 "Images/TV_icon.png" --out "$ICONSET_PATH/icon_512x512.png" >/dev/null
  sips -z 1024 1024 "Images/TV_icon.png" --out "$ICONSET_PATH/icon_512x512@2x.png" >/dev/null
  iconutil -c icns "$ICONSET_PATH" -o "$ICNS_PATH"
  ICON_ARGS=(--icon "$ICNS_PATH")
fi

# Keep the packaged files visible inside the macOS application bundle. This
# makes startup more direct and missing runtime dependencies easier to diagnose.
"$PYTHON_BIN" -m PyInstaller \
  --clean \
  --onedir \
  --windowed \
  --noconfirm \
  --hidden-import vlc \
  "${ICON_ARGS[@]}" \
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
APP_VERSION=$(sed -n 's/^CURRENT_VERSION = "\([^"]*\)"/\1/p' "$MAIN_SCRIPT" | head -n 1 | tr -d '\r')
if [ -z "$APP_VERSION" ]; then
  echo "ERROR: Could not read CURRENT_VERSION from $MAIN_SCRIPT."
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
echo "Build completed: $APP_PATH"
echo "Release package: $DMG_PATH"
echo "Launch with: open '$APP_PATH'"
echo "If Finder shows no error, diagnose with:"
echo "'$APP_PATH/Contents/MacOS/$APP_NAME'"
