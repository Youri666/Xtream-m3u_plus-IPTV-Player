@echo off
SET PYTHON_BIN=

REM Detect a Python 3 interpreter instead of asking users which command works.
py -3 --version >nul 2>&1
IF NOT ERRORLEVEL 1 SET PYTHON_BIN=py -3
IF NOT DEFINED PYTHON_BIN (
  python -c "import sys; raise SystemExit(sys.version_info.major != 3)" >nul 2>&1
  IF NOT ERRORLEVEL 1 SET PYTHON_BIN=python
)
IF NOT DEFINED PYTHON_BIN (
  echo ERROR: Python 3 was not found. Install it and try again.
  pause
  exit /b 1
)

REM Use the detected interpreter for dependency checks and the build.
echo.
echo PyInstaller version:
%PYTHON_BIN% -m PyInstaller --version
IF ERRORLEVEL 1 (
  echo.
  echo ERROR: PyInstaller is unavailable for the selected Python interpreter.
  echo Install it with: %PYTHON_BIN% -m pip install pyinstaller
  pause
  exit /b 1
)

REM Every dependency must belong to the interpreter used for packaging.
%PYTHON_BIN% -c "import PyQt5, requests, lxml, dateutil, vlc" >nul 2>&1
IF ERRORLEVEL 1 (
  echo.
  echo Installing missing application dependencies...
  %PYTHON_BIN% -m pip install -r requirements.txt
  IF ERRORLEVEL 1 (
    echo.
    echo ERROR: Application dependencies could not be installed.
    echo Check your Internet connection and Python installation, then try again.
    pause
    exit /b 1
  )
)

REM Confirm all modules can be collected before deleting previous builds.
%PYTHON_BIN% -c "import PyQt5, requests, lxml, dateutil, vlc" >nul 2>&1
IF ERRORLEVEL 1 (
  echo.
  echo ERROR: Required Python modules are still unavailable. Build cancelled.
  pause
  exit /b 1
)

echo Application dependencies are available.

REM Main Python script to package
SET MAIN_SCRIPT="IPTVPlayer.py"

REM Set build and dist folders separately
SET BUILD_PATH=build
SET DIST_PATH=dist

REM Clean previous build folder
IF EXIST %BUILD_PATH% (
  echo Deleting existing build directory: %BUILD_PATH%
  rmdir /s /q %BUILD_PATH%
)

REM Clean previous dist folder
IF EXIST %DIST_PATH% (
  echo Deleting existing dist directory: %DIST_PATH%
  rmdir /s /q %DIST_PATH%
)

REM PyInstaller writes specification files beside the script; remove stale variants.
IF EXIST "IPTV Player.spec" del /q "IPTV Player.spec"

REM python-vlc is imported lazily, so PyInstaller cannot discover it automatically.
REM Run PyInstaller directly with all necessary options and added data files
%PYTHON_BIN% -m PyInstaller ^
  --onefile ^
  --noconsole ^
  --noconfirm ^
  --hidden-import vlc ^
  --icon "Images/TV_icon.ico" ^
  --name "IPTV Player" ^
  --workpath %BUILD_PATH% ^
  --distpath %DIST_PATH% ^
  --add-data "Images/TV_icon.ico;Images" ^
  --add-data "Images/404_not_found.png;Images" ^
  --add-data "Images/no_image.jpg;Images" ^
  --add-data "Images/loading-icon.png;Images" ^
  --add-data "Images/home_tab_icon.ico;Images" ^
  --add-data "Images/tv_tab_icon.ico;Images" ^
  --add-data "Images/movies_tab_icon.ico;Images" ^
  --add-data "Images/series_tab_icon.ico;Images" ^
  --add-data "Images/favorite_tab_icon.ico;Images" ^
  --add-data "Images/favorite_tab_icon_colour.ico;Images" ^
  --add-data "Images/info_tab_icon.ico;Images" ^
  --add-data "Images/settings_tab_icon.ico;Images" ^
  --add-data "Images/search_bar_icon.ico;Images" ^
  --add-data "Images/sorting_icon.ico;Images" ^
  --add-data "Images/clear_button_icon.ico;Images" ^
  --add-data "Images/go_back_icon.ico;Images" ^
  --add-data "Images/account_manager_icon.ico;Images" ^
  --add-data "Images/film_camera_icon.ico;Images" ^
  --add-data "Images/primary_full-TMDB.svg;Images" ^
  --add-data "Images/yt_icon_rgb.png;Images" ^
  --add-data "Images/unknown_status.png;Images" ^
  --add-data "Images/online_status.png;Images" ^
  --add-data "Images/maybe_status.png;Images" ^
  --add-data "Images/offline_status.png;Images" ^
  %MAIN_SCRIPT%
IF ERRORLEVEL 1 GOTO build_failed

IF EXIST "IPTV Player.spec" del /q "IPTV Player.spec"
echo.
echo Build complete. Executable saved in %DIST_PATH%.
pause
exit /b 0

:build_failed
IF EXIST "IPTV Player.spec" del /q "IPTV Player.spec"
echo.
echo ERROR: The build failed. Review the messages above for details.
pause
exit /b 1
