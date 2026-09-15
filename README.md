![GitHub all releases](https://img.shields.io/github/downloads/LapinFou/Xtream-m3u_plus-IPTV-Player/total?color=blue&label=Total%20Downloads&logo=github)
![GitHub Release](https://img.shields.io/github/v/release/LapinFou/Xtream-m3u_plus-IPTV-Player?label=Latest%20Stable&logo=github)
![GitHub License](https://img.shields.io/github/license/LapinFou/Xtream-m3u_plus-IPTV-Player?label=License&logo=github)
![GitHub stars](https://img.shields.io/github/stars/LapinFou/Xtream-m3u_plus-IPTV-Player)

# FREE OPENSOURCE M3U/XTREME IPTV PLAYER

This IPTV player, built with Python and PyQt5, supports M3U_plus playlists and Xtream Codes API, allowing users to manage and play IPTV channels, movies, and series.

> Feel free to report issues when encountering any problems: [Issues](https://github.com/LapinFou/Xtream-m3u_plus-IPTV-Player/issues)

# Download

## V3.0.0 Beta

Version **V3.0.0** is currently available as a beta/test release for users who want to try the new V3 architecture and features before the final stable release.

[**Download V3.0.0 Beta / Test Release**](https://github.com/LapinFou/Xtream-m3u_plus-IPTV-Player/releases)

> V3.00 is currently in beta. It includes major internal changes and may still contain regressions or unfinished behavior.

## Development branch

The current V3 development branch is available here:

[**codex/v3-refactor**](https://github.com/LapinFou/Xtream-m3u_plus-IPTV-Player/tree/codex/v3-refactor)

## All releases

[**View all releases**](https://github.com/LapinFou/Xtream-m3u_plus-IPTV-Player/releases)

# What's new in V3

Version 3 is a major refactoring of the application aimed at making the codebase easier to maintain, test, debug, and extend. Most of the existing functionality has been reorganized into clearer and more reusable components, while several user-facing improvements have also been introduced.

| | |
|---|---|
| **Major codebase refactoring** | The application has been reorganized into a proper package structure with clearer separation between UI, provider communication, configuration, media playback, caching, application startup, and shared utilities. Obsolete compatibility code and duplicated logic have also been removed. |
| **Improved maintainability and testing** | Shared components have been extracted and standardized, including themes, navigation widgets, settings dialogs, information panels, sorting, search, account management, provider access, and application bootstrap logic. Regression tests were also introduced to help prevent future changes from breaking existing behavior. |
| **Safer configuration management** | Configuration handling has been extensively refactored. INI writes are now centralized and atomic, application defaults and preferences are managed consistently, and configuration migrations allow older user settings to be upgraded safely between versions. |
| **Better multi-account support** | IPTV accounts now use stable internal identifiers. Provider caches, favorites, category state, and category preferences are isolated per account. The active account is shown in the window title and accounts can be switched more quickly. |
| **Improved provider and cache handling** | Xtream API communication, credential parsing, stream URL generation, EPG decoding, provider details, catalog preparation, JSON storage, and caching are now handled by dedicated reusable components. Provider catalogs are stored locally in separate caches for each IPTV account, improving data isolation and reducing loading times when cached data can be reused. |
| **Improved search and sorting** | Title search relevance has been improved and search views now reuse the same sorting logic as the main playlists, providing more consistent results throughout the application. |
| **Player improvements** | Internal and external player handling has been reorganized and made more robust. The application now handles unavailable internal VLC configurations more cleanly, external VLC receives the media title, and the embedded player's controls have been made more compact and consistent. |
| **User interface improvements** | Category lists now display item counts, account dialogs better accommodate long URLs, passwords can be shown while editing accounts, favorites refresh immediately after changes, and several UI components have been cleaned up and standardized. |
| **Unified build and debug workflows** | Windows, MacOS, Rocky Linux, Fedora, and Red Hat Enterprise Linux 9 build workflows now follow the same release/debug approach, use more consistent Python detection, and provide improved diagnostics for troubleshooting packaged builds. |
| **Improved stability and diagnostics** | Network settings, application resources, update checks, player preferences, general preferences, and advanced settings have been centralized. Additional diagnostics and cleanup logic make runtime and startup problems easier to identify. |

# Features

- **Windows, MacOS, Rocky Linux, Fedora and Red Hat Enterprise Linux 9 support**
- **M3U_plus support:** Load and play live TV, movies, and series.
- **Xtream Codes API:** Log in with Xtream credentials and dynamically load content.
- **Categorized playlists:** Content is organized into Live TV, Movies, and Series tabs for easy navigation.
- **Favorites:** Add items to Favorites and find them in the dedicated Favorites category.
- **Per-account favorites:** Favorites are stored independently for each IPTV account.
- **Quick account switching:** Switch between configured IPTV accounts more easily.
- **Per-account category preferences:** Category state and preferences are stored independently for each IPTV account.
- **EPG support:** Access and download Electronic Program Guide data for live TV channels.
- **Movie and series information:** Display additional information such as cover, description, cast, trailer, TMDB information, and more when available.
- **Series navigation:** Browse series, seasons, and episodes with efficient Go Back navigation.
- **Improved search:** Search categories and content with more relevant title matching.
- **Search history:** Use the Up and Down arrow keys to access previously searched text.
- **Sorting:** Sort lists A-Z, Z-A, or disable sorting. The default sorting behavior can be configured in Settings.
- **Category item counts:** Category lists display the number of available items.
- **Internal player:** Built-in libVLC-based player for playing IPTV content directly inside the application.
- **External player support:** Play channels, movies, and series using an external media player such as VLC or SMPlayer.
- **Themes:** Light, Dark, and System theme support.
- **Info tab:** Display IPTV account status and account information.
- **Adjustable column widths:** Resize columns in each tab by dragging their edges.
- **Error handling:** Graceful handling of loading, configuration, and playback errors.
- **Cross-platform builds:** Dedicated build scripts are provided for Windows, MacOS, Rocky Linux, Fedora, and Red Hat Enterprise Linux 9.

### Recommended media players

For external playback, VLC and SMPlayer are supported:

- [VLC media player](https://www.videolan.org/vlc/)
- [SMPlayer](https://www.smplayer.info/)

# Future plans

- **M3U file support:** Select a local M3U file or a URL to an M3U file and load its data.
- **Home tab:** Add a home page with previously watched and popular movies and series.
- **TMDB integration:** Extend movie and series information using the TMDB API.

<details>
<summary><h1>Debug</h1></summary>

This section contains technical information intended mainly for development, troubleshooting, and testing.

<details>
<summary><h2>Configuration migrations</h2></summary>

`userdata.ini` records the version of its persisted-data schema:

```ini
[Application]
config_schema_version = 1
```

`config_schema_version` identifies the structure and meaning of the persisted data.

When a major or minor update changes that structure, the application can compare this number with `CURRENT_CONFIG_SCHEMA_VERSION` and apply every missing migration in order.

For example, schema 1 converts the former combined `VOD` option into independent LIVE, Movies, and Series options while preserving the user's previous choice.

This value is deliberately separate from `CURRENT_VERSION`. The application version is already compiled into the executable and is used by the GitHub update checker; storing it again in `userdata.ini` would be redundant. Most application releases do not change the configuration schema.

When adding a configuration migration:

1. Increment `CURRENT_CONFIG_SCHEMA_VERSION`.
2. Add an ordered `if stored_schema_version < N` block to `updateUserDataFile()`.
3. Make the migration safe to run repeatedly and preserve existing user preferences.
4. Update the stored schema marker only after the migration blocks have completed.

The loader preserves a schema number newer than the current application understands. This prevents an older build from incorrectly marking a future configuration as an older schema.

</details>

<details>
<summary><h2>How to compile the source code</h2></summary>

<details>
<summary><h3>Windows</h3></summary>

#### 1. Install Python 3

Install the latest Python 3 from [python.org](https://www.python.org/downloads/).

During installation:

- Use administrator privileges when appropriate.
- Add `python.exe` to the system `PATH`.

#### 2. Install the dependencies

Open a Windows Command Prompt in the project directory:

```bash
python -m pip install --upgrade pip
python -m pip install --upgrade setuptools
python -m pip install --upgrade pyinstaller
python -m pip install -r requirements.txt
```

#### 3. Verify PyInstaller

```bash
pyinstaller --version
```

#### 4. Build

Run:

```text
build_IPTV_Player_Win.bat
```

The generated files are written to the `dist` directory.

</details>

<details>
<summary><h3>MacOS</h3></summary>

#### 1. Install the required applications

- Install the latest Python 3 from [python.org](https://www.python.org/downloads/macos/).
- Install the latest VLC from [videolan.org](https://www.videolan.org/vlc/) in `/Applications`.

#### 2. Install the build dependencies

```bash
python3 -m pip install --upgrade pip setuptools pyinstaller
python3 -m pip install -r requirements.txt
```

#### 3. Build the application

Make the MacOS build script executable:

```bash
chmod +x build_IPTV_Player_macOS.sh
```

Run:

```bash
./build_IPTV_Player_macOS.sh
```

The build creates:

```text
dist/IPTV Player.app
dist/IPTV Player Vx.x.x.dmg
```

The `.app` bundle can be used for local testing. The versioned `.dmg` package is intended for distribution.

#### 4. Install the application

Open the generated `.dmg` file and drag `IPTV Player.app` onto the `Applications` shortcut.

The build script removes PyInstaller's duplicate executable folder after the `.app` bundle has been created.

Because the application is not currently code-signed, MacOS may require you to Control-click the application and choose **Open** on first launch.

</details>

<details>
<summary><h3>Rocky Linux / Fedora / Red Hat Enterprise Linux 9</h3></summary>

#### 1. Install the required development packages

Install Python 3 and the Python development files using `dnf`.

For example:

```bash
sudo dnf install python3 python3-devel
```

If you build Python yourself, configure it with shared-library support:

```bash
./configure --enable-shared
```

#### 2. Install the Python dependencies

```bash
python3 -m pip install --upgrade pip
python3 -m pip install --upgrade setuptools
python3 -m pip install --upgrade pyinstaller
python3 -m pip install -r requirements.txt
```

If necessary:

```bash
export PATH="$PATH:$HOME/.local/bin"
```

#### 3. Verify PyInstaller

```bash
pyinstaller --version
```

#### 4. Build

```bash
chmod +x build_IPTV_Player_Linux.sh
./build_IPTV_Player_Linux.sh
```

The generated files are written to the `dist` directory.

</details>

</details>

</details>

