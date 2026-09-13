"""Application metadata and defaults shared across IPTV Player modules."""

CURRENT_VERSION = "V3.0.0"
CURRENT_CONFIG_SCHEMA_VERSION = 1
GITHUB_REPO = "Youri666/Xtream-m3u_plus-IPTV-Player"

REMEMBER_CATEGORY_SORTING = "Remember per category"

DEFAULT_INTERNAL_SEEK_STEP_SECONDS = 10
DEFAULT_INTERNAL_VOLUME_STEP_PERCENT = 2
DEFAULT_INTERNAL_SPEED_STEP = 0.25

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
