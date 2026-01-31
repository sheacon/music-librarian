"""Qobuz API integration and qobuz-dl wrapper."""

import configparser
import hashlib
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from .config import QOBUZ_CONFIG_PATH
from .library import get_artist_search_variants, get_letter_for_artist, normalize_artist


# Minimum track count to be considered a full album (excludes singles/EPs)
MIN_ALBUM_TRACKS = 6


def _is_compilation_or_live(title: str) -> bool:
    """Check if album title indicates a compilation or live album."""
    title_lower = title.lower()

    # Greatest hits / compilation patterns
    compilation_patterns = [
        r"\bgreatest\s+hits\b",
        r"\bbest\s+of\b",
        r"\bessential\b",
        r"\bcollection\b",
        r"\banthology\b",
        r"\bretrospective\b",
        r"\bcompilation\b",
        r"\bcomplete\s+recordings\b",
        r"\bdefinitive\b",
        r"\bultimate\b",
        r"\bsingles\b",
        r"\bhits\b",
        r"\bfavorites\b",
        r"\brarities\b",
        r"\bouttakes\b",
        r"\bbox\s*set\b",
        r"\bbox\b.*\bset\b",
        r"\bthe\s+.+\s+box\s*$",  # "The ... Box" at end of title
    ]

    # Live album patterns
    live_patterns = [
        r"\blive\b",
        r"\bin\s+concert\b",
        r"\bunplugged\b",
        r"\bacoustic\s+live\b",
        r"\blive\s+at\b",
        r"\blive\s+from\b",
        r"\blive\s+in\b",
        r"\bstop\s+making\s+sense\b",  # Famous Talking Heads concert film
        r"\bname\s+of\s+this\s+band\b",  # "The Name of This Band Is..." live album
    ]

    for pattern in compilation_patterns + live_patterns:
        if re.search(pattern, title_lower):
            return True

    return False


def _normalize_album_title(title: str) -> str:
    """Normalize album title for deduplication.

    Strips trailing whitespace, edition markers, and normalizes punctuation.
    """
    normalized = title.lower().strip()

    # Remove common edition markers (in parentheses or brackets)
    edition_patterns = [
        # Parenthetical edition markers
        r"\s*\([^)]*deluxe[^)]*\)",
        r"\s*\([^)]*remaster[^)]*\)",
        r"\s*\([^)]*expanded[^)]*\)",
        r"\s*\([^)]*anniversary[^)]*\)",
        r"\s*\([^)]*special[^)]*\)",
        r"\s*\([^)]*edition[^)]*\)",
        r"\s*\([^)]*version[^)]*\)",
        r"\s*\([^)]*bonus[^)]*\)",
        r"\s*\([^)]*release[^)]*\)",  # (US Release), (UK Release), etc.
        r"\s*\(explicit\)",
        r"\s*\(clean\)",
        r"\s*\(stereo\)",
        r"\s*\(mono\)",
        r"\s*\(and more\)",
        # Bracketed edition markers
        r"\s*\[[^\]]*deluxe[^\]]*\]",
        r"\s*\[[^\]]*remaster[^\]]*\]",
        r"\s*\[[^\]]*edition[^\]]*\]",
        r"\s*\[[^\]]*super\s+deluxe[^\]]*\]",
        # Trailing edition markers
        r"\s*deluxe\s*edition\s*$",
        r"\s*remastered\s*$",
        r"\s*-\s*remaster\s*$",
        r"\s*\.\.\.and\s+more\s*$",
        r"\s*\(white\s+album\)",  # Beatles-specific subtitle
    ]
    for pattern in edition_patterns:
        normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE)

    # Normalize "&" to "and"
    normalized = normalized.replace("&", "and")

    # Normalize punctuation for matching
    # Replace colons, apostrophes (ASCII and Unicode), commas, and similar with spaces
    normalized = re.sub(r"[:'`'.,\u2018\u2019\u201c\u201d]", " ", normalized)

    # Collapse multiple spaces
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized.strip()


def _is_clean_version(title: str) -> bool:
    """Check if album title indicates a clean/censored version."""
    return "(clean)" in title.lower()


def _deduplicate_albums(albums: list["QobuzAlbum"]) -> list["QobuzAlbum"]:
    """Deduplicate albums, merging standard edition info with hi-fi versions.

    Groups albums by normalized_title, then:
    1. Filters out clean versions if explicit/regular versions exist
    2. Finds the "standard" edition (earliest year, fewest tracks)
    3. Finds the "best fidelity" edition (highest bit depth, then sample rate)
    4. If they differ and hi-fi has more tracks: use hi-fi URL but standard's
       year, and mark for track cleanup after download
    """
    from collections import defaultdict

    groups: dict[str, list[QobuzAlbum]] = defaultdict(list)

    for album in albums:
        key = _normalize_album_title(album.title)
        groups[key].append(album)

    result = []
    for group in groups.values():
        if len(group) == 1:
            result.append(group[0])
            continue

        # Filter out clean versions if non-clean versions exist
        non_clean = [a for a in group if not _is_clean_version(a.title)]
        if non_clean:
            group = non_clean

        if len(group) == 1:
            result.append(group[0])
            continue

        # Find standard edition: earliest year, then fewest tracks
        standard = sorted(group, key=lambda a: (a.year, a.tracks_count))[0]

        # Find best fidelity: highest bit depth, then sample rate
        best_fidelity = sorted(
            group, key=lambda a: (-a.bit_depth, -a.sample_rate)
        )[0]

        # Check if best fidelity is actually better
        is_higher_fidelity = (
            best_fidelity.bit_depth > standard.bit_depth
            or (
                best_fidelity.bit_depth == standard.bit_depth
                and best_fidelity.sample_rate > standard.sample_rate
            )
        )

        if is_higher_fidelity and best_fidelity.id != standard.id:
            # Use hi-fi version but with standard's year
            # Mark for track cleanup if hi-fi has more tracks
            merged = QobuzAlbum(
                id=best_fidelity.id,
                title=_normalize_album_title(standard.title).title(),
                year=standard.year,
                artist=best_fidelity.artist,
                url=best_fidelity.url,
                tracks_count=best_fidelity.tracks_count,
                bit_depth=best_fidelity.bit_depth,
                sample_rate=best_fidelity.sample_rate,
                standard_track_count=(
                    standard.tracks_count
                    if best_fidelity.tracks_count > standard.tracks_count
                    else None
                ),
                standard_id=(
                    standard.id
                    if best_fidelity.tracks_count > standard.tracks_count
                    else None
                ),
            )
            result.append(merged)
        else:
            # Standard edition is best or same fidelity
            result.append(standard)

    return result


@dataclass
class QobuzAlbum:
    """Represents an album from Qobuz."""

    id: str
    title: str
    year: int
    artist: str
    url: str
    tracks_count: int = 0
    bit_depth: int = 16
    sample_rate: float = 44.1
    # For merged albums: standard edition info for post-download cleanup
    standard_track_count: int | None = None  # If set, delete tracks beyond this
    standard_id: str | None = None  # ID of standard edition for track list lookup


def get_qobuz_credentials(config_path: Path | None = None) -> tuple[str, str]:
    """Read Qobuz credentials from qobuz-dl config.

    Returns:
        Tuple of (app_id, secret).
    """
    if config_path is None:
        config_path = QOBUZ_CONFIG_PATH

    if not config_path.exists():
        raise FileNotFoundError(
            f"qobuz-dl config not found at {config_path}. "
            "Please run 'qobuz-dl' first to set up credentials."
        )

    config = configparser.ConfigParser()
    config.read(config_path)

    app_id = config.get("DEFAULT", "app_id", fallback=None)
    secrets = config.get("DEFAULT", "secrets", fallback=None)

    if not app_id or not secrets:
        raise ValueError(
            "Missing app_id or secrets in qobuz-dl config. "
            "Please run 'qobuz-dl' to set up credentials."
        )

    # secrets is comma-separated, use the first one
    secret = secrets.split(",")[0].strip()

    return app_id, secret


def _get_auth_headers(app_id: str, secret: str) -> dict[str, str]:
    """Generate authentication headers for Qobuz API."""
    timestamp = str(int(time.time()))
    signature = hashlib.md5(f"{timestamp}{secret}".encode()).hexdigest()

    return {
        "X-App-Id": app_id,
        "X-Request-Ts": timestamp,
        "X-Request-Sign": signature,
    }


def search_artist(
    artist_name: str,
    app_id: str | None = None,
    secret: str | None = None,
) -> dict | None:
    """Search for an artist on Qobuz.

    Args:
        artist_name: Artist name to search for.
        app_id: Qobuz app ID. If None, reads from config.
        secret: Qobuz secret. If None, reads from config.

    Returns:
        Artist data dict or None if not found.
    """
    if app_id is None or secret is None:
        app_id, secret = get_qobuz_credentials()

    # Get search variants (with and without "The")
    variants = get_artist_search_variants(artist_name)

    with httpx.Client() as client:
        response = client.get(
            "https://www.qobuz.com/api.json/0.2/artist/search",
            params={"query": artist_name, "limit": 20},
            headers=_get_auth_headers(app_id, secret),
        )

        if response.status_code != 200:
            return None

        data = response.json()
        artists = data.get("artists", {}).get("items", [])

        # First, try exact match on any variant
        for artist in artists:
            name = artist.get("name", "").lower()
            for variant in variants:
                if name == variant.lower():
                    return artist

        # If no exact match, try prefix match with "The" (e.g., "The Black Keys")
        for artist in artists:
            name = artist.get("name", "").lower()
            if name.startswith("the "):
                name_without_the = name[4:]
                for variant in variants:
                    if name_without_the == variant.lower():
                        return artist

    return None


def get_artist_albums(
    artist_id: str,
    app_id: str | None = None,
    secret: str | None = None,
    albums_only: bool = True,
) -> list[QobuzAlbum]:
    """Get all albums for an artist from Qobuz.

    Args:
        artist_id: Qobuz artist ID.
        app_id: Qobuz app ID. If None, reads from config.
        secret: Qobuz secret. If None, reads from config.
        albums_only: If True, exclude singles and EPs (< MIN_ALBUM_TRACKS tracks).

    Returns:
        List of QobuzAlbum objects.
    """
    if app_id is None or secret is None:
        app_id, secret = get_qobuz_credentials()

    albums: list[QobuzAlbum] = []

    with httpx.Client() as client:
        response = client.get(
            "https://www.qobuz.com/api.json/0.2/artist/get",
            params={
                "artist_id": artist_id,
                "extra": "albums",
                "limit": 500,
            },
            headers=_get_auth_headers(app_id, secret),
        )

        if response.status_code == 200:
            data = response.json()
            artist_name = data.get("name", "Unknown")

            for album_data in data.get("albums", {}).get("items", []):
                # Skip compilations and appearances
                if album_data.get("artist", {}).get("id") != int(artist_id):
                    continue

                tracks_count = album_data.get("tracks_count", 0) or 0

                # Skip singles/EPs if albums_only is True
                if albums_only and tracks_count < MIN_ALBUM_TRACKS:
                    continue

                # Skip compilations and live albums
                title = album_data.get("title", "")
                if _is_compilation_or_live(title):
                    continue

                # Parse year from release_date_original (format: YYYY-MM-DD)
                release_date = album_data.get("release_date_original", "")
                year = 0
                if release_date and len(release_date) >= 4:
                    try:
                        year = int(release_date[:4])
                    except ValueError:
                        pass

                bit_depth = album_data.get("maximum_bit_depth", 16) or 16
                sample_rate = album_data.get("maximum_sampling_rate", 44.1) or 44.1

                albums.append(
                    QobuzAlbum(
                        id=str(album_data.get("id", "")),
                        title=album_data.get("title", "Unknown"),
                        year=year,
                        artist=artist_name,
                        url=f"https://www.qobuz.com/album/{album_data.get('id', '')}",
                        tracks_count=tracks_count,
                        bit_depth=bit_depth,
                        sample_rate=sample_rate,
                    )
                )

    # Deduplicate albums: prefer higher fidelity, then fewer tracks (standard edition)
    return _deduplicate_albums(albums)


def discover_missing_albums(
    artist_name: str,
    existing_albums: list[tuple[int, str]],
) -> list[QobuzAlbum]:
    """Find albums on Qobuz that aren't in the local library.

    Args:
        artist_name: Artist name to search for.
        existing_albums: List of (year, title) tuples from local library.

    Returns:
        List of QobuzAlbum objects not in local library.
    """
    artist = search_artist(artist_name)
    if not artist:
        return []

    qobuz_albums = get_artist_albums(str(artist["id"]))

    # Normalize existing album titles for comparison (strip edition markers)
    existing_normalized = {
        _normalize_album_title(title) for _, title in existing_albums
    }

    missing = []
    for album in qobuz_albums:
        normalized_title = _normalize_album_title(album.title)
        if normalized_title not in existing_normalized:
            missing.append(album)

    return missing


def get_album_tracks(
    album_id: str,
    app_id: str | None = None,
    secret: str | None = None,
) -> list[str]:
    """Get track titles for an album.

    Args:
        album_id: Qobuz album ID.
        app_id: Qobuz app ID. If None, reads from config.
        secret: Qobuz secret. If None, reads from config.

    Returns:
        List of track titles in order.
    """
    if app_id is None or secret is None:
        app_id, secret = get_qobuz_credentials()

    with httpx.Client() as client:
        response = client.get(
            "https://www.qobuz.com/api.json/0.2/album/get",
            params={"album_id": album_id},
            headers=_get_auth_headers(app_id, secret),
        )

        if response.status_code != 200:
            return []

        data = response.json()
        tracks = []
        for track in data.get("tracks", {}).get("items", []):
            title = track.get("title", "")
            if title:
                tracks.append(title)
        return tracks


def _normalize_track_title(title: str) -> str:
    """Normalize track title for matching."""
    # Remove common suffixes like "(Remastered)", version info, etc.
    normalized = title.lower().strip()
    patterns = [
        r"\s*\(remaster[^)]*\)",
        r"\s*\(mono[^)]*\)",
        r"\s*\(stereo[^)]*\)",
        r"\s*\(\d{4}[^)]*\)",  # Year annotations
    ]
    for pattern in patterns:
        normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE)
    return normalized.strip()


def remove_bonus_tracks(
    album_path: Path,
    standard_album_id: str,
) -> list[Path]:
    """Remove bonus tracks not in the standard edition.

    Args:
        album_path: Path to downloaded album folder.
        standard_album_id: Qobuz ID of the standard edition.

    Returns:
        List of removed file paths.
    """
    # Get standard edition track list
    standard_tracks = get_album_tracks(standard_album_id)
    if not standard_tracks:
        return []

    standard_normalized = {_normalize_track_title(t) for t in standard_tracks}

    # Find audio files in album folder
    removed = []
    for audio_file in album_path.glob("*.flac"):
        # Extract track title from filename (format: "01 - Track Title.flac")
        filename = audio_file.stem
        # Try to extract title after track number
        match = re.match(r"\d+[\s.\-]+(.+)", filename)
        if match:
            track_title = match.group(1)
        else:
            track_title = filename

        if _normalize_track_title(track_title) not in standard_normalized:
            audio_file.unlink()
            removed.append(audio_file)

    return removed


def download_album(
    url: str,
    artist_name: str | None = None,
    library_path: Path | None = None,
    album: QobuzAlbum | None = None,
) -> tuple[bool, Path | None]:
    """Download an album using qobuz-dl.

    Args:
        url: Qobuz album URL.
        artist_name: Artist name for folder structure. If None, uses default.
        library_path: Base library path. If None, uses default.
        album: QobuzAlbum object with metadata (for year override and track cleanup).

    Returns:
        Tuple of (success, album_path).
    """
    from .config import LIBRARY_PATH

    if library_path is None:
        library_path = LIBRARY_PATH

    # Determine output directory
    if artist_name:
        letter = get_letter_for_artist(artist_name)
        normalized = normalize_artist(artist_name)
        output_dir = library_path / letter / normalized
    else:
        output_dir = None

    cmd = [
        "qobuz-dl",
        "dl",
        url,
        "--embed-art",
    ]

    if output_dir:
        cmd.extend(["-d", str(output_dir)])
        # Use album year if provided, otherwise let qobuz-dl use its default
        if album and album.year:
            cmd.extend(["--folder-format", f"[{album.year}] {{album}}"])
        else:
            cmd.extend(["--folder-format", "[{year}] {album}"])

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        return False, None

    # Find the downloaded album folder
    album_path = None
    if output_dir and album:
        # Look for folder matching the expected pattern
        expected_prefix = f"[{album.year}]"
        for folder in output_dir.iterdir():
            if folder.is_dir() and folder.name.startswith(expected_prefix):
                album_path = folder
                break

    # Remove bonus tracks if this is a merged hi-fi/standard album
    if album_path and album and album.standard_id:
        remove_bonus_tracks(album_path, album.standard_id)

    # Embed artwork (ensures proper embedding even if qobuz-dl's --embed-art fails)
    if album_path:
        from .artwork import embed_artwork

        embed_artwork(album_path)

    return True, album_path
