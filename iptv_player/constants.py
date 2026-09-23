"""Application metadata and defaults shared across IPTV Player modules."""

CURRENT_VERSION = "V3.1.2"
CURRENT_CONFIG_SCHEMA_VERSION = 4
GITHUB_REPO = "Youri666/Xtream-m3u_plus-IPTV-Player"

REMEMBER_LIST_SORTING = "Remember per list"

DEFAULT_INTERNAL_SEEK_STEP_SECONDS = 10
DEFAULT_INTERNAL_VOLUME_STEP_PERCENT = 2
DEFAULT_INTERNAL_SPEED_STEP = 0.25
DEFAULT_INTERNAL_AUTO_PLAY_NEXT = False
DEFAULT_INTERNAL_AUTO_ADVANCE_SECONDS = 0
DEFAULT_INTERNAL_NETWORK_CACHING_MS = 1000
DEFAULT_HISTORY_SIZE = 50
DEFAULT_RESUME_BEHAVIOR = "ask"
RESUME_BEHAVIORS = ("ask", "resume", "restart")

MEDIA_LANGUAGE_OPTIONS = (
    ("Arabic", "ara"),
    ("Chinese", "zho"),
    ("Dutch", "nld"),
    ("English", "eng"),
    ("French", "fra"),
    ("German", "deu"),
    ("Hindi", "hin"),
    ("Italian", "ita"),
    ("Japanese", "jpn"),
    ("Korean", "kor"),
    ("Polish", "pol"),
    ("Portuguese", "por"),
    ("Romanian", "ron"),
    ("Russian", "rus"),
    ("Spanish", "spa"),
    ("Turkish", "tur"),
)

DEFAULT_URL_FORMATS = {
    "live": "{server}/live/{username}/{password}/{stream_id}.{container_extension}",
    "movie": "{server}/movie/{username}/{password}/{stream_id}.{container_extension}",
    "series": "{server}/series/{username}/{password}/{stream_id}.{container_extension}",
}
