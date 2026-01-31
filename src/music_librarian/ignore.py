"""Ignore list management for albums and artists."""

import json
from pathlib import Path

# Default location for ignore list
IGNORE_FILE = Path.home() / ".config" / "music-librarian" / "ignore.json"


def _load_ignore_list(path: Path | None = None) -> dict:
    """Load the ignore list from disk."""
    if path is None:
        path = IGNORE_FILE

    if not path.exists():
        return {"artists": [], "albums": []}

    with open(path) as f:
        return json.load(f)


def _save_ignore_list(data: dict, path: Path | None = None) -> None:
    """Save the ignore list to disk."""
    if path is None:
        path = IGNORE_FILE

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def add_ignored_artist(artist: str) -> bool:
    """Add an artist to the ignore list.

    Returns True if added, False if already present.
    """
    data = _load_ignore_list()
    artist_lower = artist.lower()

    if artist_lower not in [a.lower() for a in data["artists"]]:
        data["artists"].append(artist)
        _save_ignore_list(data)
        return True
    return False


def remove_ignored_artist(artist: str) -> bool:
    """Remove an artist from the ignore list.

    Returns True if removed, False if not found.
    """
    data = _load_ignore_list()
    artist_lower = artist.lower()

    for i, a in enumerate(data["artists"]):
        if a.lower() == artist_lower:
            data["artists"].pop(i)
            _save_ignore_list(data)
            return True
    return False


def add_ignored_album(artist: str, album: str) -> bool:
    """Add an album to the ignore list.

    Returns True if added, False if already present.
    """
    data = _load_ignore_list()
    artist_lower = artist.lower()
    album_lower = album.lower()

    for entry in data["albums"]:
        if entry["artist"].lower() == artist_lower and entry["album"].lower() == album_lower:
            return False

    data["albums"].append({"artist": artist, "album": album})
    _save_ignore_list(data)
    return True


def remove_ignored_album(artist: str, album: str) -> bool:
    """Remove an album from the ignore list.

    Returns True if removed, False if not found.
    """
    data = _load_ignore_list()
    artist_lower = artist.lower()
    album_lower = album.lower()

    for i, entry in enumerate(data["albums"]):
        if entry["artist"].lower() == artist_lower and entry["album"].lower() == album_lower:
            data["albums"].pop(i)
            _save_ignore_list(data)
            return True
    return False


def get_ignored_artists() -> list[str]:
    """Get list of ignored artists."""
    data = _load_ignore_list()
    return data["artists"]


def get_ignored_albums() -> list[dict]:
    """Get list of ignored albums."""
    data = _load_ignore_list()
    return data["albums"]


def is_artist_ignored(artist: str) -> bool:
    """Check if an artist is ignored."""
    data = _load_ignore_list()
    artist_lower = artist.lower()
    return any(a.lower() == artist_lower for a in data["artists"])


def is_album_ignored(artist: str, album: str) -> bool:
    """Check if an album is ignored."""
    data = _load_ignore_list()
    artist_lower = artist.lower()
    album_lower = album.lower()

    return any(
        entry["artist"].lower() == artist_lower and entry["album"].lower() == album_lower
        for entry in data["albums"]
    )
