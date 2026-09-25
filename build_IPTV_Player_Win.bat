@echo off
SET PYTHON_BIN=
SET VENV_PATH=.venv
SET VENV_PYTHON=.venv\Scripts\python.exe

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

REM Keep build tools and application dependencies isolated from the system Python.
IF NOT EXIST "%VENV_PYTHON%" (
  echo Creating local Python environment in %VENV_PATH%...
  %PYTHON_BIN% -m venv "%VENV_PATH%"
  IF ERRORLEVEL 1 (
    echo ERROR: Could not create the local Python environment.
    pause
    exit /b 1
  )
)

echo Installing build dependencies in %VENV_PATH%...
"%VENV_PYTHON%" -m pip install -r requirements-build.txt
IF ERRORLEVEL 1 GOTO dependency_failed

echo.
echo PyInstaller version:
"%VENV_PYTHON%" -m PyInstaller --version
IF ERRORLEVEL 1 (
  echo.
  echo ERROR: PyInstaller is unavailable in the local Python environment.
  pause
  exit /b 1
)

REM Confirm all modules can be collected before deleting previous builds.
"%VENV_PYTHON%" -c "import PyQt5, requests, lxml, dateutil, vlc" >nul 2>&1
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
"%VENV_PYTHON%" -m PyInstaller ^
  --onefile ^
  --noconsole ^
  --noconfirm ^
  --hidden-import vlc ^
  --icon "images/TV_icon.ico" ^
  --name "IPTV Player" ^
  --workpath %BUILD_PATH% ^
  --distpath %DIST_PATH% ^
  --add-data "images/TV_icon.ico;images" ^
  --add-data "images/404_not_found.png;images" ^
  --add-data "images/no_image.jpg;images" ^
  --add-data "images/loading-icon.png;images" ^
  --add-data "images/tv_tab_icon.ico;images" ^
  --add-data "images/movies_tab_icon.ico;images" ^
  --add-data "images/series_tab_icon.ico;images" ^
  --add-data "images/home_tab_icon.ico;images" ^
  --add-data "images/favorite_tab_icon.ico;images" ^
  --add-data "images/favorite_tab_icon_colour.ico;images" ^
  --add-data "images/info_tab_icon.ico;images" ^
  --add-data "images/settings_tab_icon.ico;images" ^
  --add-data "images/search_bar_icon.ico;images" ^
  --add-data "images/sorting_icon.ico;images" ^
  --add-data "images/clear_button_icon.ico;images" ^
  --add-data "images/go_back_icon.ico;images" ^
  --add-data "images/account_manager_icon.ico;images" ^
  --add-data "images/film_camera_icon.ico;images" ^
  --add-data "images/primary_full-TMDB.svg;images" ^
  --add-data "images/yt_icon_rgb.png;images" ^
  --add-data "images/unknown_status.png;images" ^
  --add-data "images/online_status.png;images" ^
  --add-data "images/maybe_status.png;images" ^
  --add-data "images/offline_status.png;images" ^
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

:dependency_failed
echo.
echo ERROR: Build dependencies could not be installed in %VENV_PATH%.
echo Check your Internet connection and Python installation, then try again.
pause
exit /b 1
