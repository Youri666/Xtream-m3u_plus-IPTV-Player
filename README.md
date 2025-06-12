
# FREE OPENSOURCE M3U/XTREME IPTV PLAYER

This IPTV player, built with Python and PyQt5, supports M3U_plus playlists and Xtream Codes API, allowing users to manage and play IPTV channels, movies, and series.

> Feel free to report issues when encountering any problems: [Issues](https://github.com/Youri666/Xtream-m3u_plus-IPTV-Player/issues)

# Download
Download the latest version here: [Latest releases](https://github.com/Youri666/Xtream-m3u_plus-IPTV-Player/releases)

# Features
- **Supports Windows, Linux and Mac OS**
- **M3U_plus Support:** Load and play live TV, movies, and series.
- **Xtream Codes API:** Log in with Xtream credentials and dynamically load content.
- **Categorized Playlists:** Organized into Live TV, Movies, and Series tabs for easy navigation.
- **Favorites:** Add items to favorite and find them in the 'Favorites' category.
- **EPG Option:** Access and download Electronic Program Guide for live TV channels.
- **Movies and series information:** Additional movies and series information e.g. movie/series cover, description, cast, trailer, TMDB, etc.
- **Series navigation:** Access series categories and specific episodes with efficient 'Go Back' functionality in series playlist.
- **Search bar history:** By using the up and down keys you can access the previously searched texts in the search bars.
- **Sorting playlists:** Each list can be sorted A-Z, Z-A or sorting can be disabled. The default sorting can be configured in the settings tab.
- **Info tab:** Information about IPTV account status.
- **Error Handling:** Graceful handling of loading issues.
- **External Player Support:** Play channels/movies/series using VLC or SMPlayer.
- **Recommended Player:** For optimal performance, use VLC media player. Download it at: https://www.videolan.org/vlc/
- **Recommended Player:** For optimal performance, use SMPlayer. Download it at: https://www.smplayer.info

# Future plans
- **Home tab:** Home tab with previously watched and popular movies and series.
- **TMDB support:** Much more information about movies and series with the TMDB API.
- **Improve startup loading time:** Improve loading time at startup by optionally loading the IPTV data from cache.
- **Dark theme**

# Screenshots
**Live TV showing EPG data**
![Image](https://github.com/user-attachments/assets/c82f0759-29d8-4b3e-a462-59581523e1d8)

**Movies with information**
![Image](https://github.com/user-attachments/assets/5a2113ef-b871-47d1-9082-85955893ff50)

**Series navigation**
![Image](https://github.com/user-attachments/assets/24c8cc12-8d3b-41c0-a2aa-035d11d6ff8d)
![Image](https://github.com/user-attachments/assets/86ddb458-9008-4875-a072-007e63028cbe)
![Image](https://github.com/user-attachments/assets/9831f4b9-5c83-44ea-9ea4-43d39d15da85)

**Search in categories and entries**
![Image](https://github.com/user-attachments/assets/faa2e022-28f8-4d28-9b39-20da5ada040c)
![Image](https://github.com/user-attachments/assets/df39bd8f-06e5-48aa-8318-dd491c52d4c1)

**Save your IPTV account and optionally auto-select at startup**
![Image](https://github.com/user-attachments/assets/678582bc-8af9-499b-b601-38b7786b57bf)

# How To compile the source code

## Windows Project Setup Instructions

### 1. Install latest Python 3
- Run the [latest Python 3 installer](https://www.python.org/downloads/).
- During installation, make sure to:
  - **Use administrator privileges** when installing Python
  - **Add `python.exe` to the system PATH**
  - Select any other appropriate options as prompted

### 2. Open a Windows Command Prompt and install all dependencies

```bash
python -m pip install --upgrade pip
python -m pip install --upgrade setuptools
python -m pip install --upgrade pyinstaller
python -m pip install --upgrade requests lxml python-dateutil PyQt5
```

### 3. Verify that PyInstaller is installed correctly

```bash
pyinstaller --version
# Example of expected output: 6.14.0
```

### 4. Final Setup
- Run the [build_iptv_player.bat](build_iptv_player.bat) file to start the process.

## Rocky9/RHEL9 Project Setup Instructions

### 1. Install latest Python 3
- To compile Python yourself, download the [source code](https://www.python.org/downloads/source/)
- Tested with Python 3.13.4\
 _Note:_  The following dependencies must be installed:\
`dnf install python3-dev python-dev`\
If you are building Python by yourself, rebuild with `--enable-shared` (or, `--enable-framework` on macOS).\

### 2. Open a Terminal and install all dependencies

```bash
python3 -m pip install --upgrade pip
python3 -m pip install --upgrade setuptools
python3 -m pip install --upgrade pyinstaller
python3 -m pip install --upgrade requests lxml python-dateutil PyQt5
```
_Note:_ If you are not logged in as root (which is recommended), you need to ensure that `pyInstaller` is included in your PATH environment variable:
```bash
export PATH=$PATH:$HOME/.local/bin
```

### 3. Verify that PyInstaller is installed correctly

```bash
pyinstaller --version
# Example of expected output: 6.14.0
```

### 4. Final Setup
- Make the SH script executable with the command:\
`chmod +x build_iptv_player.sh`
- Run the [./build_iptv_player.sh](build_iptv_player.sh) file to start the process.
