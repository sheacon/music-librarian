"""Last.fm API integration for album popularity data."""

import httpx

from .config import LASTFM_API_KEY

LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"


def get_album_listeners(artist: str, album: str, api_key: str | None = None) -> int:
    """Get listener count for an album from Last.fm.

    Args:
        artist: Artist name.
        album: Album title.
        api_key: Last.fm API key. If None, uses LASTFM_API_KEY from config/env.

    Returns:
        Number of listeners, or 0 if not found.
    """
    if api_key is None:
        api_key = LASTFM_API_KEY

    if not api_key:
        return 0

    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(
                LASTFM_API_URL,
                params={
                    "method": "album.getinfo",
                    "api_key": api_key,
                    "artist": artist,
                    "album": album,
                    "format": "json",
                },
            )

            if response.status_code != 200:
                return 0

            data = response.json()
            album_data = data.get("album", {})
            listeners = album_data.get("listeners", "0")
            return int(listeners)
    except Exception:
        return 0


def rank_albums_by_popularity(
    albums: list,
    artist: str,
    api_key: str | None = None,
) -> list:
    """Rank albums by Last.fm listener count.

    Args:
        albums: List of QobuzAlbum objects.
        artist: Artist name for Last.fm lookup.
        api_key: Last.fm API key.

    Returns:
        List of (album, listeners) tuples sorted by listeners descending.
    """
    ranked = []
    for album in albums:
        listeners = get_album_listeners(artist, album.title, api_key)
        ranked.append((album, listeners))

    # Sort by listeners descending
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked
