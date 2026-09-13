"""Compatibility imports for the provider worker module.

New code should import these classes from ``iptv_player.provider.workers``.
"""

from iptv_player.provider.workers import (
    AccountInfoWorker,
    EPGWorker,
    FetchDataWorker,
    ImageFetcher,
    MovieInfoFetcher,
    OnlineWorker,
    SeriesInfoFetcher,
)

__all__ = [
    "AccountInfoWorker",
    "EPGWorker",
    "FetchDataWorker",
    "ImageFetcher",
    "MovieInfoFetcher",
    "OnlineWorker",
    "SeriesInfoFetcher",
]
