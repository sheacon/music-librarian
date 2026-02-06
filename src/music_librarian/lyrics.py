"""Lyrics fetching from LRCLIB and Genius."""

import re

import httpx
from bs4 import BeautifulSoup

from .config import GENIUS_API_KEY

LRCLIB_API_URL = "https://lrclib.net/api/get"
GENIUS_API_URL = "https://api.genius.com"


def get_lyrics_from_lrclib(
    artist: str,
    title: str,
    album: str | None = None,
) -> str | None:
    """Fetch plain lyrics from LRCLIB.

    Args:
        artist: Artist name.
        title: Track title.
        album: Album name (optional, improves matching).

    Returns:
        Plain lyrics text, or None if not found.
    """
    try:
        params = {
            "artist_name": artist,
            "track_name": title,
        }
        if album:
            params["album_name"] = album

        with httpx.Client(timeout=10) as client:
            response = client.get(LRCLIB_API_URL, params=params)

            if response.status_code != 200:
                return None

            data = response.json()
            # Prefer plain lyrics, fall back to synced lyrics stripped of timestamps
            plain = data.get("plainLyrics")
            if plain:
                return plain

            synced = data.get("syncedLyrics")
            if synced:
                # Strip timestamps like [00:23.45]
                return re.sub(r"\[\d{2}:\d{2}\.\d{2}\]\s*", "", synced)

            return None
    except Exception:
        return None


def get_lyrics_from_genius(
    artist: str,
    title: str,
    api_key: str | None = None,
) -> str | None:
    """Fetch lyrics from Genius.

    Args:
        artist: Artist name.
        title: Track title.
        api_key: Genius API key. If None, uses GENIUS_API_KEY from config/env.

    Returns:
        Lyrics text, or None if not found.
    """
    if api_key is None:
        api_key = GENIUS_API_KEY

    if not api_key:
        return None

    try:
        # Search for the song
        with httpx.Client(timeout=10) as client:
            response = client.get(
                f"{GENIUS_API_URL}/search",
                params={"q": f"{artist} {title}"},
                headers={"Authorization": f"Bearer {api_key}"},
            )

            if response.status_code != 200:
                return None

            data = response.json()
            hits = data.get("response", {}).get("hits", [])

            if not hits:
                return None

            # Find best match - look for matching artist
            song_url = None
            artist_lower = artist.lower()
            for hit in hits:
                result = hit.get("result", {})
                primary_artist = result.get("primary_artist", {}).get("name", "").lower()
                if artist_lower in primary_artist or primary_artist in artist_lower:
                    song_url = result.get("url")
                    break

            # Fall back to first result if no artist match
            if not song_url and hits:
                song_url = hits[0].get("result", {}).get("url")

            if not song_url:
                return None

            # Scrape lyrics from the song page
            response = client.get(song_url, follow_redirects=True)
            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.text, "html.parser")

            # Genius uses data-lyrics-container attribute for lyrics
            lyrics_containers = soup.find_all(attrs={"data-lyrics-container": "true"})
            if lyrics_containers:
                lyrics_parts = []
                for container in lyrics_containers:
                    # Remove header divs that contain metadata (contributors, etc.)
                    for header in container.find_all(
                        class_=lambda c: c and "LyricsHeader" in str(c)
                    ):
                        header.decompose()

                    # Get text, replacing <br> with newlines
                    for br in container.find_all("br"):
                        br.replace_with("\n")
                    text = container.get_text()

                    # Skip empty containers
                    if len(text.strip()) < 10:
                        continue

                    lyrics_parts.append(text)
                return "\n".join(lyrics_parts).strip()

            return None
    except Exception:
        return None


def get_lyrics(
    artist: str,
    title: str,
    album: str | None = None,
    genius_api_key: str | None = None,
) -> tuple[str | None, str]:
    """Fetch lyrics, trying LRCLIB first then Genius.

    Args:
        artist: Artist name.
        title: Track title.
        album: Album name (optional).
        genius_api_key: Genius API key for fallback.

    Returns:
        Tuple of (lyrics, source) where source is "lrclib", "genius", or "none".
    """
    # Try LRCLIB first
    lyrics = get_lyrics_from_lrclib(artist, title, album)
    if lyrics:
        return lyrics, "lrclib"

    # Fall back to Genius
    lyrics = get_lyrics_from_genius(artist, title, genius_api_key)
    if lyrics:
        return lyrics, "genius"

    return None, "none"
