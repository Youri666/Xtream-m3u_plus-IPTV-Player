![GitHub all releases](https://img.shields.io/github/downloads/Youri666/Xtream-m3u_plus-IPTV-Player/total?color=blue&label=Total%20Downloads&logo=github)
![GitHub release (latest by date)](https://img.shields.io/github/downloads/Youri666/Xtream-m3u_plus-IPTV-Player/V1.03.02/total?color=purple&label=Latest%20Release%20Downloads&logo=github)
![GitHub License](https://img.shields.io/github/license/Youri666/Xtream-m3u_plus-IPTV-Player?label=License&logo=github)
![GitHub stars](https://img.shields.io/github/stars/Youri666/Xtream-m3u_plus-IPTV-Player)

# FREE OPENSOURCE M3U/XTREME IPTV PLAYER

This IPTV player, built with Python and PyQt5, supports M3U_plus playlists and Xtream Codes API, allowing users to manage and play IPTV channels, movies, and series.

## What's new in V2

| | |
|---|---|
| **Internal player** | Built-in libvlc-backed player window with seek bar, prev/next that walk the visible playlist, sidebar with live filter, subtitle picker, fullscreen, auto-hide controls, mouse-wheel volume, middle-click pause, double-click fullscreen, and persisted volume |
| **Theme** | Light / Dark / **System** (auto-detects Windows AppsUseLightTheme) |
| **Internationalization** | Application font set to Segoe UI / Noto Sans / Helvetica Neue so Arabic, CJK, Hebrew etc. render with real glyphs (no more `?` boxes). EPG decoder also tries CP1256 (Arabic ANSI) when UTF-8 fails, so MENA-region providers display correctly |
| **Stability** | Startup-crash hardening — every `configparser` read is wrapped against `Error` / `UnicodeDecodeError`, every section/key access uses `has_option()`. File-based logging to `log.txt` captures every print, traceback and unhandled exception |
| **Bug fixes** | #92, #74, #47, #18, #17, #2 / #13 — see the [V2 PR](https://github.com/hossamaladdin/Xtream-m3u_plus-IPTV-Player/tree/v2-fixes-and-internal-player) for the full list |

### Internal player

![Internal player playing a LIVE channel](Screenshots/V2/internal-player-live.png)

Auto-hides 3 s after the last input, wakes on any mouse move / key. Translucent overlay so the video shows through. Cursor hides with the controls (only over the video, never over the bar). Keyboard: `Space` play/pause, `F` fullscreen, `S` cycle subs, `M` mute, `[ / ]` prev / next, `← / →` ±10 s, `↑ / ↓` volume, `L` toggle sidebar, `Esc` exit fullscreen.



> Feel free to report issues when encountering any problems: [Issues](https://github.com/Youri666/Xtream-m3u_plus-IPTV-Player/issues)

> For sharing ideas and general questions: [Discussions](https://github.com/Youri666/Xtream-m3u_plus-IPTV-Player/discussions)

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
- **Adjustable column widths**: Adjust the column widths in each tab to your liking by dragging the edges.
- **Error Handling:** Graceful handling of loading issues.
- **External Player Support:** Play channels/movies/series using VLC or SMPlayer.
- **Recommended Player:** For optimal performance, use VLC media player. Download it at: https://www.videolan.org/vlc/
- **Recommended Player:** For optimal performance, use SMPlayer. Download it at: https://www.smplayer.info

# Future plans
- **M3U file support**: Select M3U file or URL to M3U file to load data from.
- **Home tab:** Home tab with previously watched and popular movies and series.
- **TMDB support:** Much more information about movies and series with the TMDB API.
- **Improve startup loading time:** Improve loading time at startup by optionally loading the IPTV data from cache.
- **Dark theme**

## Configuration migrations

`userdata.ini` records the version of its persisted-data schema:

```ini
[Application]
config_schema_version = 4
```

`config_schema_version` identifies the structure and meaning of the persisted data.
When a major or minor update changes that structure, the application can compare this
number with `CURRENT_CONFIG_SCHEMA_VERSION` and apply every missing migration in order.
For example, schema 1 converts the former combined `VOD` option into independent LIVE,
Movies, and Series options while preserving the user's previous choice.

This value is deliberately separate from `CURRENT_VERSION`. The application version
is already compiled into the executable and is used by the GitHub update checker;
storing it again in `userdata.ini` would be redundant. Most application releases do
not change the configuration schema.

When adding a configuration migration:

1. Increment `CURRENT_CONFIG_SCHEMA_VERSION`.
2. Add an ordered `if stored_schema_version < N` block to `migrate_user_data_file()`.
3. Make the migration safe to run repeatedly and preserve existing user preferences.
4. Update the stored schema marker only after the migration blocks have completed.

The loader preserves a schema number newer than the current application understands.
This prevents an older build from incorrectly marking a future configuration as an
older schema.

<details>
<summary><h1><strong>FAQ</strong></h1></summary>

<details>
<summary><strong>My Live TV doesn't work, but my movies and series do work. How can I fix this?</strong></summary>

Some IPTV providers require a different URL format than the default, therefore you need to change this URL format. Go to the account manager inside the IPTV player. And in the live tv format line replace the URL format with one of the following URL formats:

```{server}/{username}/{password}/{stream_id}```

```{server}/{username}/{password}/{stream_id}.ts```

```{server}/{username}/{password}/{stream_id}.m3u8```

```{server}/{username}/{password}/live/{stream_id}```

```{server}/{username}/{password}/live/{stream_id}.ts```

```{server}/{username}/{password}/live/{stream_id}.m3u8```

```{server}/live/{username}/{password}/{stream_id}```

```{server}/live/{username}/{password}/{stream_id}.ts```

```{server}/live/{username}/{password}/{stream_id}.m3u8```

If none of these work, more attention is needed and you should create an [Issues](https://github.com/Youri666/Xtream-m3u_plus-IPTV-Player/issues).

</details>

</details>

<details>
<summary><h1><strong>Screenshots</strong></h1></summary>
  
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

</details>

<details>
<summary><h1><strong>How To compile the source code</strong></h1></summary>
  
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
python -m pip install -r requirements.txt
```

### 3. Verify that PyInstaller is installed correctly

```bash
pyinstaller --version
# Example of expected output: 6.14.0
```

### 4. Final Setup
- Run the [build_IPTV_Player_Win.bat](build_IPTV_Player_Win.bat) file to start the process.
- The script creates the single desktop executable in `dist`. Detailed diagnostic
  logging can be enabled from **Advanced settings** when troubleshooting is required.

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
python3 -m pip install -r requirements.txt
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
`chmod +x build_IPTV_Player_Linux.sh`
- Run the [./build_IPTV_Player_Linux.sh](build_IPTV_Player_Linux.sh) file to start the process.
- The script creates the single desktop executable in `dist`. Detailed diagnostic
  logging can be enabled from **Advanced settings** when troubleshooting is required.

## macOS Project Setup Instructions

### 1. Install the required applications
- Install the latest Python 3 from [python.org](https://www.python.org/downloads/macos/).
- Install the latest VLC from [videolan.org](https://www.videolan.org/vlc/) in `/Applications`.

### 2. Install the build dependencies

```bash
python3 -m pip install --upgrade pip setuptools pyinstaller
python3 -m pip install -r requirements.txt
```

### 3. Build the application
- Make the macOS script executable with the command:\
`chmod +x build_IPTV_Player_macOS.sh`
- Run [./build_IPTV_Player_macOS.sh](build_IPTV_Player_macOS.sh).
- The script creates the single desktop application. Detailed diagnostic logging
  can be enabled from **Advanced settings** when troubleshooting is required.
- The generated application is written to `dist/IPTV Player.app`.
- A versioned `dist/IPTV Player Vx.x.x.dmg` release package is also created.

### 4. Install the application
- Open the generated `.dmg` file.
- Drag `IPTV Player.app` onto the `Applications` shortcut.
- The build script removes PyInstaller's duplicate executable folder after the
  `.app` bundle has been created. The `dist` folder contains the application for
  local testing and the `.dmg` file for distribution.
- On first launch, macOS may require Control-clicking the application and choosing
  **Open** because the application is not code-signed.

</details>
