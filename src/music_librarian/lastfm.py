"""Last.fm API integration for album popularity data."""

import httpx

from .config import LASTFM_API_KEY

LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"


def _call_lastfm_api(method: str, api_key: str | None = None, **params) -> dict | None:
    """Make a Last.fm API call.

    Args:
        method: API method name (e.g., "album.getinfo").
        api_key: Last.fm API key. If None, uses LASTFM_API_KEY from config/env.
        **params: Additional parameters to pass to the API.

    Returns:
        JSON response dict, or None if the request failed.
    """
    if api_key is None:
        api_key = LASTFM_API_KEY

    if not api_key:
        return None

    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(
                LASTFM_API_URL,
                params={"method": method, "api_key": api_key, "format": "json", **params},
            )
            if response.status_code != 200:
                return None
            return response.json()
    except Exception:
        return None


def get_album_listeners(artist: str, album: str, api_key: str | None = None) -> int:
    """Get listener count for an album from Last.fm.

    Args:
        artist: Artist name.
        album: Album title.
        api_key: Last.fm API key. If None, uses LASTFM_API_KEY from config/env.

    Returns:
        Number of listeners, or 0 if not found.
    """
    data = _call_lastfm_api("album.getinfo", api_key, artist=artist, album=album)
    if not data:
        return 0
    listeners = data.get("album", {}).get("listeners", "0")
    return int(listeners)


def get_artist_top_tag(artist: str, api_key: str | None = None) -> str | None:
    """Get the top tag (genre) for an artist from Last.fm.

    Args:
        artist: Artist name.
        api_key: Last.fm API key. If None, uses LASTFM_API_KEY from config/env.

    Returns:
        Top tag name, or None if not found.
    """
    data = _call_lastfm_api("artist.getTopTags", api_key, artist=artist)
    if not data:
        return None
    tags = data.get("toptags", {}).get("tag", [])
    if tags:
        return tags[0].get("name")
    return None


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
    ranked = [(album, get_album_listeners(artist, album.title, api_key)) for album in albums]
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked
