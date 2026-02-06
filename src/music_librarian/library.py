"""Library scanning and parsing functionality."""

import re
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz, process

from .config import LIBRARY_PATH


@dataclass
class Album:
    """Represents an album in the library."""

    year: int
    title: str
    path: Path


@dataclass
class Artist:
    """Represents an artist in the library."""

    name: str
    canonical_name: str  # Name as stored in library (may have "The" prefix)
    albums: list[Album]
    path: Path


def normalize_artist(name: str) -> str:
    """Normalize artist name by stripping leading 'The ' prefix."""
    if name.lower().startswith("the "):
        return name[4:]
    return name


def get_artist_search_variants(name: str) -> list[str]:
    """Get search variants for an artist name (with and without 'The')."""
    normalized = normalize_artist(name)
    variants = [normalized]
    if normalized == name:
        # Original didn't have "The", add variant with it
        variants.append(f"The {name}")
    else:
        # Original had "The", normalized version is already different
        variants.append(name)
    return variants


def parse_album_folder(folder_name: str) -> tuple[int, str] | None:
    """Parse album folder name in format '[YYYY] Album Title'.

    Returns (year, title) tuple or None if parsing fails.
    """
    match = re.match(r"\[(\d{4})\]\s*(.+)", folder_name)
    if match:
        return int(match.group(1)), match.group(2)
    return None


def get_letter_for_artist(artist_name: str) -> str:
    """Get the alphabetical letter folder for an artist.

    Strips 'The ' prefix and uses first letter of remaining name.
    """
    normalized = normalize_artist(artist_name)
    if normalized:
        return normalized[0].upper()
    return "A"  # Fallback


def scan_library(library_path: Path | None = None) -> dict[str, Artist]:
    """Scan the music library and return a dict of artists.

    Args:
        library_path: Path to library root. Defaults to LIBRARY_PATH.

    Returns:
        Dict mapping normalized artist name to Artist object.
    """
    if library_path is None:
        library_path = LIBRARY_PATH

    artists: dict[str, Artist] = {}

    if not library_path.exists():
        return artists

    # Iterate through letter folders (A, B, C, etc.)
    for letter_folder in sorted(library_path.iterdir()):
        if not letter_folder.is_dir() or len(letter_folder.name) != 1:
            continue

        # Iterate through artist folders
        for artist_folder in sorted(letter_folder.iterdir()):
            if not artist_folder.is_dir():
                continue

            artist_name = artist_folder.name
            normalized_name = normalize_artist(artist_name)
            albums: list[Album] = []

            # Iterate through album folders
            for album_folder in sorted(artist_folder.iterdir()):
                if not album_folder.is_dir():
                    continue

                parsed = parse_album_folder(album_folder.name)
                if parsed:
                    year, title = parsed
                    albums.append(Album(year=year, title=title, path=album_folder))

            if albums:
                artists[normalized_name] = Artist(
                    name=normalized_name,
                    canonical_name=artist_name,
                    albums=albums,
                    path=artist_folder,
                )

    return artists


def parse_new_folder(folder_name: str) -> tuple[str, int, str] | None:
    """Parse folder name in format '{Artist} - [{YYYY}] {Album Title}'.

    Returns (artist, year, title) tuple or None if parsing fails.
    """
    match = re.match(r"^(.+?)\s*-\s*\[(\d{4})\]\s*(.+)$", folder_name)
    if match:
        return match.group(1).strip(), int(match.group(2)), match.group(3).strip()
    return None


def check_volume_mounted(volume_path: Path) -> bool:
    """Check if a network volume is mounted.

    On macOS, /Volumes/music may exist as an empty stub when unmounted.
    Checks for actual content to confirm the volume is mounted.
    """
    if not volume_path.exists() or not volume_path.is_dir():
        return False
    try:
        return any(volume_path.iterdir())
    except PermissionError:
        return False


def get_artist_path(artist_name: str, library_path: Path | None = None) -> Path:
    """Get the expected path for an artist in the library."""
    if library_path is None:
        library_path = LIBRARY_PATH

    letter = get_letter_for_artist(artist_name)
    normalized = normalize_artist(artist_name)
    return library_path / letter / normalized


def find_matching_artist(query: str, artists: list[str], threshold: int = 80) -> str | None:
    """Find best matching artist using fuzzy matching.

    Args:
        query: Artist name to search for.
        artists: List of artist names to match against.
        threshold: Minimum score (0-100) to consider a match.

    Returns:
        Best matching artist name, or None if no match above threshold.
    """
    if not artists:
        return None

    # Create lowercase mapping to handle case-insensitive matching
    lower_to_original = {a.lower(): a for a in artists}
    lower_artists = list(lower_to_original.keys())

    # Use token_set_ratio for word order independence
    result = process.extractOne(
        query.lower(),
        lower_artists,
        scorer=fuzz.token_set_ratio,
        score_cutoff=threshold,
    )

    if result:
        return lower_to_original[result[0]]
    return None
