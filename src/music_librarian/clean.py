"""Clean edition markers from album folders, filenames, and metadata."""

import re
from pathlib import Path

from mutagen.flac import FLAC


# Patterns to remove from titles (these appear at the end or in parentheses/brackets)
EDITION_PATTERNS = [
    r"\s*\(\d{4}\s+remaster(ed)?\)",  # (2020 Remaster), (2020 Remastered)
    r"\s*\[\d{4}\s+remaster(ed)?\]",  # [2020 Remaster]
    r"\s*\(remaster(ed)?\s+\d{4}\)",  # (Remastered 2020)
    r"\s*\(remaster(ed)?\)",  # (Remaster), (Remastered)
    r"\s*\[remaster(ed)?\]",  # [Remaster]
    r"\s*-\s*remaster(ed)?(\s+\d{4})?\s*$",  # - Remastered, - Remaster 2020
    r"\s*\(deluxe(\s+edition)?\)",  # (Deluxe), (Deluxe Edition)
    r"\s*\[deluxe(\s+edition)?\]",  # [Deluxe]
    r"\s*\(super\s+deluxe(\s+edition)?\)",  # (Super Deluxe Edition)
    r"\s*\[super\s+deluxe(\s+edition)?\]",  # [Super Deluxe]
    r"\s*\(expanded(\s+edition)?\)",  # (Expanded), (Expanded Edition)
    r"\s*\(\d+th\s+anniversary(\s+edition)?\)",  # (25th Anniversary Edition)
    r"\s*\(anniversary(\s+edition)?\)",  # (Anniversary Edition)
    r"\s*\(special\s+edition\)",  # (Special Edition)
    r"\s*\(bonus\s+track(\s+version)?\)",  # (Bonus Track Version)
    r"\s*\(explicit\)",  # (Explicit)
    r"\s*\(clean\)",  # (Clean)
]


def clean_title(title: str) -> str:
    """Remove edition markers from a title string."""
    cleaned = title
    for pattern in EDITION_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def clean_album_folder(album_path: Path) -> Path | None:
    """Rename album folder to remove edition markers.

    Args:
        album_path: Path to album folder.

    Returns:
        New path if renamed, None if no change needed.
    """
    if not album_path.exists() or not album_path.is_dir():
        return None

    folder_name = album_path.name
    cleaned_name = clean_title(folder_name)

    if cleaned_name != folder_name:
        new_path = album_path.parent / cleaned_name
        # Handle case where target already exists
        if new_path.exists():
            return None
        album_path.rename(new_path)
        return new_path

    return None


def clean_track_files(album_path: Path) -> list[tuple[Path, Path]]:
    """Rename track files to remove edition markers.

    Args:
        album_path: Path to album folder.

    Returns:
        List of (old_path, new_path) tuples for renamed files.
    """
    renamed = []

    for audio_file in album_path.glob("*.flac"):
        old_name = audio_file.stem
        cleaned_name = clean_title(old_name)

        if cleaned_name != old_name:
            new_path = audio_file.parent / f"{cleaned_name}{audio_file.suffix}"
            if not new_path.exists():
                audio_file.rename(new_path)
                renamed.append((audio_file, new_path))

    return renamed


def clean_track_metadata(album_path: Path) -> int:
    """Clean edition markers from track metadata.

    Args:
        album_path: Path to album folder.

    Returns:
        Number of tracks with metadata cleaned.
    """
    cleaned_count = 0

    for audio_file in album_path.glob("*.flac"):
        try:
            audio = FLAC(audio_file)
            modified = False

            # Clean title tag
            if "title" in audio:
                old_title = audio["title"][0]
                new_title = clean_title(old_title)
                if new_title != old_title:
                    audio["title"] = new_title
                    modified = True

            # Clean album tag
            if "album" in audio:
                old_album = audio["album"][0]
                new_album = clean_title(old_album)
                if new_album != old_album:
                    audio["album"] = new_album
                    modified = True

            if modified:
                audio.save()
                cleaned_count += 1

        except Exception:
            # Skip files that can't be processed
            pass

    return cleaned_count


def clean_album(album_path: Path) -> dict:
    """Clean edition markers from an album (folder, files, and metadata).

    Args:
        album_path: Path to album folder.

    Returns:
        Dict with cleaning results.
    """
    results = {
        "folder_renamed": False,
        "new_folder_path": None,
        "files_renamed": 0,
        "metadata_cleaned": 0,
    }

    if not album_path.exists() or not album_path.is_dir():
        return results

    # Clean folder name first
    new_path = clean_album_folder(album_path)
    if new_path:
        results["folder_renamed"] = True
        results["new_folder_path"] = new_path
        album_path = new_path

    # Clean track filenames
    renamed = clean_track_files(album_path)
    results["files_renamed"] = len(renamed)

    # Clean track metadata
    results["metadata_cleaned"] = clean_track_metadata(album_path)

    return results
