![GitHub all releases](https://img.shields.io/github/downloads/Youri666/Xtream-m3u_plus-IPTV-Player/total?color=blue&label=Total%20Downloads&logo=github)
![GitHub Release](https://img.shields.io/github/v/release/Youri666/Xtream-m3u_plus-IPTV-Player?label=Latest%20Stable&logo=github)
![GitHub License](https://img.shields.io/github/license/Youri666/Xtream-m3u_plus-IPTV-Player?label=License&logo=github)
![GitHub stars](https://img.shields.io/github/stars/Youri666/Xtream-m3u_plus-IPTV-Player)

# FREE OPENSOURCE M3U/XTREME IPTV PLAYER

This IPTV player, built with Python and PyQt5, supports M3U_plus playlists and Xtream Codes API, allowing users to manage and play IPTV channels, movies, and series.

[**View all releases**](https://github.com/Youri666/Xtream-m3u_plus-IPTV-Player/releases)

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
| **Player improvements** | Internal and external player handling has been reorganized and made more robust. The application now handles unavailable internal VLC configurations more cleanly, external VLC receives the media title, and the embedded player's controls have been made more compact and consistent. Internal playback automatically pauses when the player is minimized and resumes when the window is restored. |
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
- **Playback resume:** When using the internal player, partially watched content can be resumed, restarted from the beginning, or canceled.
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
- **TMDB integration:** Extend movie and series information using the TMDB API.


# User Guide

## Main interface

The main interface is organized into six tabs: **Live**, **Movies**, **Series**, **History**, **Info**, and **Settings**.

The **Live**, **Movies**, and **Series** tabs all use the same three-column layout:
- **Left column:** categories
- **Middle column:** items available in the selected category
- **Right column:** information about the currently selected item

You can navigate through the first two columns with the **Up/Down arrow keys** and use **Enter** to open or select an item.

Both the category and content lists include a **search bar**, a **clear search** button, and a **filter** button.  
The first column also includes a **Categories** button that lets you choose which categories are visible.

![Main interface showing the common three-column layout used by Live, Movies and Series](Screenshots/main-interface.png)

## History tab

The **History** tab keeps track of recently viewed content and separates it into **Live**, **Movies**, and **Series**.

Each section shows the **last viewed date/time** and the corresponding **title**, making it easy to find content that was previously opened.

The maximum number of history entries is configurable in **Advanced Settings**. The default value is **50 items per content type**.

The History feature is still under development, but playback resume support is already available with the internal player.

![History tab showing recently viewed Live, Movies and Series content](Screenshots/history-tab.png)

## Info tab

The **Info** tab displays information about the currently selected IPTV account.

Its content is refreshed automatically when the tab is opened. A manual refresh can also be triggered with the **Refresh** button.

The refresh interval can be configured in **Advanced Settings**. To avoid unnecessary requests, the information is only refreshed while the **Info** tab is actually being viewed.

The application title bar also shows the name of the currently selected IPTV provider/account after the application name.

![Info tab showing account information and refresh controls](Screenshots/info-tab.png)

## Settings

The **Settings** tab groups the main application preferences, including IPTV accounts, visible content, appearance, sorting, media player selection, advanced options, and update settings.

![Main Settings tab](Screenshots/settings-main.png)

### IPTV accounts

The **IPTV accounts** button opens the account manager, where accounts can be added, edited, or removed.

![IPTV account manager](Screenshots/iptv-accounts.png)

Two account input methods are available:

- **Manual/Xtream entry:** enter the server URL, username, password, and stream URL formats manually.
- **M3U_plus URL entry:** paste an M3U_plus URL and let the application extract the required credentials.

![Manual Xtream account configuration](Screenshots/add-account-xtream.png)

![M3U_plus account configuration](Screenshots/add-account-m3u-plus.png)

Stream URL formats are fully editable because IPTV providers do not always use the same URL structure.

The **Startup account** selects which account should be loaded when the application starts. The **Active account** can be used to switch immediately between configured IPTV accounts.

**My Live TV doesn't work, but Movies and Series do. How can I fix this?**

Some IPTV providers require a different URL format for LIVE streams.
Edit the affected account and try replacing the **Live URL format** with one of the following:

```text
{server}/{username}/{password}/{stream_id}
{server}/{username}/{password}/{stream_id}.ts
{server}/{username}/{password}/{stream_id}.m3u8
{server}/{username}/{password}/live/{stream_id}
{server}/{username}/{password}/live/{stream_id}.ts
{server}/{username}/{password}/live/{stream_id}.m3u8
{server}/live/{username}/{password}/{stream_id}
{server}/live/{username}/{password}/{stream_id}.ts
{server}/live/{username}/{password}/{stream_id}.m3u8
```

If none of these formats work, please open an issue on the V3 repository: [Issues](https://github.com/Youri666/Xtream-m3u_plus-IPTV-Player/issues)

### Content and appearance

The **LIVE**, **Movies**, and **Series** options control which content sections are displayed. Disabled content types are also hidden from related parts of the application, such as History.

**Keep on top** keeps the main window above other windows.

![Content and appearance](Screenshots/content-appearance.png)

The theme can be set to:

- **System** — follows the operating system appearance
- **Light**
- **Dark**

![Content and appearance Dark Theme](Screenshots/content-appearance-dark.png)

### Sorting

The default sorting mode can be configured globally.

Available modes include:
- **Sorting disabled** — keep the order provided by the IPTV provider
- **A → Z**
- **Z → A**
- **Remember per list** — each list/category can use its own sorting mode, selected with the sorting button and remembered for future use

The per-list sorting preferences are stored so they persist between sessions.

![Sorting](Screenshots/sorting.png)


### Media player

The recommended option is the built-in **Internal VLC** player, which uses the VLC engine installed on the computer.

An external media player can also be selected.

The internal player has its own configurable options:

![Internal player settings](Screenshots/internal-player-settings.png)

These settings control seek steps, volume steps, playback-speed steps, preferred audio and subtitle languages, and what should happen when opening media that was previously started.

When **Previously started media** is set to **Ask**, the player can offer to **Resume**, **Restart**, or **Cancel** playback.

### Advanced settings

![Advanced settings](Screenshots/advanced-settings.png)

Advanced settings provide additional control over:
- network timeouts and User-Agent
- automatic Info-tab refresh
- provider catalog caching and refresh interval
- LIVE stream availability checks
- detailed diagnostic logging
- History size and cleanup

When **LIVE stream status checks** are enabled, the Live TV information panel displays a small status indicator for the selected stream: **green** when the stream is available and **red** when it is unavailable. This check can be disabled from Advanced Settings.

Provider catalog caching can significantly reduce loading time by reusing locally stored catalog data instead of downloading it again when it is still valid.

### Updates

The application can check for new releases manually with **Check for updates**, or automatically when **Auto check for updates** is enabled.

![Updates](Screenshots/updates.png)


## Internal player

The built-in **Internal Player** provides direct playback using the installed VLC engine.

The playlist panel can be shown or hidden with the button in the upper-left corner. It displays the current list and includes a filter field for quickly finding an item.

Playback controls provide previous/next navigation, play/pause, seeking, playback speed, volume, audio track selection, subtitles when available, and fullscreen mode.

### Keyboard shortcuts

- **Page Up / Page Down** — previous / next item
- **Left / Right Arrow** — seek backward / forward
- **Space** — play / pause
- **+ / -** — increase / decrease playback speed
- **Mouse wheel** — increase / decrease volume
- **M** — mute / unmute
- **A** — cycle through available audio tracks
- **S** — cycle through available subtitles
- **F** — toggle fullscreen

![Internal player showing the playlist and playback controls](Screenshots/internal-player.png)


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

