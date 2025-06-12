@echo off
REM Set the path to PyInstaller executable (if pyinstaller is in PATH, just use "pyinstaller")
SET PYINSTALLER=pyinstaller

REM Main Python script to package
SET MAIN_SCRIPT="IPTV M3U_Plus PLAYER by MY-1.py"

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

REM Run PyInstaller directly with all necessary options and added data files
%PYINSTALLER% ^
  --onefile ^
  --noconsole ^
  --noconfirm ^
  --icon "Images/TV_icon.ico" ^
  --name "IPTV_Player" ^
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
  --add-data "Threadpools.py;." ^
  --add-data "CustomPyQtWidgets.py;." ^
  --add-data "AccountManager.py;." ^
  %MAIN_SCRIPT%

echo.
echo Build complete. Executable saved in %DIST_PATH%.
pause
